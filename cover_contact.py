"""
cover_contact.py
----------------
Page 1 (cover) and contact/RM sign-off handlers, plus house-style formatters.
Field geometry comes from a measured TemplateProfile when provided.
"""

from datetime import datetime
import re

import config
from pdf_ops import draw_field


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
    for field_name, spec in fields.items():
        if field_name not in data or not spec:
            continue
        draw_field(page, spec, str(data[field_name]), font_mgr, warnings, field_name)


def fill_contact_page(doc, data: dict, font_mgr, warnings: list, profile=None):
    fields = profile.contact_fields if profile and profile.contact_fields else config.CONTACT_FIELDS
    for field_name, spec in fields.items():
        if field_name not in data or not spec:
            continue
        page = doc[spec.get("page", profile.page_contact if profile else config.PAGE_CONTACT)]
        font_mgr.ensure_registered(page)
        value = str(data[field_name])
        if field_name == "contact_email":
            value = re.sub(r"^\s*E:\s*", "", value, flags=re.I)
        draw_field(page, spec, value, font_mgr, warnings, field_name)
