import fitz
import os

doc = fitz.open(r"C:\Users\grvns\Documents\stargtm\template.pdf")
out = r"C:\Users\grvns\Documents\stargtm\assets\fonts"
seen = set()
for i in range(1, doc.xref_length()):
    try:
        info = doc.extract_font(i)
    except Exception:
        continue
    if not info or len(info) < 4 or not info[3]:
        continue
    name, ext, subtype, buffer = info[0], info[1], info[2], info[3]
    if not buffer or len(buffer) < 1000:
        continue
    key = (name, len(buffer))
    if key in seen:
        continue
    seen.add(key)
    safe = name.replace("+", "-").replace(",", "-").replace(" ", "")
    ext = ext or "ttf"
    path = os.path.join(out, f"extracted-{safe}.{ext}")
    with open(path, "wb") as f:
        f.write(buffer)
    print(f"extracted {name} subtype={subtype} ext={ext} bytes={len(buffer)}")
print("total", len(seen))

# Test if extracted fonts work with fitz.Font
for fn in os.listdir(out):
    if not fn.startswith("extracted-"):
        continue
    path = os.path.join(out, fn)
    try:
        font = fitz.Font(fontfile=path)
        w = font.text_length("WE.9055", fontsize=4.63)
        print(f"OK {fn} measure WE.9055={w:.2f}")
    except Exception as e:
        print(f"FAIL {fn}: {e}")
