"""
catalog.py
----------
Resolve which proposal PDF to use from category + event_type + slot.

Selection order:
  1. Explicit payload.template_id  (e.g. "corporate/summer_event/any")
  2. category + event_type + slot
  3. event_type alone (search aliases across categories)
  4. Transfer auto-slot from guest count
  5. Fallback to legacy template.pdf / summer_event
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
MANIFEST_PATH = BASE_DIR / "assets" / "templates" / "catalog" / "manifest.json"
LEGACY_TEMPLATE = BASE_DIR / "template.pdf"


def _slug(text: str) -> str:
    text = (text or "").strip().lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


class TemplateCatalog:
    def __init__(self, manifest_path: Path = MANIFEST_PATH):
        self.manifest_path = Path(manifest_path)
        self.templates = []
        self.by_id = {}
        self._load()

    def _load(self):
        if not self.manifest_path.exists():
            return
        data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        self.templates = data.get("templates", [])
        self.by_id = {t["id"]: t for t in self.templates}

    def list_event_types(self, category: str | None = None) -> list[str]:
        seen = []
        for t in self.templates:
            if category and t["category"] != category.lower():
                continue
            if t["event_type"] not in seen:
                seen.append(t["event_type"])
        return seen

    def list_slots(self, event_type: str, category: str | None = None) -> list[str]:
        slug = _slug(event_type)
        slots = []
        for t in self.templates:
            if category and t["category"] != category.lower():
                continue
            if t["event_slug"] == slug or _slug(event_type) in [_slug(a) for a in t.get("aliases", [])]:
                if t["slot"] not in slots:
                    slots.append(t["slot"])
        return slots

    def resolve(self, payload: dict) -> dict:
        """
        Returns {id, path, category, event_type, slot, matched_by}.
        Raises FileNotFoundError if nothing usable is found.
        """
        lead = payload.get("lead", {})
        template_id = payload.get("template_id")
        category = (payload.get("category") or lead.get("category") or "").strip().lower() or None
        event_type = (
            payload.get("event_type")
            or lead.get("event_type")
            or payload.get("eventType")
            or ""
        ).strip()
        slot = (
            payload.get("slot")
            or payload.get("time_of_day")
            or lead.get("slot")
            or lead.get("time_of_day")
            or ""
        ).strip().lower() or None

        # Normalize slot aliases
        slot_map = {
            "day": "daytime", "daytime": "daytime",
            "evening": "evening", "night": "evening",
            "any": "any", "default": "default",
            "above_12": "above_12", "below_12": "below_12",
            "above12": "above_12", "below12": "below_12",
        }
        if slot:
            slot = slot_map.get(slot, _slug(slot))

        # Transfer auto-slot from guest count
        if event_type and "transfer" in event_type.lower() and not slot:
            guests = payload.get("calculations", {}).get("guests") or lead.get("guest_quote_n")
            try:
                n = int(str(guests).strip())
                slot = "above_12" if n >= 12 else "below_12"
            except (TypeError, ValueError):
                slot = "above_12"

        if template_id and template_id in self.by_id:
            return self._result(self.by_id[template_id], matched_by="template_id")

        candidates = list(self.templates)

        # Filter by category if given
        if category:
            candidates = [t for t in candidates if t["category"] == category]

        # Filter by event type / aliases
        if event_type:
            slug = _slug(event_type)
            matched = []
            for t in candidates:
                aliases = [_slug(a) for a in t.get("aliases", [])] + [t["event_slug"], _slug(t["event_type"])]
                if slug in aliases or slug.replace("_event", "") in [a.replace("_event", "") for a in aliases]:
                    matched.append(t)
            candidates = matched or candidates

        if not candidates and self.templates:
            # broaden: search all categories by alias
            slug = _slug(event_type)
            candidates = [
                t for t in self.templates
                if slug in [_slug(a) for a in t.get("aliases", [])] + [t["event_slug"]]
            ]

        if not candidates:
            # Ultimate fallback: legacy single template or summer_event
            for fallback_id in ("corporate/summer_event/any",):
                if fallback_id in self.by_id:
                    return self._result(self.by_id[fallback_id], matched_by="fallback_summer")
            if LEGACY_TEMPLATE.exists():
                return {
                    "id": "legacy/template.pdf",
                    "path": str(LEGACY_TEMPLATE),
                    "category": category or "corporate",
                    "event_type": event_type or "Summer Event",
                    "slot": slot or "any",
                    "matched_by": "legacy_template",
                }
            raise FileNotFoundError(
                f"No template found for event_type={event_type!r} category={category!r}. "
                f"Known event types: {self.list_event_types()}"
            )

        # Slot preference
        preferred_slots = []
        if slot:
            preferred_slots.append(slot)
        preferred_slots += ["any", "default", "daytime", "evening", "above_12", "below_12"]

        for pref in preferred_slots:
            for t in candidates:
                if t["slot"] == pref:
                    return self._result(t, matched_by=f"event_type+slot:{pref}")

        return self._result(candidates[0], matched_by="event_type_first_match")

    def _result(self, entry: dict, matched_by: str) -> dict:
        # path in manifest is relative to repo root
        rel = entry["path"]
        abs_path = BASE_DIR / rel.replace("assets/templates/", "assets/templates/")
        # manifest stores "assets/templates/catalog/..."
        abs_path = BASE_DIR / Path(rel)
        if not abs_path.exists():
            # try relative to catalog parent
            abs_path = BASE_DIR / "assets" / "templates" / "catalog" / entry["category"] / entry["event_slug"] / entry["slot"] / "template.pdf"
        if not abs_path.exists():
            raise FileNotFoundError(f"Template file missing for {entry['id']}: {abs_path}")
        return {
            "id": entry["id"],
            "path": str(abs_path),
            "category": entry["category"],
            "event_type": entry["event_type"],
            "slot": entry["slot"],
            "matched_by": matched_by,
        }


# Module-level singleton
_catalog = None


def get_catalog() -> TemplateCatalog:
    global _catalog
    if _catalog is None:
        _catalog = TemplateCatalog()
    return _catalog


def resolve_template(payload: dict) -> dict:
    return get_catalog().resolve(payload)
