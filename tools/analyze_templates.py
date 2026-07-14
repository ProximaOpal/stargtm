"""
Deep-analyze all Corporate + Wedding proposal templates:
- inventory tree
- page counts / sizes
- cover field span fingerprints
- page-index of "Bespoke Package" / "Vessel" / "Contact"
- structural similarity clustering (cover field bboxes)
"""
import hashlib
import json
import os
import re
from collections import defaultdict
from pathlib import Path

import fitz

ROOT = Path(r"C:\Users\grvns\Documents\stargtm\assets\templates\_scratch")
OUT = Path(r"C:\Users\grvns\Documents\stargtm\assets\templates\_analysis")
OUT.mkdir(parents=True, exist_ok=True)

LABEL_KEYS = [
    "Proposal/Quotation Ref",
    "Prepared by",
    "Client Name",
    "Organisation",
    "Telephone",
    "Email",
    "Event type",
    "Event date requested",
    "Event timings",
    "No. of guests",
    "YOUR BESPOKE PACKAGE",
    "VESSEL DETAILS",
    "YOUR CONTACT",
    "ADDED EXTRAS",
]


def find_label(page, needle):
    d = page.get_text("dict")
    hits = []
    for b in d["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for sp in line["spans"]:
                if needle.lower() in sp["text"].lower():
                    hits.append({
                        "text": sp["text"],
                        "bbox": [round(x, 1) for x in sp["bbox"]],
                        "size": round(sp["size"], 2),
                        "font": sp["font"],
                    })
    return hits


def page_titles(doc):
    titles = {}
    for i in range(doc.page_count):
        text = doc[i].get_text("text")
        first = " | ".join([ln.strip() for ln in text.splitlines() if ln.strip()][:4])[:120]
        titles[i] = first
    return titles


def cover_fingerprint(doc):
    """Stable fingerprint from cover label bboxes."""
    if doc.page_count < 1:
        return None
    page = doc[0]
    parts = []
    for label in ["Proposal/Quotation Ref", "Event type", "Event timings", "Client Name", "No. of guests"]:
        hits = find_label(page, label)
        if hits:
            parts.append(f"{label}:{hits[0]['bbox']}")
    return "|".join(parts)


def find_page_containing(doc, needle):
    for i in range(doc.page_count):
        if needle.lower() in doc[i].get_text("text").lower():
            return i
    return None


def analyze_pdf(path: Path, category: str):
    rel = path.relative_to(ROOT)
    doc = fitz.open(path)
    try:
        # Derive taxonomy from path
        parts = list(rel.parts)
        # e.g. corporate/Corporate/Summer Event/Daytime or Evening Event/file.pdf
        event_type = None
        slot = None
        if "Corporate" in parts:
            idx = parts.index("Corporate")
            event_type = parts[idx + 1] if len(parts) > idx + 1 else None
            slot = parts[idx + 2] if len(parts) > idx + 2 and not parts[idx + 2].lower().endswith(".pdf") else None
        elif "Wedding" in parts:
            idx = parts.index("Wedding")
            event_type = parts[idx + 1] if len(parts) > idx + 1 else None
            slot = parts[idx + 2] if len(parts) > idx + 2 and not parts[idx + 2].lower().endswith(".pdf") else None

        cover_labels = {}
        if doc.page_count:
            for label in ["Proposal/Quotation Ref |", "Event type |", "Event timings |", "Client Name |",
                          "Prepared by", "No. of guests |", "Organisation |"]:
                hits = find_label(doc[0], label.replace(" |", ""))
                cover_labels[label] = hits[0] if hits else None

        # Value spans that sit after labels (approximate by searching known placeholders)
        placeholders = {}
        if doc.page_count:
            text = doc[0].get_text("text")
            for pat in [r"WE\.\d+", r"Summer Event", r"Wedding", r"Katherine", r"Sarah Prentice"]:
                m = re.search(pat, text)
                placeholders[pat] = m.group(0) if m else None

        info = {
            "path": str(path),
            "rel": str(rel).replace("\\", "/"),
            "category": category,
            "event_type": event_type,
            "slot": slot,
            "filename": path.name,
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()[:16],
            "pages": doc.page_count,
            "page_size": [round(doc[0].rect.width, 2), round(doc[0].rect.height, 2)] if doc.page_count else None,
            "cover_fp": cover_fingerprint(doc),
            "page_bespoke": find_page_containing(doc, "YOUR BESPOKE PACKAGE"),
            "page_vessel": find_page_containing(doc, "VESSEL DETAILS"),
            "page_contact": find_page_containing(doc, "YOUR CONTACT"),
            "page_extras": find_page_containing(doc, "ADDED EXTRAS"),
            "cover_labels": cover_labels,
            "page_titles": page_titles(doc),
            "cover_text_preview": doc[0].get_text("text")[:800] if doc.page_count else "",
        }
        return info
    finally:
        doc.close()


def main():
    results = []
    for pdf in sorted(ROOT.rglob("*.pdf")):
        cat = "corporate" if "corporate" in str(pdf).lower().replace("\\", "/") else "wedding"
        print("analyzing", pdf.name[:60], "...")
        results.append(analyze_pdf(pdf, cat))

    # Cluster by cover fingerprint
    clusters = defaultdict(list)
    for r in results:
        clusters[r["cover_fp"] or "NONE"].append(r["rel"])

    # Cluster by page layout signature
    layout_clusters = defaultdict(list)
    for r in results:
        key = (r["pages"], r["page_bespoke"], r["page_vessel"], r["page_contact"], r["page_extras"])
        layout_clusters[str(key)].append(r["rel"])

    summary = {
        "total_templates": len(results),
        "by_category": {
            "corporate": sum(1 for r in results if r["category"] == "corporate"),
            "wedding": sum(1 for r in results if r["category"] == "wedding"),
        },
        "unique_cover_fingerprints": len(clusters),
        "cover_clusters": {k: v for k, v in clusters.items()},
        "layout_clusters": {k: v for k, v in layout_clusters.items()},
        "event_types": sorted({(r["category"], r["event_type"], r["slot"]) for r in results}),
        "templates": results,
    }

    with open(OUT / "analysis.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, default=str)

    # Human-readable inventory
    lines = ["# Template inventory\n", f"Total: {len(results)}\n"]
    for r in results:
        lines.append(
            f"- [{r['category']}] **{r['event_type']}** / {r['slot'] or '-'}  "
            f"pages={r['pages']} bespoke={r['page_bespoke']} vessel={r['page_vessel']} "
            f"contact={r['page_contact']} sha={r['sha256']}\n"
            f"  `{r['rel']}`\n"
        )
    lines.append("\n## Cover fingerprint clusters\n")
    for i, (fp, members) in enumerate(clusters.items(), 1):
        lines.append(f"\n### Cluster {i} ({len(members)} templates)\n`{fp}`\n")
        for m in members:
            lines.append(f"- {m}\n")
    lines.append("\n## Layout clusters (pages, bespoke, vessel, contact, extras)\n")
    for key, members in layout_clusters.items():
        lines.append(f"\n### {key} ({len(members)})\n")
        for m in members:
            lines.append(f"- {m}\n")

    (OUT / "inventory.md").write_text("".join(lines), encoding="utf-8")
    print("Wrote", OUT / "analysis.json")
    print("Cover clusters:", len(clusters))
    print("Layout clusters:", len(layout_clusters))
    for key, members in layout_clusters.items():
        print(" ", key, len(members))


if __name__ == "__main__":
    main()
