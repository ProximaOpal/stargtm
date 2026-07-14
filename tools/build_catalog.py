"""
Build a clean template catalog from the unpacked Corporate/Wedding ZIPs
and a machine-readable manifest for event-type → PDF resolution.
"""
import json
import re
import shutil
from pathlib import Path

SCRATCH = Path(r"C:\Users\grvns\Documents\stargtm\assets\templates\_scratch")
CATALOG = Path(r"C:\Users\grvns\Documents\stargtm\assets\templates\catalog")


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def classify_slot(folder_name: str | None) -> str:
    if not folder_name:
        return "default"
    n = folder_name.lower()
    if "below 12" in n:
        return "below_12"
    if "above 12" in n:
        return "above_12"
    if "daytime" in n and "evening" in n:
        return "any"
    if "daytime" in n:
        return "daytime"
    if "evening" in n:
        return "evening"
    return slugify(folder_name)


def main():
    if CATALOG.exists():
        shutil.rmtree(CATALOG)
    CATALOG.mkdir(parents=True)

    entries = []
    for pdf in sorted(SCRATCH.rglob("*.pdf")):
        parts = pdf.relative_to(SCRATCH).parts
        # corporate/Corporate/<Event>/[<Slot>/]file.pdf
        # wedding/Wedding/<Event>/[<Slot>/]file.pdf
        if "Corporate" in parts:
            category = "corporate"
            i = parts.index("Corporate")
        elif "Wedding" in parts:
            category = "wedding"
            i = parts.index("Wedding")
        else:
            continue

        event_type = parts[i + 1]
        rest = parts[i + 2 :]
        slot_folder = rest[0] if len(rest) > 1 else None
        slot = classify_slot(slot_folder)

        dest_dir = CATALOG / category / slugify(event_type) / slot
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "template.pdf"
        shutil.copy2(pdf, dest)

        entry = {
            "id": f"{category}/{slugify(event_type)}/{slot}",
            "category": category,
            "event_type": event_type,
            "event_slug": slugify(event_type),
            "slot": slot,
            "path": str(dest.relative_to(CATALOG.parent.parent.parent)).replace("\\", "/"),
            "aliases": _aliases(category, event_type, slot),
        }
        entries.append(entry)
        print("catalogued", entry["id"])

    manifest = {
        "version": 1,
        "description": "WEOTT proposal templates indexed by category + event type + slot",
        "templates": entries,
        "selection_rules": {
            "required": ["event_type"],
            "optional": ["category", "slot", "time_of_day", "guest_quote_n"],
            "slot_aliases": {
                "day": "daytime",
                "daytime": "daytime",
                "evening": "evening",
                "night": "evening",
                "any": "any",
                "default": "default",
            },
            "notes": [
                "If slot is omitted, prefer 'any' then 'default' then 'daytime'.",
                "For Transfer events, slot is auto-chosen from guest_quote_n (>=12 => above_12).",
            ],
        },
    }
    (CATALOG / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n{len(entries)} templates -> {CATALOG / 'manifest.json'}")


def _aliases(category, event_type, slot):
    base = [
        event_type,
        event_type.lower(),
        slugify(event_type).replace("_", " "),
        slugify(event_type),
    ]
    # short forms
    short = slugify(event_type).replace("_event", "").replace("_or_", "_")
    base.append(short)
    base.append(short.replace("_", " "))
    if category == "wedding" and "reception" in event_type.lower():
        base += ["wedding", "Wedding"]
    if "summer" in event_type.lower():
        base += ["Summer Event", "summer"]
    if "network" in event_type.lower():
        base += ["Networking", "Corporate Networking", "networking"]
    return sorted(set(base))


if __name__ == "__main__":
    main()
