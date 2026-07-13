"""
engine.py
---------
Dynamic PDF Proposal Orchestrator -- top-level entry point.

USAGE
    python3 engine.py payload.json template.pdf output.pdf

PAYLOAD SCHEMA (JSON)
{
  "lead": {
    "proposal_ref": "WE.9128",
    "prepared_by": "Katherine Bulaon",
    "quote_date": "13 July 2026 | Quotation valid for 28 days",
    "client_name": "Sarah Prentice",
    "organisation": "Blue Apple Contract Catering",
    "telephone": "020 3452 2222",
    "email": "sarah@blue-apple.co.uk",
    "event_type": "Summer Event",
    "event_date": "Saturday 2nd June 2026",
    "event_timings": "13:00hrs - 17:00hrs",
    "guest_range": "40 - 60",
    "guest_quote_n": "40",
    "contact_name": "Katherine Bulaon",
    "contact_title": "Client Relationship Manager",
    "contact_phone": "020 8323 5827",
    "contact_email": "sales@westendonthethames.com"
  },
  "calculations": {
    "guests": 50,
    "package_cost": 4000,
    "vat": 800,
    "grand_total": 4800
  },
  "selectedUpgrades": ["live_dj", "photo_booth", "drink_tokens"],
  "packageWording": {
    "venue_and_management": [
      {"heading": "4 hours private venue hire", "items": ["Embark at 12:45hrs", "..."]}
    ],
    "entertainment_and_decor": [ ... ],
    "stationery_and_catering": [ ... ]
  }
}

Any field not present in `lead` is simply left as the template's original
placeholder text (so a partial payload never crashes the run).
"""

import json
import sys

import fitz

import config
from fonts import FontManager
from cover_contact import fill_cover_page, fill_contact_page
from bespoke import render_financials, render_upgrade_list, render_package_columns


def build_proposal(payload: dict, template_path: str, output_path: str) -> dict:
    """
    Runs the full pipeline. Returns a report dict with any validation
    warnings collected along the way (font-shrink alerts, overflow alerts,
    etc.) so a calling n8n workflow can decide
    whether to auto-send or route to human review.
    """
    warnings = []
    lead = payload.get("lead", {})
    calculations = payload.get("calculations", {})
    selected_upgrades = payload.get("selectedUpgrades", [])
    package_wording = payload.get("packageWording", {})

    doc = fitz.open(template_path)
    font_mgr = FontManager()

    # --- Page 1: cover ---
    fill_cover_page(doc, lead, font_mgr, warnings)

    # --- Page 13: financials ---
    render_financials(doc, calculations, font_mgr, warnings)

    # --- Page 13: conditional upgrade list ---
    render_upgrade_list(doc, selected_upgrades, font_mgr, warnings)

    # --- Page 13 -> 14: bespoke description stacking + overflow ---
    if package_wording:
        render_package_columns(doc, package_wording, font_mgr, warnings)

    # --- Page 16: contact / relationship manager sign-off ---
    fill_contact_page(doc, lead, font_mgr, warnings)

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    return {
        "output_path": output_path,
        "using_brand_font": font_mgr.using_brand_font,
        "warnings": [f"[{w.field}] {w.message}" for w in warnings],
        "page_count_final": _page_count(output_path),
    }


def _page_count(path: str) -> int:
    d = fitz.open(path)
    n = d.page_count
    d.close()
    return n


def _warn(field: str, message: str):
    return type("ValidationWarning", (), {"field": field, "message": message})()


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python3 engine.py payload.json template.pdf output.pdf")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        payload = json.load(f)

    report = build_proposal(payload, sys.argv[2], sys.argv[3])
    print(json.dumps(report, indent=2))
    if report["warnings"]:
        print("\n⚠ VALIDATION WARNINGS -- recommend manual review before sending:", file=sys.stderr)
        for w in report["warnings"]:
            print(f"  - {w}", file=sys.stderr)
