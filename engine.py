"""
engine.py
---------
Dynamic PDF Proposal Orchestrator -- supports all Corporate + Wedding templates.

USAGE
    python engine.py payload.json [template.pdf] output.pdf

If template.pdf is omitted (2-arg form after payload), or the special token
AUTO is passed, the engine resolves the template from:
    payload.category + payload.event_type + payload.slot
(or lead.event_type). See catalog.py.

PAYLOAD (key additions)
    {
      "category": "corporate" | "wedding",
      "event_type": "Summer Event",
      "slot": "daytime" | "evening" | "any" | "above_12" | "below_12",
      "template_id": "corporate/summer_event/any",   // optional explicit
      "lead": { "event_type": "...", ... },
      "calculations": {...},
      "selectedUpgrades": [...],
      "packageWording": {...},
      "vessel": "weott_i",
      "menuLinks": {...}
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
from catalog import resolve_template, get_catalog
from measure import get_profile


def build_proposal(payload: dict, template_path: str | None, output_path: str) -> dict:
    warnings = []
    lead = payload.get("lead", {})
    calculations = payload.get("calculations", {})
    selected_upgrades = payload.get("selectedUpgrades", [])
    package_wording = payload.get("packageWording", {})
    vessel_id = payload.get("vessel") or lead.get("vessel")
    menu_links = payload.get("menuLinks") or {}

    # Resolve template from event type when path is missing / AUTO
    resolved = None
    if not template_path or str(template_path).upper() in ("AUTO", "AUTO.PDF", "-"):
        resolved = resolve_template(payload)
        template_path = resolved["path"]
        # Ensure cover event_type matches the selected template's canonical name
        if "event_type" not in lead and resolved.get("event_type"):
            lead = dict(lead)
            lead["event_type"] = resolved["event_type"]
            payload = dict(payload)
            payload["lead"] = lead
    else:
        # Still record what would have been selected, for the report
        try:
            resolved = resolve_template(payload)
        except Exception:
            resolved = {"id": "explicit", "path": template_path, "matched_by": "cli_path"}

    profile = get_profile(template_path)

    doc = fitz.open(template_path)
    font_mgr = FontManager()

    if vessel_id and profile.page_vessel is not None:
        swap_vessel_page(doc, vessel_id, warnings, page_index=profile.page_vessel)

    fill_cover_page(doc, lead, font_mgr, warnings, profile=profile)
    render_financials(doc, calculations, font_mgr, warnings, profile=profile)
    render_upgrade_list(doc, selected_upgrades, font_mgr, warnings, profile=profile)

    if package_wording:
        render_package_columns(doc, package_wording, font_mgr, warnings, profile=profile)

    if menu_links:
        apply_menu_links(doc, menu_links, warnings, profile=profile)

    fill_contact_page(doc, lead, font_mgr, warnings, profile=profile)

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()

    return {
        "output_path": output_path,
        "template_id": (resolved or {}).get("id"),
        "template_path": template_path,
        "template_matched_by": (resolved or {}).get("matched_by"),
        "category": (resolved or {}).get("category"),
        "event_type": (resolved or {}).get("event_type") or lead.get("event_type"),
        "slot": (resolved or {}).get("slot"),
        "using_brand_font": font_mgr.using_brand_font,
        "measured_cover_fields": sorted(profile.cover_fields.keys()),
        "warnings": [f"[{w.field}] {w.message}" for w in warnings],
        "page_count_final": _page_count(output_path),
    }


def _page_count(path: str) -> int:
    d = fitz.open(path)
    n = d.page_count
    d.close()
    return n


if __name__ == "__main__":
    # Forms:
    #   python engine.py payload.json output.pdf
    #   python engine.py payload.json AUTO output.pdf
    #   python engine.py payload.json template.pdf output.pdf
    if len(sys.argv) == 3:
        payload_path, output_path = sys.argv[1], sys.argv[2]
        template_path = "AUTO"
    elif len(sys.argv) == 4:
        payload_path, template_path, output_path = sys.argv[1], sys.argv[2], sys.argv[3]
    else:
        print("Usage:")
        print("  python engine.py payload.json output.pdf")
        print("  python engine.py payload.json AUTO output.pdf")
        print("  python engine.py payload.json template.pdf output.pdf")
        print("\nKnown event types:")
        cat = get_catalog()
        for et in cat.list_event_types():
            print(f"  - {et}  slots={cat.list_slots(et)}")
        sys.exit(1)

    with open(payload_path, encoding="utf-8") as f:
        payload = json.load(f)

    report = build_proposal(payload, template_path, output_path)
    print(json.dumps(report, indent=2))
    if report["warnings"]:
        print("\n⚠ VALIDATION WARNINGS -- recommend manual review before sending:", file=sys.stderr)
        for w in report["warnings"]:
            print(f"  - {w}", file=sys.stderr)
