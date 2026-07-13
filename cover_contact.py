"""
cover_contact.py
----------------
Handlers for Page 1 (cover) and Page 16 (contact / RM sign-off), plus
house-style formatters so payload values match the sample-proposal look.
"""

from datetime import datetime
import re

import fitz

import config
from pdf_ops import draw_field


_ORDINAL = {1: "st", 2: "nd", 3: "rd"}


def _ordinal(n: int) -> str:
    if 10 <= (n % 100) <= 20:
        return "th"
    return _ORDINAL.get(n % 10, "th")


def format_event_date(value: str) -> str:
    """
    Normalise to house style: 'Saturday 2nd June 2024'.
    Accepts ISO dates, already-formatted strings, or 'TBC'.
    """
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw or raw.upper() == "TBC":
        return "TBC"
    # Already looks like house style (contains a month name)
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
    """
    Normalise to '13:00hrs – 17:00hrs (TBC)' house style.
    """
    if value is None:
        return ""
    raw = str(value).strip()
    if not raw:
        return ""
    # Extract HH:MM pairs
    times = re.findall(r"(\d{1,2}:\d{2})", raw)
    if len(times) >= 2:
        start, end = times[0], times[1]
        # Zero-pad hours
        def norm(t):
            h, m = t.split(":")
            return f"{int(h):02d}:{m}"
        out = f"{norm(start)}hrs – {norm(end)}hrs"
    else:
        # Pass through but normalise hyphen/dash and ensure hrs markers if present as times
        out = raw.replace("-", "–").replace(" - ", " – ")
        out = re.sub(r"(\d{1,2}:\d{2})(?!\s*hrs)", r"\1hrs", out)
    has_tbc = bool(re.search(r"\(?\s*TBC\s*\)?", raw, re.I))
    if include_tbc and (has_tbc or include_tbc and "(TBC)" not in out):
        # Only append (TBC) when the source had it OR caller wants default TBC for proposals
        if has_tbc and "(TBC)" not in out:
            out = f"{out} (TBC)"
        elif has_tbc is False and include_tbc is True and "TBC" not in raw:
            # Don't force TBC if the payload didn't ask for it
            pass
    return out


def format_quote_date(value: str) -> str:
    """Normalise to '27 January 2026' (validity suffix is static in the template)."""
    if value is None:
        return ""
    raw = str(value).strip()
    # Strip trailing validity clause if the caller included it
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
    # Normalise separators to '40 - 60'
    m = re.match(r"(\d+)\s*[-–—to]+\s*(\d+)", raw, re.I)
    if m:
        return f"{m.group(1)} \u2013 {m.group(2)}"
    return raw


def normalize_cover_lead(lead: dict) -> dict:
    """Return a shallow copy of lead with cover fields house-formatted."""
    out = dict(lead)
    if "event_date" in out:
        out["event_date"] = format_event_date(out["event_date"])
    if "event_timings" in out:
        # Preserve (TBC) if present in original
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


def fill_cover_page(doc: "fitz.Document", data: dict, font_mgr, warnings: list):
    page = doc[config.PAGE_COVER]
    font_mgr.ensure_registered(page)
    data = normalize_cover_lead(data)
    for field_name, spec in config.COVER_FIELDS.items():
        if field_name not in data:
            continue
        draw_field(page, spec, str(data[field_name]), font_mgr, warnings, field_name)


def fill_contact_page(doc: "fitz.Document", data: dict, font_mgr, warnings: list):
    for field_name, spec in config.CONTACT_FIELDS.items():
        if field_name not in data:
            continue
        page = doc[spec["page"]]
        font_mgr.ensure_registered(page)
        value = str(data[field_name])
        # contact_email stores the address only; prefix "E: " is applied by draw_field
        if field_name == "contact_email":
            value = re.sub(r"^\s*E:\s*", "", value, flags=re.I)
        draw_field(page, spec, value, font_mgr, warnings, field_name)
