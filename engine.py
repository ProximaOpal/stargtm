"""
engine.py
---------
Dynamic PDF Proposal Orchestrator -- top-level entry point.

USAGE
    python engine.py payload.json template.pdf output.pdf

PAYLOAD SCHEMA (JSON)
    {
      "lead": { ... cover + contact fields ... },
      "calculations": { "guests", "package_cost", "vat", "grand_total" },
      "selectedUpgrades": ["live_dj", ...],
      "packageWording": { "venue_and_management": [...], ... },
      "vessel": "weott_i" | "avon_tour" | "london_rose",
      "menuLinks": {
        "food_menu": "https://...",
        "mood_board": "https://...",
        "street_food_menu": "https://..."
      }
    }
"""

import json
import sys

import fitz

from fonts import FontManager
from cover_contact import fill_cover_page, fill_contact_page
from bespoke import (
    render_financials,
    render_upgrade_list,
    render_package_columns,
    apply_menu_links,
)
from vessel import swap_vessel_page


def build_proposal(payload: dict, template_path: str, output_path: str) -> dict:
    warnings = []
    lead = payload.get("lead", {})
    calculations = payload.get("calculations", {})
    selected_upgrades = payload.get("selectedUpgrades", [])
    package_wording = payload.get("packageWording", {})
    vessel_id = payload.get("vessel") or lead.get("vessel")
    menu_links = payload.get("menuLinks") or {}

    doc = fitz.open(template_path)
    font_mgr = FontManager()

    # --- Page 9: vessel profile swap (before other edits; page indices stable) ---
    if vessel_id:
        swap_vessel_page(doc, vessel_id, warnings)

    # --- Page 1: cover ---
    fill_cover_page(doc, lead, font_mgr, warnings)

    # --- Page 13: financials ---
    render_financials(doc, calculations, font_mgr, warnings)

    # --- Page 13: conditional upgrade list ---
    render_upgrade_list(doc, selected_upgrades, font_mgr, warnings)

    # --- Page 13 -> 14: bespoke description stacking + overflow ---
    if package_wording:
        render_package_columns(doc, package_wording, font_mgr, warnings)

    # --- Page 13: menu / mood-board link URIs ---
    if menu_links:
        apply_menu_links(doc, menu_links, warnings)

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


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python engine.py payload.json template.pdf output.pdf")
        sys.exit(1)

    with open(sys.argv[1], encoding="utf-8") as f:
        payload = json.load(f)

    report = build_proposal(payload, sys.argv[2], sys.argv[3])
    print(json.dumps(report, indent=2))
    if report["warnings"]:
        print("\n⚠ VALIDATION WARNINGS -- recommend manual review before sending:", file=sys.stderr)
        for w in report["warnings"]:
            print(f"  - {w}", file=sys.stderr)
