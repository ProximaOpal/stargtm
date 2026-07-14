"""
measure.py
----------
Dynamically measure editable field geometry from any WEOTT proposal template.
Slight bbox drift between Corporate/Wedding variants is absorbed here so the
engine does not need one hardcoded config per PDF.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import fitz


@dataclass
class TemplateProfile:
    path: str
    pages: int
    page_cover: int = 0
    page_vessel: Optional[int] = None
    page_bespoke: Optional[int] = None
    page_extras: Optional[int] = None
    page_contact: Optional[int] = None
    cover_fields: dict = field(default_factory=dict)
    contact_fields: dict = field(default_factory=dict)
    financial_fields: dict = field(default_factory=dict)
    upgrade_list: dict = field(default_factory=dict)
    package_columns: list = field(default_factory=list)
    package_clear_zone: tuple = (22.0, 156.0, 360.0, 263.8)
    menu_link_targets: dict = field(default_factory=dict)


def _spans(page):
    rows = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for sp in line["spans"]:
                rows.append(sp)
    return rows


def _find_title_page(doc, *needles, min_size=12):
    for i in range(doc.page_count):
        for sp in _spans(doc[i]):
            text = sp["text"].strip().upper()
            if sp["size"] >= min_size and any(n.upper() in text for n in needles):
                # Prefer real titles near the top of the page
                if sp["bbox"][1] < 100:
                    return i
    for i in range(doc.page_count):
        for sp in _spans(doc[i]):
            text = sp["text"].strip().upper()
            if sp["size"] >= min_size and any(n.upper() in text for n in needles):
                return i
    return None


def _value_after_label(spans, label_substr, *, value_same_line=True):
    """
    Locate the editable value span that follows a label such as
    'Event type |' or 'Prepared by '.
    Returns (bbox, origin, size, bold_hint) or None.
    """
    label_substr_l = label_substr.lower()
    for i, sp in enumerate(spans):
        text = sp["text"]
        if label_substr_l not in text.lower():
            continue

        # Case A: label ends with '|', value is the next span on similar y
        if "|" in text and text.strip().endswith("|"):
            if i + 1 < len(spans):
                nxt = spans[i + 1]
                if abs(nxt["bbox"][1] - sp["bbox"][1]) < 4:
                    return _span_field(nxt)

        # Case B: 'Prepared by NAME' — name is next span
        if label_substr_l.startswith("prepared by") and text.strip().lower().endswith("prepared by"):
            if i + 1 < len(spans):
                return _span_field(spans[i + 1])

        # Case C: combined 'Label | value' in one span — redact only the value portion
        if "|" in text:
            left, right = text.split("|", 1)
            if right.strip():
                # Approximate value bbox as the right side of this span
                full = fitz.Rect(sp["bbox"])
                # Split proportionally by character count (good enough for redact)
                ratio = len(left) / max(len(text), 1)
                x0 = full.x0 + full.width * ratio
                bbox = (round(x0, 1), round(full.y0, 1), round(full.x1 + 20, 1), round(full.y1, 1))
                origin = (round(x0, 1), round(sp["origin"][1], 1))
                bold = "Bold" in sp["font"] or "bold" in sp["font"].lower()
                return dict(bbox=bbox, origin=origin, size=round(sp["size"], 2), bold=bold)

        # Case D: bare label, next span is value
        if i + 1 < len(spans) and abs(spans[i + 1]["bbox"][1] - sp["bbox"][1]) < 4:
            return _span_field(spans[i + 1])
    return None


def _span_field(sp):
    bbox = tuple(round(x, 1) for x in sp["bbox"])
    # Widen bbox to the right so longer replacement values fit / clear leftovers
    bbox = (bbox[0], bbox[1], max(bbox[2] + 25, bbox[0] + 40), bbox[3])
    origin = (round(sp["origin"][0], 1), round(sp["origin"][1], 1))
    bold = "Bold" in sp["font"] or "bold" in sp["font"].lower()
    return dict(bbox=bbox, origin=origin, size=round(sp["size"], 2), bold=bold)


def _find_date_span(spans):
    """Find the quote-date span (e.g. '27 January 2026') before '| Quotation valid'."""
    for i, sp in enumerate(spans):
        if "quotation valid" in sp["text"].lower():
            # previous span on same line is often the date, or same span before |
            if "|" in sp["text"]:
                left = sp["text"].split("|", 1)[0]
                if any(ch.isdigit() for ch in left):
                    return _span_field(sp)
            if i > 0 and abs(spans[i - 1]["bbox"][1] - sp["bbox"][1]) < 4:
                return _span_field(spans[i - 1])
        # standalone date-like span near prepared-by block
        t = sp["text"].strip()
        months = ("January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December")
        if any(m in t for m in months) and any(ch.isdigit() for ch in t) and "valid" not in t.lower():
            if sp["bbox"][0] > 200:  # cover right/left info panels
                return _span_field(sp)
    return None


def _guest_quote_n(spans):
    """The bold number in 'Quote based on a group of up to N guests'."""
    for i, sp in enumerate(spans):
        if "quote based on a group of up to" in sp["text"].lower():
            if i + 1 < len(spans) and spans[i + 1]["text"].strip().isdigit():
                return _span_field(spans[i + 1])
        # number may be embedded: '... up to 40 guests'
        if "up to" in sp["text"].lower() and "guest" in sp["text"].lower():
            import re
            m = re.search(r"up to\s+(\d+)\s+guests?", sp["text"], re.I)
            if m:
                # tight bbox around the digits — approximate mid-span
                return _span_field(sp)
    # fallback: look for short numeric span near guests line
    for i, sp in enumerate(spans):
        if sp["text"].strip().isdigit() and len(sp["text"].strip()) <= 3:
            if i > 0 and "up to" in spans[i - 1]["text"].lower():
                field = _span_field(sp)
                field["bold"] = True
                field["max_width"] = 8.0
                return field
    return None


def measure_cover(page) -> dict:
    spans = _spans(page)
    fields = {}

    # --- Standard label → value fields ---
    # "No. of guests" is often split across spans ("No. " / "o" / "f guests |")
    label_map = {
        "proposal_ref": ["Proposal/Quotation Ref"],
        "client_name": ["Client Name"],
        "organisation": ["Organisation"],
        "telephone": ["Telephone"],
        "email": ["Email"],
        "event_type": ["Event type"],
        "event_date": ["Event date requested"],
        "event_timings": ["Event timings"],
        "guest_range": ["No. of guests", "f guests |", "guests |"],
    }
    for key, labels in label_map.items():
        for label in labels:
            found = _value_after_label(spans, label)
            if found:
                fields[key] = found
                break

    # Prepared by — handle both split and combined spans
    for i, sp in enumerate(spans):
        text = sp["text"]
        low = text.lower()
        if "prepared by" not in low:
            continue

        # Combined: 'Prepared by Katherine Bulaon |'
        if "prepared by" in low and "|" in text:
            import re as _re
            m = _re.search(r"prepared by\s+(.+?)\s*\|", text, _re.I)
            if m:
                name = m.group(1).strip()
                # Approximate value bbox: from after 'Prepared by ' to before '|'
                full = fitz.Rect(sp["bbox"])
                pre = "Prepared by "
                ratio0 = len(pre) / max(len(text), 1)
                ratio1 = text.lower().find("|") / max(len(text), 1)
                if ratio1 <= 0:
                    ratio1 = 1.0
                x0 = full.x0 + full.width * ratio0
                x1 = full.x0 + full.width * ratio1
                fields["prepared_by"] = dict(
                    bbox=(round(x0, 1), round(full.y0, 1), round(x1 + 5, 1), round(full.y1, 1)),
                    origin=(round(x0, 1), round(sp["origin"][1], 1)),
                    size=round(sp["size"], 2),
                    bold=True,
                )
                break
        # Split: 'Prepared by ' + 'Katherine Bulaon' + ' |'
        if text.strip().lower() in ("prepared by", "prepared by "):
            for j in range(i + 1, min(i + 4, len(spans))):
                cand = spans[j]
                t = cand["text"].strip()
                if t.startswith("|") or t.lower().startswith("client") or t.lower().startswith("relationship"):
                    continue
                # skip dates
                months = ("January", "February", "March", "April", "May", "June",
                          "July", "August", "September", "October", "November", "December")
                if any(m in t for m in months):
                    continue
                if len(t) >= 4:
                    f = _span_field(cand)
                    f["bold"] = True
                    fields["prepared_by"] = f
                    break
            break

    # Quote date: left panel date near prepared-by, NOT the event date on the right
    for i, sp in enumerate(spans):
        t = sp["text"].strip()
        months = ("January", "February", "March", "April", "May", "June",
                  "July", "August", "September", "October", "November", "December")
        if any(m in t for m in months) and any(ch.isdigit() for ch in t):
            # left info panel
            if 220 < sp["bbox"][0] < 340 and "valid" not in t.lower() and "requested" not in t.lower():
                # exclude weekday event dates like 'Saturday 2nd June...'
                weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
                if any(t.startswith(d) for d in weekdays):
                    continue
                f = _span_field(sp)
                f["bold"] = True
                fields["quote_date"] = f
                break
    # Fallback: span immediately before '| Quotation valid'
    if "quote_date" not in fields:
        for i, sp in enumerate(spans):
            if "quotation valid" in sp["text"].lower() and i > 0:
                prev = spans[i - 1]
                if abs(prev["bbox"][1] - sp["bbox"][1]) < 4:
                    f = _span_field(prev)
                    f["bold"] = True
                    fields["quote_date"] = f
                    break

    gqn = _guest_quote_n(spans)
    if gqn:
        gqn["bold"] = True
        gqn["max_width"] = gqn.get("max_width", 8.0)
        fields["guest_quote_n"] = gqn

    return fields


def measure_contact(page, page_index: int) -> dict:
    spans = _spans(page)
    fields = {}

    # Name under "Kind regards,"
    for i, sp in enumerate(spans):
        if "kind regards" in sp["text"].lower():
            # next non-empty content-ish span with larger/bold text
            for j in range(i + 1, min(i + 6, len(spans))):
                cand = spans[j]
                if cand["size"] >= 4.5 and len(cand["text"].strip()) > 3 and "promise" not in cand["text"].lower():
                    f = _span_field(cand)
                    f["bold"] = True
                    f["page"] = page_index
                    f["size"] = round(cand["size"], 2)
                    fields["contact_name"] = f
                    # title often follows
                    if j + 1 < len(spans):
                        title = spans[j + 1]
                        if "manager" in title["text"].lower() or "relationship" in title["text"].lower():
                            tf = _span_field(title)
                            tf["bold"] = True
                            tf["page"] = page_index
                            # orange-ish title colour used in template
                            tf["color"] = (0.89, 0.51, 0.21)
                            fields["contact_title"] = tf
                    break
            break

    # Phone after 'T:'
    for i, sp in enumerate(spans):
        if sp["text"].strip() in ("T:", "T: ") or sp["text"].strip().startswith("T:"):
            if sp["text"].strip() in ("T:", "T: ") and i + 1 < len(spans):
                f = _span_field(spans[i + 1])
                f["page"] = page_index
                fields["contact_phone"] = f
            break

    # Email: clear from 'E:' through domain
    for i, sp in enumerate(spans):
        if sp["text"].strip().startswith("E:"):
            # gather until end of email cluster
            x0 = sp["bbox"][0]
            y0 = sp["bbox"][1]
            x1 = sp["bbox"][2]
            y1 = sp["bbox"][3]
            for j in range(i, min(i + 4, len(spans))):
                if abs(spans[j]["bbox"][1] - y0) < 5:
                    x1 = max(x1, spans[j]["bbox"][2])
                    y1 = max(y1, spans[j]["bbox"][3])
            fields["contact_email"] = dict(
                bbox=(round(x0, 1), round(y0, 1), round(x1 + 10, 1), round(y1, 1)),
                origin=(round(x0, 1), round(sp["origin"][1], 1)),
                size=round(sp["size"], 2),
                bold=False,
                page=page_index,
                prefix="E: ",
            )
            break

    return fields


def measure_financials(page) -> dict:
    """
    Locate white numbers inside the orange finance table by finding spans
    that look like money / guest counts near 'No.Guests' / 'VAT' / 'Grand Total'.
    Falls back to the known Summer-Event geometry when detection is thin.
    """
    spans = _spans(page)
    # Defaults from the measured Summer Event template (works for most variants)
    defaults = {
        "pkg_guests": dict(bbox=(115, 89.5, 135, 95.5), size=4.16, bold=True, align="center", color=(1, 1, 1)),
        "pkg_cost": dict(bbox=(195, 89.5, 226, 95.5), size=4.16, bold=True, align="right", right_x=225.9, y=94.7, color=(1, 1, 1)),
        "pkg_vat": dict(bbox=(195, 119.9, 226, 125.8), size=4.16, bold=True, align="right", right_x=225.4, y=125.1, color=(1, 1, 1)),
        "pkg_total": dict(bbox=(195, 130.5, 226, 136.4), size=4.16, bold=True, align="right", right_x=225.3, y=135.7, color=(1, 1, 1)),
    }

    # Try to snap cost cells to actual white-ish numeric spans in the upper-left quadrant
    money_spans = []
    for sp in spans:
        t = sp["text"].strip().replace(",", "")
        if sp["bbox"][0] < 240 and sp["bbox"][1] < 150:
            try:
                float(t)
                money_spans.append(sp)
            except ValueError:
                continue

    if len(money_spans) >= 3:
        # Sort by y then x
        money_spans.sort(key=lambda s: (round(s["bbox"][1], 0), s["bbox"][0]))
        # Heuristic: first short int near centre = guests; right-aligned moneys = cost/vat/total
        guests = [s for s in money_spans if s["bbox"][0] < 160]
        prices = [s for s in money_spans if s["bbox"][0] >= 160]
        if guests:
            g = guests[0]
            defaults["pkg_guests"] = dict(
                bbox=(g["bbox"][0] - 5, g["bbox"][1] - 1, g["bbox"][2] + 5, g["bbox"][3] + 1),
                size=round(g["size"], 2), bold=True, align="center", color=(1, 1, 1),
                origin=(round(g["origin"][0], 1), round(g["origin"][1], 1)),
            )
        if len(prices) >= 3:
            for key, sp in zip(("pkg_cost", "pkg_vat", "pkg_total"), prices[:3]):
                defaults[key] = dict(
                    bbox=(sp["bbox"][0] - 8, sp["bbox"][1] - 1, sp["bbox"][2] + 2, sp["bbox"][3] + 1),
                    size=round(sp["size"], 2), bold=True, align="right",
                    right_x=round(sp["bbox"][2], 1), y=round(sp["origin"][1], 1), color=(1, 1, 1),
                )
        elif len(prices) == 1:
            # only package cost visible as a number sometimes
            sp = prices[0]
            defaults["pkg_cost"] = dict(
                bbox=(sp["bbox"][0] - 8, sp["bbox"][1] - 1, sp["bbox"][2] + 2, sp["bbox"][3] + 1),
                size=round(sp["size"], 2), bold=True, align="right",
                right_x=round(sp["bbox"][2], 1), y=round(sp["origin"][1], 1), color=(1, 1, 1),
            )

    return defaults


def measure_upgrade_list(page, page_index: int) -> dict:
    spans = _spans(page)
    # Find "Consider upgrading" then first bullet below it
    header_y = None
    for sp in spans:
        if "consider upgrading" in sp["text"].lower():
            header_y = sp["bbox"][3]
            break

    bullets = []
    for sp in spans:
        if header_y is not None and sp["bbox"][1] > header_y and sp["bbox"][0] > 350:
            if sp["text"].strip() in ("•", "\u2022") or (
                len(sp["text"].strip()) > 8 and sp["bbox"][0] > 360
            ):
                bullets.append(sp)

    # Fallback geometry (Summer Event)
    cfg = dict(
        page=page_index,
        clear_zone=(365, 88, 481, 240),
        bullet_x=369.6,
        text_x=375.3,
        first_baseline_y=97.2,
        row_pitch=8.4,
        bullet_size=4.0,
        text_size=4.7,
        max_width=105,
        bold=False,
    )

    text_spans = [s for s in spans if s["bbox"][0] > 360 and s["bbox"][1] > (header_y or 85) and len(s["text"].strip()) > 5]
    text_spans.sort(key=lambda s: s["bbox"][1])
    if len(text_spans) >= 2:
        cfg["text_x"] = round(text_spans[0]["bbox"][0], 1)
        cfg["first_baseline_y"] = round(text_spans[0]["origin"][1], 1)
        cfg["row_pitch"] = round(text_spans[1]["origin"][1] - text_spans[0]["origin"][1], 1) or 8.4
        cfg["text_size"] = round(text_spans[0]["size"], 2)
        cfg["clear_zone"] = (
            360,
            round((header_y or 85) + 2, 1),
            500,
            round(text_spans[-1]["bbox"][3] + 8, 1),
        )
        cfg["bullet_x"] = cfg["text_x"] - 5.7

    return cfg


def measure_package_columns(page) -> tuple:
    """Return (columns, clear_zone) with defaults tuned for the shared layout."""
    columns = [
        dict(name="venue_and_management", x=24.2, text_x=28.6, top_y=164.2, max_y=263.5, width=100),
        dict(name="entertainment_and_decor", x=130.3, text_x=134.7, top_y=164.1, max_y=263.5, width=98),
        dict(name="stationery_and_catering", x=249.0, text_x=254.5, top_y=164.0, max_y=263.5, width=98),
    ]
    clear_zone = (22.0, 156.0, 360.0, 263.8)

    # Snap top_y to first package bullet below the intro paragraph if detectable
    spans = _spans(page)
    for sp in spans:
        if sp["text"].strip() in ("•", "\u2022") and 20 < sp["bbox"][0] < 40 and sp["bbox"][1] > 150:
            y = round(sp["origin"][1], 1)
            for col in columns:
                col["top_y"] = y
            clear_zone = (22.0, y - 8, 360.0, 263.8)
            break

    return columns, clear_zone


def measure_menu_links(page) -> dict:
    targets = {}
    spans = _spans(page)
    for sp in spans:
        if sp["text"].strip().lower() == "click here":
            bbox = tuple(round(x, 1) for x in sp["bbox"])
            # classify by x position
            if sp["bbox"][0] < 200:
                targets["mood_board"] = dict(click_bbox=bbox)
            elif sp["bbox"][0] < 360:
                targets["food_menu"] = dict(click_bbox=bbox)
            else:
                targets["street_food_menu"] = dict(click_bbox=bbox)
    # ensure keys exist with defaults
    targets.setdefault("food_menu", dict(click_bbox=(310.9, 242.7, 332.9, 249.1)))
    targets.setdefault("mood_board", dict(click_bbox=(131.2, 264.1, 153.9, 270.5)))
    targets.setdefault("street_food_menu", dict(click_bbox=(413.9, 113.4, 435.9, 119.8)))
    return targets


def measure_template(template_path: str) -> TemplateProfile:
    doc = fitz.open(template_path)
    try:
        page_bespoke = _find_title_page(doc, "YOUR BESPOKE PACKAGE")
        page_contact = _find_title_page(doc, "YOUR CONTACT")
        page_vessel = _find_title_page(doc, "VESSEL DETAILS", "VESSEL")
        page_extras = _find_title_page(doc, "ADDED EXTRAS")

        # Fallbacks matching the dominant layout
        if page_bespoke is None:
            page_bespoke = 12 if doc.page_count > 12 else doc.page_count - 5
        if page_contact is None:
            page_contact = 15 if doc.page_count > 15 else doc.page_count - 2
        if page_extras is None:
            page_extras = page_bespoke + 1 if page_bespoke + 1 < doc.page_count else page_bespoke
        if page_vessel is None:
            page_vessel = 8 if doc.page_count > 8 else None

        cover_fields = measure_cover(doc[0])
        contact_fields = measure_contact(doc[page_contact], page_contact) if page_contact is not None else {}
        financial_fields = measure_financials(doc[page_bespoke])
        upgrade_list = measure_upgrade_list(doc[page_bespoke], page_bespoke)
        package_columns, package_clear = measure_package_columns(doc[page_bespoke])
        menu_links = measure_menu_links(doc[page_bespoke])

        return TemplateProfile(
            path=template_path,
            pages=doc.page_count,
            page_cover=0,
            page_vessel=page_vessel,
            page_bespoke=page_bespoke,
            page_extras=page_extras,
            page_contact=page_contact,
            cover_fields=cover_fields,
            contact_fields=contact_fields,
            financial_fields=financial_fields,
            upgrade_list=upgrade_list,
            package_columns=package_columns,
            package_clear_zone=package_clear,
            menu_link_targets=menu_links,
        )
    finally:
        doc.close()


# Simple in-process cache
_PROFILE_CACHE: dict[str, TemplateProfile] = {}


def get_profile(template_path: str, *, force: bool = False) -> TemplateProfile:
    key = str(template_path)
    if force or key not in _PROFILE_CACHE:
        _PROFILE_CACHE[key] = measure_template(key)
    return _PROFILE_CACHE[key]


def clear_profile_cache():
    _PROFILE_CACHE.clear()
