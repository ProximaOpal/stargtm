"""
inserts.py
----------
Merge optional proposal inserts into a base template PDF.

Placement rules (MVP, manual selection — no auto-pick):
  - vessel: replace page index 8 (Vessel Details)
  - staff:  replace page index 15 (Contact / page 16)
  - map:    insert after the vessel page (default index 9)
  - other:  append at end unless target_page is set

Multiple vessel/staff inserts: last selected wins for that slot.
Multiple maps: inserted in selection order after the vessel page.
"""

from __future__ import annotations

import json
from pathlib import Path

import fitz

BASE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = BASE_DIR / "assets" / "inserts" / "manifest.json"

_manifest_cache = None


def get_insert_manifest() -> dict:
    global _manifest_cache
    if _manifest_cache is None:
        if MANIFEST_PATH.exists():
            _manifest_cache = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        else:
            _manifest_cache = {"version": 1, "inserts": [], "placement_rules": {}}
    return _manifest_cache


def list_inserts(
    *,
    kind: str | None = None,
    category: str | None = None,
    vessel: str | None = None,
) -> list[dict]:
    items = list(get_insert_manifest().get("inserts", []))
    if kind:
        items = [i for i in items if i.get("kind") == kind]
    if category and category != "any":
        items = [i for i in items if i.get("category") in (category, "any")]
    if vessel:
        v = vessel.lower()
        items = [
            i
            for i in items
            if not i.get("vessel")
            or v in str(i.get("vessel", "")).lower()
            or str(i.get("vessel", "")).lower() in v
        ]
    return items


def resolve_insert_paths(selected_ids: list[str]) -> list[dict]:
    """Return ordered insert entries for the given ids (skips missing)."""
    by_id = {i["id"]: i for i in get_insert_manifest().get("inserts", [])}
    resolved = []
    for iid in selected_ids or []:
        entry = by_id.get(iid)
        if not entry:
            continue
        path = BASE_DIR / entry["path"]
        if not path.exists():
            continue
        resolved.append({**entry, "abs_path": str(path)})
    return resolved


def _replace_page(doc: fitz.Document, insert_path: str, page_index: int, warnings: list) -> None:
    src = fitz.open(insert_path)
    try:
        if src.page_count < 1:
            warnings.append(
                type(
                    "ValidationWarning",
                    (),
                    {"field": "insert", "message": f"Insert has no pages: {insert_path}"},
                )()
            )
            return
        # Clamp if template is shorter than expected
        if page_index < 0 or page_index >= doc.page_count:
            warnings.append(
                type(
                    "ValidationWarning",
                    (),
                    {
                        "field": "insert",
                        "message": (
                            f"target_page {page_index} out of range "
                            f"(doc has {doc.page_count} pages) — appending instead"
                        ),
                    },
                )()
            )
            doc.insert_pdf(src, from_page=0, to_page=0, start_at=doc.page_count)
            return
        doc.insert_pdf(src, from_page=0, to_page=0, start_at=page_index)
        doc.delete_page(page_index + 1)
    finally:
        src.close()


def _insert_page_at(doc: fitz.Document, insert_path: str, start_at: int, warnings: list) -> int:
    """Insert first page of insert_path at start_at. Returns new page count delta (1)."""
    src = fitz.open(insert_path)
    try:
        if src.page_count < 1:
            warnings.append(
                type(
                    "ValidationWarning",
                    (),
                    {"field": "insert", "message": f"Insert has no pages: {insert_path}"},
                )()
            )
            return 0
        at = max(0, min(start_at, doc.page_count))
        doc.insert_pdf(src, from_page=0, to_page=0, start_at=at)
        return 1
    finally:
        src.close()


def apply_inserts(doc: fitz.Document, selected_ids: list[str], warnings: list) -> dict:
    """
    Apply selected inserts to an open document.
    Returns a small report of what was applied.
    """
    resolved = resolve_insert_paths(selected_ids)
    applied = []
    # Partition by kind; preserve user order within kind
    vessels = [r for r in resolved if r.get("kind") == "vessel"]
    staff = [r for r in resolved if r.get("kind") == "staff"]
    maps = [r for r in resolved if r.get("kind") == "map"]
    others = [r for r in resolved if r.get("kind") not in ("vessel", "staff", "map")]

    # Vessel: last wins
    if vessels:
        last = vessels[-1]
        page = last.get("target_page")
        if page is None:
            page = 8
        _replace_page(doc, last["abs_path"], int(page), warnings)
        applied.append({"id": last["id"], "kind": "vessel", "action": "replace", "page": page})
        if len(vessels) > 1:
            warnings.append(
                type(
                    "ValidationWarning",
                    (),
                    {
                        "field": "insert",
                        "message": f"Multiple vessel inserts selected; used last: {last['id']}",
                    },
                )()
            )

    # Maps: insert after vessel page (index 9 after replace keeps vessel at 8)
    map_at = 9
    for m in maps:
        target = m.get("target_page")
        at = int(target) if target is not None else map_at
        delta = _insert_page_at(doc, m["abs_path"], at, warnings)
        if delta:
            applied.append({"id": m["id"], "kind": "map", "action": "insert", "page": at})
            map_at = at + 1

    # Staff: last wins — page index may have shifted if maps were inserted before page 15
    if staff:
        last = staff[-1]
        page = last.get("target_page")
        if page is None:
            page = 15
        # After inserting N map pages at/after index 9, contact page shifts by N if original >= 9
        shift = len(maps)  # maps inserted starting at 9
        adjusted = int(page) + shift if int(page) >= 9 else int(page)
        _replace_page(doc, last["abs_path"], adjusted, warnings)
        applied.append(
            {"id": last["id"], "kind": "staff", "action": "replace", "page": adjusted}
        )
        if len(staff) > 1:
            warnings.append(
                type(
                    "ValidationWarning",
                    (),
                    {
                        "field": "insert",
                        "message": f"Multiple staff inserts selected; used last: {last['id']}",
                    },
                )()
            )

    for o in others:
        page = o.get("target_page")
        if page is None:
            _insert_page_at(doc, o["abs_path"], doc.page_count, warnings)
            applied.append({"id": o["id"], "kind": o.get("kind"), "action": "append"})
        else:
            _replace_page(doc, o["abs_path"], int(page), warnings)
            applied.append(
                {"id": o["id"], "kind": o.get("kind"), "action": "replace", "page": page}
            )

    return {"applied": applied, "requested": list(selected_ids or []), "resolved": len(resolved)}
