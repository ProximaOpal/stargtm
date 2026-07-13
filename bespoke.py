"""
bespoke.py
----------
Everything about Page 13 ("Your Bespoke Package"), plus overflow onto Page 14:

1. render_financials       -- guest count / cost / VAT / grand total
2. render_upgrade_list     -- conditional inclusion of selected upgrades
3. render_package_columns  -- stacking algorithm + overflow continuation
4. apply_menu_links        -- rewrite / attach current-year menu URLs
"""

import fitz

import config
from pdf_ops import redact_zone, draw_text, draw_field


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


def render_upgrade_list(doc: "fitz.Document", selected_upgrades, font_mgr, warnings: list):
    """
    Clears the upgrade bullet zone and redraws only selected upgrades in
    catalogue order, stacked with no gaps.
    """
    cfg = config.UPGRADE_LIST
    page = doc[cfg["page"]]
    font_mgr.ensure_registered(page)

    # clear_graphics=True removes orphaned underlines left by the template
    # (e.g. orange "click here" rules) once the glyph text is wiped.
    redact_zone(page, cfg["clear_zone"], clear_graphics=True)

    selected = set(selected_upgrades or [])
    chosen = [item for item in config.UPGRADE_CATALOGUE if item["id"] in selected]

    if not chosen:
        return

    cursor_y = cfg["first_baseline_y"]
    # Always draw the upgrade column with the bundled fallback font. The
    # template-extracted Century Gothic subset reports advances for '£' but
    # embeds a broken glyph for it; Poppins renders currency correctly.
    import os
    fallback_path = os.path.join(os.path.dirname(font_mgr.regular_path), "Fallback-Regular.ttf")
    if not os.path.exists(fallback_path):
        fallback_path = font_mgr.regular_path
    page.insert_font(fontname="UpgradeRegular", fontfile=fallback_path)
    bullet_font = "UpgradeRegular"
    fontfile = fallback_path

    class _FallbackMeasure:
        def __init__(self):
            self._font = fitz.Font(fontfile=fallback_path)

        def text_length(self, text, size, bold):
            return self._font.text_length(text, fontsize=size)

    wrap_mgr = _FallbackMeasure()

    for item in chosen:
        # Normalise hyphens/dashes so we never emit soft-hyphen artefacts
        label = item["label"].replace("\u00ad", "-").replace("–", "-").replace("—", "-")
        lines = _wrap(wrap_mgr, label, cfg["text_size"], False, cfg["max_width"])
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


def render_package_columns(doc: "fitz.Document", package_wording: dict, font_mgr, warnings: list):
    """
    Flow each package column. Overflow continues onto a continuation page
    inserted after Page 14.
    """
    overflow_by_column = {}

    # Wipe the entire three-column package region once up front so leftover
    # underlines / partial glyphs from the template cannot survive between columns.
    page13 = doc[config.PAGE_BESPOKE_PACKAGE]
    font_mgr.ensure_registered(page13)
    redact_zone(page13, config.PACKAGE_CLEAR_ZONE, clear_graphics=True)

    for col_cfg in config.PACKAGE_COLUMNS:
        groups = package_wording.get(col_cfg["name"], [])
        if not groups:
            continue

        page13 = doc[config.PAGE_BESPOKE_PACKAGE]  # re-fetch after any prior ops
        font_mgr.ensure_registered(page13)

        lines = _flatten_groups(groups, font_mgr, col_cfg["width"] - 6)

        overflow_index = _flow_lines(page13, col_cfg, lines, font_mgr)
        if overflow_index is not None:
            overflow_by_column[col_cfg["name"]] = lines[overflow_index:]

    if not overflow_by_column:
        return False

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


