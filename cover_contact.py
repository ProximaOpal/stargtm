"""
cover_contact.py
----------------
Page 1 (cover) and contact/RM sign-off handlers, plus house-style formatters.
Uses batched redaction for speed and measured TemplateProfile geometry.
"""

from datetime import datetime
import re

import config
from pdf_ops import prepare_field_draw, draw_fields_batched


_ORDINAL = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        return "th"
    return _ORDINAL.get(n % 10, "th")


def format_event_date(value: str) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw or raw.upper() == "TBC":
        return "TBC"
    months = "January February March April May June July August September October November December"
    if any(m in raw for m in months.split()) and re.search(r"\d", raw):
        return raw
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(raw[:10], fmt)
            return f"{dt.strftime('%A')} {dt.day}{_ordinal(dt.day)} {dt.strftime('%B %Y')}"
        except ValueError:
            continue
    return raw


def format_event_date_compact(value: str) -> str:
    """Shorter house style when the full weekday date won't fit the panel."""
    raw = format_event_date(value)
    if raw in ("", "TBC"):
        return raw
    # Try parse back from house style or ISO
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(str(value).strip()[:10], fmt)
            return f"{dt.strftime('%a')} {dt.day}{_ordinal(dt.day)} {dt.strftime('%b %Y')}"
        except ValueError:
            continue
    # From already-formatted long date: Tuesday 14th July 2026 -> Tue 14th Jul 2026
    m = re.match(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)\s+(\d{1,2})(st|nd|rd|th)\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        raw,
    )
    if m:
        day_map = {
            "Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu",
            "Friday": "Fri", "Saturday": "Sat", "Sunday": "Sun",
        }
        mon_map = {
            "January": "Jan", "February": "Feb", "March": "Mar", "April": "Apr",
            "May": "May", "June": "Jun", "July": "Jul", "August": "Aug",
            "September": "Sep", "October": "Oct", "November": "Nov", "December": "Dec",
        }
        return f"{day_map[m.group(1)]} {m.group(2)}{m.group(3)} {mon_map[m.group(4)]} {m.group(5)}"
    return raw


def format_event_timings(value: str, *, include_tbc: bool = True) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    times = re.findall(r"(\d{1,2}:\d{2})", raw)
    if len(times) >= 2:
        def norm(t):
            h, m = t.split(":")
            return f"{int(h):02d}:{m}"
        out = f"{norm(times[0])}hrs – {norm(times[1])}hrs"
    else:
        out = raw.replace("-", "–").replace(" - ", " – ")
        out = re.sub(r"(\d{1,2}:\d{2})(?!\s*hrs)", r"\1hrs", out)
    has_tbc = bool(re.search(r"\(?\s*TBC\s*\)?", raw, re.I))
    if has_tbc and "(TBC)" not in out:
        out = f"{out} (TBC)"
    return out


def format_quote_date(value: str) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    raw = re.split(r"\s*\|\s*Quotation valid", raw, maxsplit=1)[0].strip()
    months = "January February March April May June July August September October November December"
    if any(m in raw for m in months.split()):
        return raw
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            dt = datetime.strptime(raw[:10], fmt)
            return f"{dt.day} {dt.strftime('%B %Y')}"
        except ValueError:
            continue
    return raw


def format_guest_range(value) -> str:
    if value is None:
        return ""
    raw = str(value).strip()
    m = re.match(r"(\d+)\s*[-–—to]+\s*(\d+)", raw, re.I)
    if m:
        return f"{m.group(1)} \u2013 {m.group(2)}"
    return raw


def normalize_cover_lead(lead: dict) -> dict:
    out = dict(lead)
    if "event_date" in out:
        out["event_date"] = format_event_date(out["event_date"])
    if "event_timings" in out:
        original = str(lead.get("event_timings", ""))
        formatted = format_event_timings(original, include_tbc=False)
        if re.search(r"TBC", original, re.I) and "(TBC)" not in formatted:
            formatted = f"{formatted} (TBC)"
        out["event_timings"] = formatted
    if "quote_date" in out:
        out["quote_date"] = format_quote_date(out["quote_date"])
    if "guest_range" in out:
        out["guest_range"] = format_guest_range(out["guest_range"])
    if "guest_quote_n" in out:
        out["guest_quote_n"] = str(out["guest_quote_n"]).strip()
    return out


def fill_cover_page(doc, data: dict, font_mgr, warnings: list, profile=None):
    page_index = profile.page_cover if profile else config.PAGE_COVER
    fields = profile.cover_fields if profile and profile.cover_fields else config.COVER_FIELDS
    page = doc[page_index]
    font_mgr.ensure_registered(page)
    data = normalize_cover_lead(data)

    prepared = []
    for field_name, spec in fields.items():
        if field_name not in data or not spec:
            continue
        value = str(data[field_name])
        # If event_date won't fit at designed size, use compact form before shrink
        if field_name == "event_date":
            max_w = spec.get("max_width", 56)
            if font_mgr.text_length(value, spec["size"], spec.get("bold", False)) > max_w:
                value = format_event_date_compact(data[field_name])
        # Page 1 must stay pixel-perfect with the chosen template: measured
        # span colour + Century Gothic only. Page-13 pure-white / Fallback-Bold
        # styling must not leak onto the cover.
        spec = dict(spec)
        spec["color"] = _cover_ink_from_template(spec.get("color"))
        # Keep brand CG on cover even for "bold" fields (template-extracted CG
        # Bold subsets can't re-embed; Fallback Bold reads as a different face).
        want_weight = bool(spec.get("bold"))
        spec["bold"] = False
        spec["deep_bold"] = want_weight  # light echo approximates template bold
        prepared.append(prepare_field_draw(spec, value, font_mgr, warnings, field_name))

    draw_fields_batched(page, prepared, font_mgr, clear_graphics=False)


def _cover_ink_from_template(color) -> tuple:
    """
    Cover ink must match the template PDF, not Page-13 pure white.

    Catalog templates store panel copy as RGB(230,242,243). Re-inserting with
    that exact triplet keeps edited values identical to static labels.
    """
    if color and isinstance(color, (tuple, list)) and len(color) >= 3:
        return (float(color[0]), float(color[1]), float(color[2]))
    # Same triplet measured from assets/templates/catalog/**/template.pdf covers
    return (230 / 255, 242 / 255, 243 / 255)


def fill_contact_page(doc, data: dict, font_mgr, warnings: list, profile=None):
    fields = profile.contact_fields if profile and profile.contact_fields else config.CONTACT_FIELDS
    # Group by page for batched apply
    by_page: dict[int, list] = {}
    for field_name, spec in fields.items():
        if field_name not in data or not spec:
            continue
        page_i = spec.get("page", profile.page_contact if profile else config.PAGE_CONTACT)
        value = str(data[field_name])
        if field_name == "contact_email":
            value = re.sub(r"^\s*E:\s*", "", value, flags=re.I)
        page = doc[page_i]
        font_mgr.ensure_registered(page)
        item = prepare_field_draw(spec, value, font_mgr, warnings, field_name)
        by_page.setdefault(page_i, []).append(item)

    for page_i, items in by_page.items():
        draw_fields_batched(doc[page_i], items, font_mgr, clear_graphics=False)
