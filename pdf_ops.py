"""
pdf_ops.py
----------
Low-level, reusable primitives for redact-and-replace text editing. Every
higher-level page handler (cover.py, bespoke.py, vessel.py, contact.py) is
built on top of these two functions so the "don't touch the background
photo/gradient" safety rule lives in exactly one place.
"""

import fitz


def redact_zone(page: "fitz.Page", bbox):
    """
    Remove the glyphs inside `bbox` and nothing else. `images=PDF_REDACT_IMAGE_NONE`
    is the load-bearing safety setting here: it tells PyMuPDF to leave the
    background image/gradient layer completely untouched, so the real photo
    shows through with zero seam. `graphics=1` clears vector fill (e.g. the
    orange table background) only within the box; `text=0` means "don't also
    auto-strike the annotation," we already removed the glyphs via the redact.
    """
    rect = fitz.Rect(bbox)
    page.add_redact_annot(rect)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE, graphics=1, text=0)
    return rect


def draw_text(page: "fitz.Page", origin, text: str, fontname: str, size: float, color=(0, 0, 0), fontfile=None):
    page.insert_text(origin, text, fontname=fontname, fontfile=fontfile, fontsize=size, color=color)


def draw_field(page, spec: dict, text: str, font_mgr, warnings: list, field_name: str):
    """
    Generalised version of the original static `draw_field`: redacts the old
    value's bbox, then draws the new value using the resolved brand/fallback
    font, auto-shrinking (with a validation warning) if it would overflow.
    """
    bbox = fitz.Rect(spec["bbox"])
    redact_zone(page, bbox)
    font_mgr.ensure_registered(page)

    bold = spec.get("bold", False)
    fontname = font_mgr.font_name(bold)
    fontfile = font_mgr.bold_path if bold else font_mgr.regular_path
    base_size = spec["size"]

    align = spec.get("align")
    box_width = spec.get("max_width", bbox.x1 - bbox.x0)
    size = font_mgr.fit_font_size(text, box_width, base_size, bold, field_name, warnings)

    if align == "right":
        text_width = font_mgr.text_length(text, size, bold)
        x = spec["right_x"] - text_width
        y = spec["y"]
    elif align == "center":
        cx = (bbox.x0 + bbox.x1) / 2
        text_width = font_mgr.text_length(text, size, bold)
        x = cx - text_width / 2
        y = spec.get("origin", (0, bbox.y1 - 0.8))[1]
    else:
        x, y = spec["origin"]

    draw_text(page, (x, y), text, fontname, size, color=spec.get("color", (0, 0, 0)), fontfile=fontfile)
