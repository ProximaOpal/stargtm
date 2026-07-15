"""
measure.py
----------
Dynamically measure editable field geometry from any WEOTT proposal template.
Slight bbox drift between Corporate/Wedding variants is absorbed here so the
engine does not need one hardcoded config per PDF.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz

import config


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


def _span_color(sp) -> tuple:
    """Convert a PyMuPDF span color (int or sequence) to an RGB float tuple."""
    c = sp.get("color", 0xFFFFFF)
    if isinstance(c, (tuple, list)) and len(c) >= 3:
        vals = tuple(float(x) for x in c[:3])
        # Already 0..1 floats, or 0..255 ints
        if max(vals) > 1.0:
            return tuple(v / 255.0 for v in vals)
        return vals
    try:
        c = int(c)
    except (TypeError, ValueError):
        return (1.0, 1.0, 1.0)
    return (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0)


def _span_field(sp, next_sp=None, widen=2.0, max_x1=None):
    """
    Build a redact/draw field from a value span.

    Never expand into the next sibling span on the same line — cap x1 at
    next_sp.bbox[0] - 0.6 when next_sp is provided. Also respect max_x1
    (panel right edge) and set max_width from the available width.
    """
    x0, y0, x1, y1 = sp["bbox"]
    x1 = x1 + widen

    if next_sp is not None:
        cap = next_sp["bbox"][0] - 0.6
        if cap > x0:
            x1 = min(x1, cap)

    if max_x1 is not None and max_x1 > x0:
        x1 = min(x1, max_x1)

    # Ensure a usable minimum width without crossing caps already applied
    min_x1 = x0 + 8.0
    if next_sp is not None:
        min_x1 = min(min_x1, next_sp["bbox"][0] - 0.6)
    if max_x1 is not None:
        min_x1 = min(min_x1, max_x1)
    if min_x1 > x0:
        x1 = max(x1, min_x1)

    bbox = (round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1))
    origin = (round(sp["origin"][0], 1), round(sp["origin"][1], 1))
    bold = "Bold" in sp["font"] or "bold" in sp["font"].lower()
    max_width = round(max(bbox[2] - bbox[0], 1.0), 1)
    return dict(
        bbox=bbox,
        origin=origin,
        size=round(sp["size"], 2),
        bold=bold,
        max_width=max_width,
        color=_span_color(sp),
    )


def _next_same_line(spans, i):
    """Return the next span on the same line as spans[i], or None."""
    if i + 1 >= len(spans):
        return None
    nxt = spans[i + 1]
    if abs(nxt["bbox"][1] - spans[i]["bbox"][1]) < 4:
        return nxt
    return None


def _value_after_label(spans, label_substr, *, value_same_line=True, panel_right=None):
    """
    Locate the editable value span that follows a label such as
    'Event type |' or 'Prepared by '.
    Returns (bbox, origin, size, bold_hint) or None.

    When panel_right is set it is used as max_x1 so values stay inside the
    left (338) or right (467) cover panel.
    """
    label_substr_l = label_substr.lower()
    for i, sp in enumerate(spans):
        text = sp["text"]
        if label_substr_l not in text.lower():
            continue

        # Case A: label ends with '|', value is the next span on similar y
        if "|" in text and text.strip().endswith("|"):
            nxt = _next_same_line(spans, i)
            if nxt is not None:
                nxt2 = _next_same_line(spans, i + 1)
                return _span_field(nxt, next_sp=nxt2, max_x1=panel_right)

        # Case B: 'Prepared by NAME' — name is next span
        if label_substr_l.startswith("prepared by") and text.strip().lower().endswith("prepared by"):
            if i + 1 < len(spans):
                nxt2 = _next_same_line(spans, i + 1)
                return _span_field(spans[i + 1], next_sp=nxt2, max_x1=panel_right)

        # Case C: combined 'Label | value' in one span — redact only the value portion
        if "|" in text:
            left, right = text.split("|", 1)
            if right.strip():
                full = fitz.Rect(sp["bbox"])
                ratio = len(left) / max(len(text), 1)
                x0 = full.x0 + full.width * ratio
                x1 = full.x1 + 2.0
                nxt = _next_same_line(spans, i)
                if nxt is not None:
                    x1 = min(x1, nxt["bbox"][0] - 0.6)
                if panel_right is not None:
                    x1 = min(x1, panel_right)
                bbox = (round(x0, 1), round(full.y0, 1), round(x1, 1), round(full.y1, 1))
                origin = (round(x0, 1), round(sp["origin"][1], 1))
                bold = "Bold" in sp["font"] or "bold" in sp["font"].lower()
                return dict(
                    bbox=bbox,
                    origin=origin,
                    size=round(sp["size"], 2),
                    bold=bold,
                    max_width=round(max(bbox[2] - bbox[0], 1.0), 1),
                    color=_span_color(sp),
                )

        # Case D: bare label, next span is value
        nxt = _next_same_line(spans, i)
        if nxt is not None:
            nxt2 = _next_same_line(spans, i + 1)
            return _span_field(nxt, next_sp=nxt2, max_x1=panel_right)
    return None


def _guest_quote_n(spans):
    """Bold guest count; redacts N + ' guests' and redraws both so 3-digit counts fit."""
    for i, sp in enumerate(spans):
        if "quote based on a group of up to" in sp["text"].lower():
            if i + 1 < len(spans) and spans[i + 1]["text"].strip().isdigit():
                return _guest_quote_field(spans[i + 1], spans[i + 2] if i + 2 < len(spans) else None)
        if "up to" in sp["text"].lower() and "guest" in sp["text"].lower():
            m = re.search(r"up to\s+(\d+)\s+guests?", sp["text"], re.I)
            if m:
                return _span_field(sp, widen=0.5)
    for i, sp in enumerate(spans):
        if sp["text"].strip().isdigit() and len(sp["text"].strip()) <= 3:
            if i > 0 and "up to" in spans[i - 1]["text"].lower():
                return _guest_quote_field(sp, spans[i + 1] if i + 1 < len(spans) else None)
    return None


def _guest_quote_field(num_sp, guests_sp):
    """
    Cover the digit span plus the following ' guests' word so wider numbers
    (e.g. 230) never clip the leading 'g'. Draw path re-inserts the suffix.
    """
    x0, y0, x1, y1 = num_sp["bbox"]
    suffix = " guests"
    if guests_sp and "guest" in guests_sp["text"].lower():
        x1 = guests_sp["bbox"][2]
        y0 = min(y0, guests_sp["bbox"][1])
        y1 = max(y1, guests_sp["bbox"][3])
        suffix = guests_sp["text"] if guests_sp["text"].startswith(" ") else f" {guests_sp['text'].lstrip()}"
    # Digits may use up to ~11pt before the suffix is drawn after them
    digit_w = 11.0
    return dict(
        bbox=(round(x0 - 0.3, 1), round(y0 - 0.2, 1), round(x1 + 0.3, 1), round(y1 + 0.2, 1)),
        origin=(round(num_sp["origin"][0], 1), round(num_sp["origin"][1], 1)),
        size=round(num_sp["size"], 2),
        bold=True,
        max_width=digit_w,
        suffix=suffix,
        suffix_bold=False,
        color=_span_color(num_sp),
    )


def measure_cover(page) -> dict:
    spans = _spans(page)
    fields = {}
    RIGHT_PANEL = 467.0
    LEFT_PANEL = 338.0

    # "No. of guests" is often split across spans ("No. " / "o" / "f guests |")
    label_map = {
        "proposal_ref": (["Proposal/Quotation Ref"], LEFT_PANEL),
        "client_name": (["Client Name"], LEFT_PANEL),
        "organisation": (["Organisation"], LEFT_PANEL),
        "telephone": (["Telephone"], LEFT_PANEL),
        "email": (["Email"], LEFT_PANEL),
        "event_type": (["Event type"], RIGHT_PANEL),
        "event_date": (["Event date requested"], RIGHT_PANEL),
        "event_timings": (["Event timings"], RIGHT_PANEL),
        "guest_range": (["No. of guests", "f guests |", "guests |"], RIGHT_PANEL),
    }
    for key, (labels, panel) in label_map.items():
        for label in labels:
            found = _value_after_label(spans, label, panel_right=panel)
            if found:
                fields[key] = found
                break

    # Prepared by — handle both split and combined spans; don't collide with quote_date
    for i, sp in enumerate(spans):
        text = sp["text"]
        low = text.lower()
        if "prepared by" not in low:
            continue

        # Combined: 'Prepared by Katherine Bulaon |'
        if "|" in text:
            m = re.search(r"prepared by\s+(.+?)\s*\|", text, re.I)
            if m:
                full = fitz.Rect(sp["bbox"])
                pre = "Prepared by "
                ratio0 = len(pre) / max(len(text), 1)
                ratio1 = text.lower().find("|") / max(len(text), 1)
                if ratio1 <= 0:
                    ratio1 = 1.0
                x0 = full.x0 + full.width * ratio0
                x1 = full.x0 + full.width * ratio1
                if LEFT_PANEL > x0:
                    x1 = min(x1, LEFT_PANEL)
                fields["prepared_by"] = dict(
                    bbox=(round(x0, 1), round(full.y0, 1), round(x1, 1), round(full.y1, 1)),
                    origin=(round(x0, 1), round(sp["origin"][1], 1)),
                    size=round(sp["size"], 2),
                    bold=True,
                    max_width=round(max(x1 - x0, 1.0), 1),
                    color=_span_color(sp),
                )
                break

        # Split: 'Prepared by ' + 'Katherine Bulaon' + ' |'
        if text.strip().lower() in ("prepared by", "prepared by "):
            months = (
                "January", "February", "March", "April", "May", "June",
                "July", "August", "September", "October", "November", "December",
            )
            for j in range(i + 1, min(i + 4, len(spans))):
                cand = spans[j]
                t = cand["text"].strip()
                if t.startswith("|") or t.lower().startswith("client") or t.lower().startswith("relationship"):
                    continue
                # skip dates so we don't collide with quote_date
                if any(m in t for m in months):
                    continue
                if len(t) >= 4:
                    nxt2 = spans[j + 1] if j + 1 < len(spans) else None
                    f = _span_field(cand, next_sp=nxt2, max_x1=LEFT_PANEL)
                    f["bold"] = True
                    fields["prepared_by"] = f
                    break
            break

    # Quote date: left-panel date like "27 January 2026" (NOT weekday event dates)
    months = (
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    )
    weekdays = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
    for i, sp in enumerate(spans):
        t = sp["text"].strip()
        if any(m in t for m in months) and any(ch.isdigit() for ch in t):
            # left info panel
            if 220 < sp["bbox"][0] < 340 and "valid" not in t.lower() and "requested" not in t.lower():
                if any(t.startswith(d) for d in weekdays):
                    continue
                # next_sp is typically "| Quotation valid..." — widen=0.5 preserves it
                nxt = None
                if i + 1 < len(spans) and abs(spans[i + 1]["bbox"][1] - sp["bbox"][1]) < 3:
                    nxt = spans[i + 1]
                f = _span_field(sp, next_sp=nxt, widen=0.5)
                f["bold"] = True
                fields["quote_date"] = f
                break

    # Fallback: span immediately before '| Quotation valid'
    if "quote_date" not in fields:
        for i, sp in enumerate(spans):
            if "quotation valid" in sp["text"].lower() and i > 0:
                prev = spans[i - 1]
                if abs(prev["bbox"][1] - sp["bbox"][1]) < 4:
                    if prev["text"].strip() in ("|", "| ") and i > 1:
                        f = _span_field(spans[i - 2], next_sp=prev, widen=0.5)
                    else:
                        f = _span_field(prev, next_sp=sp, widen=0.5)
                    f["bold"] = True
                    fields["quote_date"] = f
                    break

    gqn = _guest_quote_n(spans)
    if gqn:
        fields["guest_quote_n"] = gqn

    # Guest ranges like "200 – 250" need more width than the template's "40-50"
    if "guest_range" in fields:
        gr = fields["guest_range"]
        x0, y0, _, y1 = gr["bbox"]
        x1 = min(RIGHT_PANEL, x0 + 28.0)
        gr["bbox"] = (x0, y0, x1, y1)
        gr["max_width"] = round(x1 - x0, 1)

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
                            # Titles vary in length across RMs — expand past the
                            # template placeholder (max_x1 is a cap, not a target).
                            tf = _span_field(title, next_sp=None, widen=2.0)
                            x0, y0, _, y1 = tf["bbox"]
                            x1 = 160.0
                            tf["bbox"] = (x0, y0, x1, y1)
                            tf["max_width"] = round(x1 - x0, 1)
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
    """
    Measure the Added Extras column while treating the instructional header
    ('Consider upgrading your bespoke package to the left with the below
    items...') as a permanent, never-redacted layout anchor.

    Dynamic bullets always start UPGRADE_HEADER_GAP_PT below the header's
    last-line baseline, regardless of which upgrades are selected.
    """
    spans = _spans(page)
    header_spans = []
    for i, sp in enumerate(spans):
        if "consider upgrading" not in sp["text"].lower():
            continue
        header_spans.append(sp)
        for j in range(i + 1, min(i + 5, len(spans))):
            nxt = spans[j]
            if nxt["bbox"][0] < 350:
                break
            if abs(nxt["bbox"][0] - sp["bbox"][0]) > 8:
                break
            if nxt["bbox"][1] > sp["bbox"][1] + 22:
                break
            low = nxt["text"].lower()
            if nxt["text"].strip() in ("•", "\u2022") or low.startswith("drink") or low.startswith("unlimited"):
                break
            header_spans.append(nxt)
            if "below items" in low or "items..." in low:
                break
        break

    cfg = dict(
        page=page_index,
        clear_zone=tuple(config.UPGRADE_LIST["clear_zone"]),
        bullet_x=config.UPGRADE_LIST["bullet_x"],
        text_x=config.UPGRADE_LIST["text_x"],
        first_baseline_y=config.UPGRADE_LIST["first_baseline_y"],
        header_baseline_y=config.UPGRADE_LIST.get("header_baseline_y", 84.2),
        header_bottom=config.UPGRADE_LIST.get("header_bottom", 85.6),
        row_pitch=config.UPGRADE_LIST["row_pitch"],
        bullet_size=config.UPGRADE_LIST["bullet_size"],
        text_size=config.UPGRADE_LIST["text_size"],
        max_width=config.UPGRADE_LIST["max_width"],
        bold=False,
        header_protected=True,
        header_lines=[
            "Consider upgrading your bespoke package to",
            "the left with the below items...",
        ],
        header_size=4.7,
        header_color=config.TEXT_COLOR,
        header_x=368.7,
    )

    if header_spans:
        header_baseline = header_spans[-1]["origin"][1]
        header_bottom = max(s["bbox"][3] for s in header_spans)
        cfg["header_baseline_y"] = round(header_baseline, 1)
        cfg["header_bottom"] = round(header_bottom, 1)
        cfg["header_x"] = round(header_spans[0]["origin"][0], 1)
        cfg["header_size"] = round(header_spans[0]["size"], 2)
        cfg["header_color"] = _span_color(header_spans[0])
        cfg["header_lines"] = [s["text"].rstrip() for s in header_spans]
        if len(cfg["header_lines"]) == 1 and "below items" not in cfg["header_lines"][0].lower():
            cfg["header_lines"] = [
                "Consider upgrading your bespoke package to",
                "the left with the below items...",
            ]

    gap = float(getattr(config, "UPGRADE_HEADER_GAP_PT", 20.0))
    cfg["first_baseline_y"] = round(cfg["header_baseline_y"] + gap, 1)

    text_spans = [
        s for s in spans
        if s["bbox"][0] > 360
        and s["bbox"][1] > cfg["header_bottom"]
        and len(s["text"].strip()) > 5
        and "consider upgrading" not in s["text"].lower()
        and "below items" not in s["text"].lower()
    ]
    text_spans.sort(key=lambda s: s["bbox"][1])
    if text_spans:
        cfg["text_x"] = round(text_spans[0]["bbox"][0], 1)
        cfg["text_size"] = round(text_spans[0]["size"], 2)
        cfg["bullet_x"] = round(cfg["text_x"] - 5.7, 1)
        if len(text_spans) >= 2:
            pitch = text_spans[1]["origin"][1] - text_spans[0]["origin"][1]
            if pitch > 4:
                cfg["row_pitch"] = round(pitch, 1)
        bottom = max(s["bbox"][3] for s in text_spans)
    else:
        bottom = 240.0

    # Clear ONLY the dynamic bullet zone — from just under the protected
    # header through the last catalogue row. Starting later leaves orphan
    # template bullets in the 20pt gap above the first stacked item.
    clear_y0 = round(cfg["header_bottom"] + 1.0, 1)
    cfg["clear_zone"] = (360.0, clear_y0, 500.0, round(max(bottom + 8.0, clear_y0 + 40), 1))
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


# In-process + on-disk profile cache (measurement is the slow part)
_PROFILE_CACHE: dict[str, TemplateProfile] = {}
_DISK_CACHE_DIR = Path(__file__).resolve().parent / "assets" / "templates" / "catalog" / ".profile_cache"


def _profile_to_dict(profile: TemplateProfile) -> dict:
    return {
        "path": profile.path,
        "pages": profile.pages,
        "page_cover": profile.page_cover,
        "page_vessel": profile.page_vessel,
        "page_bespoke": profile.page_bespoke,
        "page_extras": profile.page_extras,
        "page_contact": profile.page_contact,
        "cover_fields": profile.cover_fields,
        "contact_fields": profile.contact_fields,
        "financial_fields": profile.financial_fields,
        "upgrade_list": profile.upgrade_list,
        "package_columns": profile.package_columns,
        "package_clear_zone": list(profile.package_clear_zone),
        "menu_link_targets": profile.menu_link_targets,
    }


def _profile_from_dict(data: dict) -> TemplateProfile:
    return TemplateProfile(
        path=data["path"],
        pages=data["pages"],
        page_cover=data.get("page_cover", 0),
        page_vessel=data.get("page_vessel"),
        page_bespoke=data.get("page_bespoke"),
        page_extras=data.get("page_extras"),
        page_contact=data.get("page_contact"),
        cover_fields=data.get("cover_fields") or {},
        contact_fields=data.get("contact_fields") or {},
        financial_fields=data.get("financial_fields") or {},
        upgrade_list=data.get("upgrade_list") or {},
        package_columns=data.get("package_columns") or [],
        package_clear_zone=tuple(data.get("package_clear_zone") or (22.0, 156.0, 360.0, 263.8)),
        menu_link_targets=data.get("menu_link_targets") or {},
    )


def _disk_cache_path(template_path: str) -> Path:
    digest = hashlib.sha1(str(template_path).encode("utf-8")).hexdigest()[:16]
    try:
        mtime = int(Path(template_path).stat().st_mtime)
    except OSError:
        mtime = 0
    return _DISK_CACHE_DIR / f"{digest}_{mtime}.json"


def get_profile(template_path: str, *, force: bool = False) -> TemplateProfile:
    key = str(template_path)
    if not force and key in _PROFILE_CACHE:
        return _PROFILE_CACHE[key]

    disk = _disk_cache_path(key)
    if not force and disk.exists():
        try:
            data = json.loads(disk.read_text(encoding="utf-8"))
            profile = _profile_from_dict(data)
            _PROFILE_CACHE[key] = profile
            return profile
        except Exception:
            pass

    profile = measure_template(key)
    _PROFILE_CACHE[key] = profile
    try:
        _DISK_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        digest = disk.name.split("_")[0]
        for old in _DISK_CACHE_DIR.glob(f"{digest}_*.json"):
            if old != disk:
                old.unlink(missing_ok=True)
        disk.write_text(json.dumps(_profile_to_dict(profile)), encoding="utf-8")
    except Exception:
        pass
    return profile


def clear_profile_cache():
    _PROFILE_CACHE.clear()
    if _DISK_CACHE_DIR.exists():
        for f in _DISK_CACHE_DIR.glob("*.json"):
            f.unlink(missing_ok=True)


def warm_profiles(template_paths):
    """Pre-measure a list of templates (call at app startup)."""
    for path in template_paths:
        try:
            get_profile(path)
        except Exception:
            continue
