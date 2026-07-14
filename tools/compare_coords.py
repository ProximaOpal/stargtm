"""
Compare cover VALUE field bboxes across templates vs the original template.pdf.
Also locate real content pages (not TOC mentions).
"""
import json
import hashlib
from pathlib import Path
from collections import defaultdict

import fitz

ROOT = Path(r"C:\Users\grvns\Documents\stargtm\assets\templates\_scratch")
ORIG = Path(r"C:\Users\grvns\Documents\stargtm\template.pdf")
OUT = Path(r"C:\Users\grvns\Documents\stargtm\assets\templates\_analysis")


def spans(page):
    rows = []
    for b in page.get_text("dict")["blocks"]:
        if b.get("type") != 0:
            continue
        for line in b["lines"]:
            for sp in line["spans"]:
                rows.append(sp)
    return rows


def find_value_after_label(page, label_prefix):
    """Find the span that follows a label like 'Event type |' on the same line-ish."""
    sps = spans(page)
    for i, sp in enumerate(sps):
        if label_prefix.lower() in sp["text"].lower() and "|" in sp["text"]:
            # value may be in same span after | or next span
            if sp["text"].strip().endswith("|") and i + 1 < len(sps):
                return sps[i + 1]
            parts = sp["text"].split("|", 1)
            if len(parts) == 2 and parts[1].strip():
                return sp  # combined
        if sp["text"].strip() == label_prefix.strip() or sp["text"].strip() == label_prefix.strip() + " |":
            if i + 1 < len(sps):
                return sps[i + 1]
    # fallback: label without pipe in one span, value in next
    for i, sp in enumerate(sps):
        if label_prefix.lower().replace(" |", "") in sp["text"].lower() and "|" in sp["text"]:
            if i + 1 < len(sps) and "|" not in sps[i + 1]["text"]:
                # check same-ish y
                if abs(sps[i + 1]["bbox"][1] - sp["bbox"][1]) < 3:
                    return sps[i + 1]
    return None


def real_page(doc, heading):
    """Find page where heading is a large title, not TOC."""
    for i in range(doc.page_count):
        for sp in spans(doc[i]):
            t = sp["text"].strip()
            if t.upper() == heading.upper() and sp["size"] >= 10:
                return i
            if heading.upper() in t.upper() and sp["size"] >= 14:
                return i
    # fallback: first page containing heading not in TOC-like page
    for i in range(doc.page_count):
        text = doc[i].get_text("text")
        if heading in text and "Page 13" not in text[:80] and i > 2:
            # prefer pages where heading appears near top
            for sp in spans(doc[i]):
                if heading.lower() in sp["text"].lower() and sp["bbox"][1] < 80:
                    return i
    return None


def file_digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def analyze_one(path):
    doc = fitz.open(path)
    cover = doc[0]
    fields = {}
    for label in ["Proposal/Quotation Ref", "Prepared by", "Event type", "Event date requested",
                  "Event timings", "No. of guests", "Client Name", "Organisation", "Telephone", "Email"]:
        v = find_value_after_label(cover, label)
        if v:
            fields[label] = {
                "text": v["text"][:60],
                "bbox": [round(x, 1) for x in v["bbox"]],
                "size": round(v["size"], 2),
                "origin_y": round(v["origin"][1], 1) if "origin" in v else None,
            }
        else:
            fields[label] = None

    # Cover event type value text for taxonomy check
    et = fields.get("Event type")
    info = {
        "path": str(path),
        "pages": doc.page_count,
        "size": [round(doc[0].rect.width, 2), round(doc[0].rect.height, 2)],
        "sha256": file_digest(path)[:16],
        "fields": fields,
        "page_bespoke": real_page(doc, "YOUR BESPOKE PACKAGE"),
        "page_vessel": real_page(doc, "VESSEL DETAILS"),
        "page_contact": real_page(doc, "YOUR CONTACT"),
        "page_extras": real_page(doc, "ADDED EXTRAS"),
        "cover_event_type_text": et["text"].strip() if et else None,
    }
    doc.close()
    return info


def field_sig(fields):
    parts = []
    for k in sorted(fields.keys()):
        f = fields[k]
        if f:
            parts.append(f"{k}:{f['bbox']}")
        else:
            parts.append(f"{k}:NONE")
    return "|".join(parts)


def main():
    results = []
    # original first
    results.append({"rel": "ORIGINAL template.pdf", **analyze_one(ORIG)})

    for pdf in sorted(ROOT.rglob("*.pdf")):
        rel = str(pdf.relative_to(ROOT)).replace("\\", "/")
        print(rel)
        results.append({"rel": rel, **analyze_one(pdf)})

    # cluster by field bboxes
    clusters = defaultdict(list)
    for r in results:
        clusters[field_sig(r["fields"])].append(r["rel"])

    layout = defaultdict(list)
    for r in results:
        key = (r["pages"], r["page_bespoke"], r["page_vessel"], r["page_contact"], r["page_extras"])
        layout[str(key)].append(r["rel"])

    # Compare each to original
    orig = results[0]
    diffs = []
    for r in results[1:]:
        delta = {}
        for k, ov in orig["fields"].items():
            nv = r["fields"].get(k)
            if (ov is None) != (nv is None):
                delta[k] = {"orig": ov, "new": nv}
            elif ov and nv and ov["bbox"] != nv["bbox"]:
                delta[k] = {"orig_bbox": ov["bbox"], "new_bbox": nv["bbox"]}
        diffs.append({
            "rel": r["rel"],
            "same_as_orig_coords": len(delta) == 0,
            "page_layout": (r["pages"], r["page_bespoke"], r["page_vessel"], r["page_contact"]),
            "field_deltas": delta,
            "cover_event_type_text": r["cover_event_type_text"],
        })

    out = {
        "field_bbox_clusters": {k: v for k, v in clusters.items()},
        "layout_clusters": {k: v for k, v in layout.items()},
        "vs_original": diffs,
        "templates": results,
    }
    (OUT / "coords_compare.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print("\n=== FIELD BBOX CLUSTERS ===")
    for i, (sig, members) in enumerate(clusters.items(), 1):
        print(f"\nCluster {i}: {len(members)} templates")
        for m in members:
            print(" ", m)

    print("\n=== LAYOUT ===")
    for k, members in layout.items():
        print(k, len(members))

    same = sum(1 for d in diffs if d["same_as_orig_coords"])
    print(f"\nSame cover coords as original: {same}/{len(diffs)}")
    different = [d for d in diffs if not d["same_as_orig_coords"]]
    print(f"Different: {len(different)}")
    for d in different[:8]:
        print(" ", d["rel"], "deltas:", list(d["field_deltas"].keys())[:6])


if __name__ == "__main__":
    main()
