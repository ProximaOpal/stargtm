"""
bespoke.py
----------
Everything about Page 13 ("Your Bespoke Package"), plus the overflow
mechanism onto Page 14 ("Added Extras"):

1. render_financials       -- inject guest count / cost / VAT / grand total
2. render_upgrade_list     -- "Conditional Inclusion": only print upgrades the
                               client actually selected, stacked with no gaps
3. render_package_columns  -- "Stacking Algorithm": flow the three bespoke
                               description columns, overflowing extra content
                               onto a generated continuation page if the
                               wording is too long to fit
"""

import fitz

import config
from pdf_ops import redact_zone, draw_text, draw_field


# ---------------------------------------------------------------------------
# 1. FINANCIALS
# ---------------------------------------------------------------------------
def render_financials(doc: "fitz.Document", calculations: dict, font_mgr, warnings: list):
    page = doc[config.PAGE_BESPOKE_PACKAGE]
    font_mgr.ensure_registered(page)

    mapping = {
        "pkg_guests": calculations.get("guests"),
        "pkg_cost": _money(calculations.get("package_cost")),
        "pkg_vat": _money(calculations.get("vat")),
        "pkg_total": _money(calculations.get("grand_total")),
    }
    for field_name, value in mapping.items():
        if value is None:
            continue
        spec = config.FINANCIAL_FIELDS[field_name]
        draw_field(page, spec, str(value), font_mgr, warnings, field_name)


def _money(value) -> str:
    if value is None:
        return None
    return f"{float(value):,.2f}"


# ---------------------------------------------------------------------------
# 2. CONDITIONAL UPGRADE LIST
# ---------------------------------------------------------------------------
def render_upgrade_list(doc: "fitz.Document", selected_upgrades, font_mgr, warnings: list):
    """
    Clears the entire "Consider upgrading..." bullet zone and redraws only
    the upgrades in `selected_upgrades` (a list/set of catalogue `id`s), in
    catalogue order, stacked back-to-back with the template's original row
    pitch -- so skipping "Live DJ" doesn't leave a blank line where it used
    to be; everything below it simply shifts up.
    """
    cfg = config.UPGRADE_LIST
    page = doc[cfg["page"]]
    font_mgr.ensure_registered(page)

    redact_zone(page, cfg["clear_zone"])

    selected = set(selected_upgrades or [])
    chosen = [item for item in config.UPGRADE_CATALOGUE if item["id"] in selected]

    if not chosen:
        return  # nothing selected -- leave the zone blank, that's correct

    cursor_y = cfg["first_baseline_y"]
    bullet_font = font_mgr.font_name(False)
    fontfile = font_mgr.regular_path

    for item in chosen:
        lines = _wrap(font_mgr, item["label"], cfg["text_size"], False, cfg["max_width"])
        for i, line in enumerate(lines):
            if i == 0:
                draw_text(page, (cfg["bullet_x"], cursor_y), "\u2022", bullet_font, cfg["bullet_size"], fontfile=fontfile)
            draw_text(page, (cfg["text_x"], cursor_y), line, bullet_font, cfg["text_size"], fontfile=fontfile)
            cursor_y += cfg["row_pitch"]

    bottom_limit = cfg["clear_zone"][3]
    if cursor_y > bottom_limit:
        warnings.append(
            type("ValidationWarning", (), {"field": "upgrade_list", "message": (
                f"{len(chosen)} selected upgrades overflow the upgrade panel by "
                f"{round(cursor_y - bottom_limit, 1)}pt -- consider trimming the selection "
                f"or shrinking row_pitch in config.UPGRADE_LIST."
            )})()
        )