def apply_menu_links(doc: "fitz.Document", menu_links: dict, warnings: list):
    """
    Attach / rewrite Page 13 menu and mood-board URIs.

    `menu_links` keys match config.MENU_LINK_TARGETS (food_menu, street_food_menu,
    mood_board). Values are absolute https URLs for the current season/year.
    """
    if not menu_links:
        return

    page = doc[config.PAGE_BESPOKE_PACKAGE]
    existing = list(page.get_links())

    for key, uri in menu_links.items():
        if not uri:
            continue
        target = config.MENU_LINK_TARGETS.get(key)
        if not target:
            warnings.append(
                type("ValidationWarning", (), {"field": "menu_links", "message": (
                    f"Unknown menu link key '{key}'. Known: {list(config.MENU_LINK_TARGETS)}"
                )})()
            )
            continue

        click = fitz.Rect(target["click_bbox"])
        # Remove any existing link whose rect overlaps this hotspot
        for link in existing:
            link_rect = fitz.Rect(link.get("from"))
            if link_rect.intersects(click):
                try:
                    page.delete_link(link)
                except Exception:
                    pass

        page.insert_link({
            "kind": fitz.LINK_URI,
            "from": click,
            "uri": str(uri),
        })


def _flatten_groups(groups, font_mgr, width):
    lines = []
    for group in groups:
        heading = group.get("heading")
        if heading:
            wrapped_h = _wrap(font_mgr, heading, config.PACKAGE_TEXT_SIZE, False, width)
            for i, ln in enumerate(wrapped_h):
                lines.append(("heading" if i == 0 else "heading_cont", ln))
        for item_text in group.get("items", []):
            wrapped = _wrap(font_mgr, item_text, config.PACKAGE_TEXT_SIZE, False, width)
            for i, ln in enumerate(wrapped):
                lines.append(("item" if i == 0 else "item_cont", ln))
    return lines


def _flow_lines(page, col_cfg, lines, font_mgr, start_index=0):
    cursor_y = col_cfg["top_y"]
    fontname = font_mgr.font_name(False)
    fontfile = font_mgr.regular_path
    i = start_index
    while i < len(lines):
        # cursor_y is the baseline; allow drawing while baseline itself is in range
        if cursor_y > col_cfg["max_y"]:
            return i
        kind, text = lines[i]
        is_heading = kind in ("heading", "heading_cont")
        indent = 0 if is_heading else 7.4
        bullet_x = col_cfg["x"] + indent
        text_x = col_cfg["text_x"] + indent
        # Only the first line of a heading/item gets a bullet (matches template)
        if kind in ("heading", "item"):
            draw_text(page, (bullet_x, cursor_y), "\u2022", fontname, config.PACKAGE_TEXT_SIZE, fontfile=fontfile)
        draw_text(page, (text_x, cursor_y), text, fontname, config.PACKAGE_TEXT_SIZE, fontfile=fontfile)
        cursor_y += config.PACKAGE_ROW_PITCH
        i += 1
    return None


def _create_continuation_page(doc: "fitz.Document") -> "fitz.Page":
    """
    Insert a continuation page after Added Extras. Prefer a branded blank
    from assets/vessels-style overflow if present; otherwise a minimal header.
    """
    template_rect = doc[config.PAGE_BESPOKE_PACKAGE].rect
    insert_at = config.PAGE_ADDED_EXTRAS + 1

    branded = os_path_overflow()
    if branded:
        src = fitz.open(branded)
        try:
            doc.insert_pdf(src, from_page=0, to_page=0, start_at=insert_at)
            return doc[insert_at]
        finally:
            src.close()

    page = doc.new_page(insert_at, width=template_rect.width, height=template_rect.height)
    page.insert_text((22.7, 30), "YOUR BESPOKE PACKAGE (CONTINUED)", fontsize=14, color=(0.13, 0.13, 0.13))
    page.draw_line((22.7, 35), (template_rect.width - 22.7, 35), color=(0.94, 0.55, 0.2), width=1.2)
    return page


def os_path_overflow():
    import os
    path = os.path.join(config.BASE_DIR, "assets", "overflow_blank.pdf")
    return path if os.path.exists(path) else None


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
