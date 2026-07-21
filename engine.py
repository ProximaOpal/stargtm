"""
engine.py
---------
Dynamic PDF Proposal Orchestrator -- supports all Corporate + Wedding templates
plus optional manual insert selection (Meera MVP Priority 1).

USAGE
    python engine.py payload.json [template.pdf] output.pdf

Pass AUTO (or omit template) to resolve from event_type / category / slot,
or set payload.template_id for an explicit salesperson-selected template.
"""

import json
import sys
import time

import fitz

from fonts import get_font_manager
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
from inserts import apply_inserts


def build_proposal(payload: dict, template_path: str | None, output_path: str) -> dict:
    t0 = time.perf_counter()
    warnings = []
    lead = payload.get("lead", {})
    calculations = payload.get("calculations", {})
    selected_upgrades = payload.get("selectedUpgrades", [])
    package_wording = payload.get("packageWording", {})
    vessel_id = payload.get("vessel") or lead.get("vessel")
    menu_links = payload.get("menuLinks") or {}
    selected_inserts = (
        payload.get("selectedInserts")
        or payload.get("inserts")
        or payload.get("selected_inserts")
        or []
    )
    prefer_manual = bool(payload.get("template_id") or payload.get("manual_template"))

    resolved = None
    auto = not template_path or str(template_path).upper() in ("AUTO", "AUTO.PDF", "-")
    if auto:
        resolved = resolve_template(payload)
        template_path = resolved["path"]
        if "event_type" not in lead and resolved.get("event_type"):
            lead = dict(lead)
            lead["event_type"] = resolved["event_type"]
            payload = dict(payload)
            payload["lead"] = lead
        if prefer_manual and payload.get("template_id"):
            resolved["matched_by"] = f"manual_template_id:{resolved.get('matched_by')}"
    else:
        resolved = {
            "id": "explicit",
            "path": template_path,
            "matched_by": "cli_path",
            "category": payload.get("category"),
            "event_type": lead.get("event_type") or payload.get("event_type"),
            "slot": payload.get("slot"),
        }

    profile = get_profile(template_path)
    t_measure = time.perf_counter()

    doc = fitz.open(template_path)
    font_mgr = get_font_manager()
    font_mgr.reset_doc_registry()

    # Vessel insert PDFs replace the vessel page; otherwise use legacy vessel swap.
    if vessel_id and profile.page_vessel is not None and not selected_inserts:
        if str(vessel_id).lower().replace(" ", "_") not in (
            "weott_i",
            "weott",
            "weotti",
            "weott1",
            "",
        ):
            swap_vessel_page(doc, vessel_id, warnings, page_index=profile.page_vessel)

    fill_cover_page(doc, lead, font_mgr, warnings, profile=profile)
    render_financials(doc, calculations, font_mgr, warnings, profile=profile)
    render_upgrade_list(doc, selected_upgrades, font_mgr, warnings, profile=profile)

    if package_wording:
        render_package_columns(doc, package_wording, font_mgr, warnings, profile=profile)

    if menu_links:
        apply_menu_links(doc, menu_links, warnings, profile=profile)

    fill_contact_page(doc, lead, font_mgr, warnings, profile=profile)

    insert_report = {"applied": [], "requested": [], "resolved": 0}
    if selected_inserts:
        insert_report = apply_inserts(doc, list(selected_inserts), warnings)

    doc.save(output_path, garbage=0, deflate=False)
    page_count = doc.page_count
    doc.close()
    t1 = time.perf_counter()

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
        "inserts": insert_report,
        "warnings": [f"[{w.field}] {w.message}" for w in warnings],
        "page_count_final": page_count,
        "timing_ms": {
            "resolve_and_measure": round((t_measure - t0) * 1000),
            "render_and_save": round((t1 - t_measure) * 1000),
            "total": round((t1 - t0) * 1000),
        },
    }


if __name__ == "__main__":
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
