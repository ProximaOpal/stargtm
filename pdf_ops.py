"""
pdf_ops.py
----------
Low-level redact-and-replace primitives. Prefer batched redaction
(apply once per page) for speed.
"""

import fitz

import config


def add_redact(page: "fitz.Page", bbox):
    """Queue a redact annotation without applying yet."""
    page.add_redact_annot(fitz.Rect(bbox))


def apply_redacts(page: "fitz.Page", *, clear_graphics: bool = False):
    """Apply all queued redacts on this page in one pass."""
    page.apply_redactions(
        images=fitz.PDF_REDACT_IMAGE_NONE,
        graphics=1 if clear_graphics else 0,
        text=0,
    )


def redact_zone(page: "fitz.Page", bbox, *, clear_graphics: bool = False):
    """Immediate redact (single zone). Prefer add_redact + apply_redacts for batches."""
    add_redact(page, bbox)
    apply_redacts(page, clear_graphics=clear_graphics)
    return fitz.Rect(bbox)


def draw_text(page: "fitz.Page", origin, text: str, fontname: str, size: float,
              color=None, fontfile=None):
    if color is None:
        color = config.TEXT_COLOR
    text = (
        text.replace("\u00ad", "-")
            .replace("\u2010", "-")
            .replace("\u2011", "-")
    )
    page.insert_text(origin, text, fontname=fontname, fontfile=fontfile, fontsize=size, color=color)


def prepare_field_draw(spec: dict, text: str, font_mgr, warnings: list, field_name: str):
    """Compute draw parameters for a field without touching the page."""
    bbox = fitz.Rect(spec["bbox"])
    bold = spec.get("bold", False)
    fontname = font_mgr.font_name(bold)
    fontfile = font_mgr.bold_path if bold else font_mgr.regular_path
    base_size = spec["size"]
    color = spec.get("color", config.TEXT_COLOR)
    prefix = spec.get("prefix", "")
    draw_str = f"{prefix}{text}" if prefix else text

    align = spec.get("align")
    box_width = spec.get("max_width", max(bbox.x1 - bbox.x0, 1.0))
    size = font_mgr.fit_font_size(draw_str, box_width, base_size, bold, field_name, warnings)

    if align == "right":
        text_width = font_mgr.text_length(draw_str, size, bold)
        x = spec["right_x"] - text_width
        y = spec["y"]
    elif align == "center":
        cx = (bbox.x0 + bbox.x1) / 2
        text_width = font_mgr.text_length(draw_str, size, bold)
        x = cx - text_width / 2
        y = spec.get("origin", (0, bbox.y1 - 0.8))[1]
    else:
        x, y = spec["origin"]

    prepared = {
        "bbox": bbox,
        "draw_str": draw_str,
        "fontname": fontname,
        "fontfile": fontfile,
        "size": size,
        "color": color,
        "origin": (x, y),
        "bold": bold,
        "deep_bold": bool(spec.get("deep_bold")),
    }
    suffix = spec.get("suffix")
    if suffix:
        prepared["suffix"] = suffix
        prepared["suffix_bold"] = spec.get("suffix_bold", False)
    return prepared


def draw_prepared(page, prepared: dict, font_mgr=None):
    draw_text(
        page,
        prepared["origin"],
        prepared["draw_str"],
        prepared["fontname"],
        prepared["size"],
        color=prepared["color"],
        fontfile=prepared["fontfile"],
    )
    # Slight horizontal echo thickens white finance figures without bloating glyphs
    if prepared.get("deep_bold"):
        x, y = prepared["origin"]
        draw_text(
            page,
            (x + 0.18, y),
            prepared["draw_str"],
            prepared["fontname"],
            prepared["size"],
            color=prepared["color"],
            fontfile=prepared["fontfile"],
        )
    suffix = prepared.get("suffix")
    if not suffix:
        return
    # Re-draw trailing static text (e.g. " guests") after a wider digit count
    x, y = prepared["origin"]
    if font_mgr is not None:
        num_w = font_mgr.text_length(
            prepared["draw_str"], prepared["size"], prepared.get("bold", False)
        )
        s_bold = prepared.get("suffix_bold", False)
        # Small optical gap so 3-digit counts don't collide with "guests"
        gap = 0.7 if len(prepared["draw_str"].strip()) >= 3 else 0.0
        draw_text(
            page,
            (x + num_w + gap, y),
            suffix,
            font_mgr.font_name(s_bold),
            prepared["size"],
            color=prepared["color"],
            fontfile=font_mgr.bold_path if s_bold else font_mgr.regular_path,
        )
    else:
        draw_text(
            page,
            (x + len(prepared["draw_str"]) * prepared["size"] * 0.5, y),
            suffix,
            prepared["fontname"],
            prepared["size"],
            color=prepared["color"],
            fontfile=prepared["fontfile"],
        )


def draw_field(page, spec: dict, text: str, font_mgr, warnings: list, field_name: str):
    """Single-field redact+draw (slower). Prefer batching in page handlers."""
    prepared = prepare_field_draw(spec, text, font_mgr, warnings, field_name)
    add_redact(page, prepared["bbox"])
    apply_redacts(page, clear_graphics=False)
    font_mgr.ensure_registered(page)
    draw_prepared(page, prepared, font_mgr=font_mgr)


def draw_fields_batched(page, items: list, font_mgr, *, clear_graphics: bool = False):
    """
    items: list of prepared dicts from prepare_field_draw (must include bbox).
    Queues all redacts, applies once, then draws all text.
    """
    if not items:
        return
    font_mgr.ensure_registered(page)
    for item in items:
        add_redact(page, item["bbox"])
    apply_redacts(page, clear_graphics=clear_graphics)
    for item in items:
        draw_prepared(page, item, font_mgr=font_mgr)
