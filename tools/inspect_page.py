"""
Utility: dump every text span on a page with its exact bbox, baseline-ready
y-coordinate, and font size. Use this whenever WEOTT tweaks the template, to
re-measure coordinates for config.py instead of guessing.

Usage:
    python3 tools/inspect_page.py template.pdf 12
"""
import sys
import fitz


def inspect(pdf_path: str, page_index: int):
    doc = fitz.open(pdf_path)
    page = doc[page_index]
    print(f"Page {page_index} size: {page.rect}")
    d = page.get_text("dict")
    for block in d["blocks"]:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                text = span["text"]
                if not text.strip():
                    continue
                bbox = tuple(round(v, 1) for v in span["bbox"])
                print(f"{bbox}  size={span['size']:.2f}  {text!r}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python3 inspect_page.py <pdf> <page_index_0based>")
        sys.exit(1)
    inspect(sys.argv[1], int(sys.argv[2]))