# ---------------------------------------------------------------------------
# 3. STACKING ALGORITHM + OVERFLOW HANDLER
# ---------------------------------------------------------------------------
def render_package_columns(doc: "fitz.Document", package_wording: dict, font_mgr, warnings: list):
    """
    `package_wording` maps each column name in config.PACKAGE_COLUMNS to a
    list of groups: [{"heading": "Entertainment", "items": ["...", "..."]}, ...]

    Each column is flowed independently. If a column's content is too long
    for Page 13, the overflow continues into the matching column position on
    a generated continuation page inserted directly after Page 14 ("Added
    Extras (continued)"), keeping the original Added Extras content intact.
    """
    # --- Pass 1: clear + flow every column onto Page 13 itself, collecting
    # whatever doesn't fit. We deliberately do NOT insert the continuation
    # page inside this loop: doc.new_page() shifts page indices and
    # invalidates any fitz.Page object obtained before the insert, which
    # would silently corrupt subsequent column edits on Page 13.
    overflow_by_column = {}
    for col_cfg in config.PACKAGE_COLUMNS:
        groups = package_wording.get(col_cfg["name"], [])
        if not groups:
            continue

        page13 = doc[config.PAGE_BESPOKE_PACKAGE]  # re-fetch: safe even before any insert
        font_mgr.ensure_registered(page13)

        lines = _flatten_groups(groups, font_mgr, col_cfg["width"] - 6)

        clear_bbox = (col_cfg["x"] - 2, col_cfg["top_y"] - 8, col_cfg["x"] + col_cfg["width"] + 10, col_cfg["max_y"] + 4)
        redact_zone(page13, clear_bbox)

        overflow_index = _flow_lines(page13, col_cfg, lines, font_mgr)
        if overflow_index is not None:
            overflow_by_column[col_cfg["name"]] = lines[overflow_index:]

    if not overflow_by_column:
        return False

    # --- Pass 2: everything that didn't fit gets one shared continuation page ---
    continuation_page = _create_continuation_page(doc)
    for col_cfg in config.PACKAGE_COLUMNS:
        remaining = overflow_by_column.get(col_cfg["name"])
        if not remaining:
            continue
        cont_col_cfg = dict(col_cfg, top_y=40, max_y=continuation_page.rect.height - 20)
        still_over = _flow_lines(continuation_page, cont_col_cfg, remaining, font_mgr)
        if still_over is not None:
            warnings.append(
                type("ValidationWarning", (), {"field": col_cfg["name"], "message": (
                    f"Column '{col_cfg['name']}' still overflows even after adding a "
                    f"continuation page -- wording needs manual trimming."
                )})()
            )

    return True


def _flatten_groups(groups, font_mgr, width):
    lines = []
    for group in groups:
        heading = group.get("heading")
        if heading:
            lines.append(("heading", heading))
        for item_text in group.get("items", []):
            wrapped = _wrap(font_mgr, item_text, config.PACKAGE_TEXT_SIZE, False, width)
            for i, ln in enumerate(wrapped):
                lines.append(("item" if i == 0 else "item_cont", ln))
    return lines


def _flow_lines(page, col_cfg, lines, font_mgr, start_index=0):
    """
    Draws lines starting at `start_index` until the column's `max_y` would be
    exceeded. Returns the index of the first line that didn't fit, or None
    if every line fit on this page.
    """
    cursor_y = col_cfg["top_y"]
    fontname = font_mgr.font_name(False)
    fontfile = font_mgr.regular_path
    i = start_index
    while i < len(lines):
        if cursor_y + config.PACKAGE_ROW_PITCH > col_cfg["max_y"]:
            return i
        kind, text = lines[i]
        indent = 0 if kind == "heading" else 7.4
        bullet_x = col_cfg["x"] + indent
        text_x = col_cfg["text_x"] + indent
        draw_text(page, (bullet_x, cursor_y), "\u2022", fontname, config.PACKAGE_TEXT_SIZE, fontfile=fontfile)
        draw_text(page, (text_x, cursor_y), text, fontname, config.PACKAGE_TEXT_SIZE, fontfile=fontfile)
        cursor_y += config.PACKAGE_ROW_PITCH
        i += 1
    return None


def _create_continuation_page(doc: "fitz.Document") -> "fitz.Page":
    """
    Inserts a plain continuation page directly after Page 14 (Added Extras),
    sized to match the template, with a minimal running header so it reads
    as part of the document rather than a dropped-in blank sheet.

    This is a functional placeholder: if WEOTT supplies a branded "overflow"
    template (matching background art), swap the body of this function to
    insert_pdf() that asset instead of fitz.new_page().
    """
    template_rect = doc[config.PAGE_BESPOKE_PACKAGE].rect
    insert_at = config.PAGE_ADDED_EXTRAS + 1
    page = doc.new_page(insert_at, width=template_rect.width, height=template_rect.height)

    page.insert_text((22.7, 30), "YOUR BESPOKE PACKAGE (CONTINUED)", fontsize=14, color=(0.13, 0.13, 0.13))
    page.draw_line((22.7, 35), (template_rect.width - 22.7, 35), color=(0.94, 0.55, 0.2), width=1.2)
    return page


def _wrap(font_mgr, text: str, size: float, bold: bool, max_width: float):
    words = text.split()
    if not words:
        return [""]
    lines = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if font_mgr.text_length(trial, size, bold) <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines
