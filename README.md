# WEOTT Dynamic PDF Proposal Orchestrator

A working implementation built and tested against the real 18-page template
(`template.pdf`).

## Run it

```bash
pip install pymupdf
python engine.py data/sample_payload.json template.pdf output.pdf
```

## What's implemented

| Spec requirement | Status |
|---|---|
| Cover fields (Page 1) with house-style dates/timings | Done |
| Century Gothic body text + `#323232` colour | Done (`assets/fonts/CenturyGothic-Regular.ttf`) |
| Vessel page swap (Page 9) | Done — `assets/vessels/{weott_i,avon_tour,london_rose}.pdf` |
| Bespoke package columns + itinerary (Page 13) | Done |
| Financials (cost / VAT / total) | Done |
| Conditional upgrade filtering | Done |
| Menu / mood-board link rewrite | Done via `menuLinks` |
| Contact / RM sign-off (Page 16) | Done — measured coordinates |
| Redaction safety (images untouched; graphics preserved on financial cells) | Done |
| Overflow continuation page | Done (optional branded `assets/overflow_blank.pdf`) |

## Payload extras

```json
{
  "vessel": "weott_i",
  "menuLinks": {
    "food_menu": "https://…/summer-barbecue-2026",
    "mood_board": "https://drive.google.com/…"
  }
}
```

Cover formatters accept ISO dates (`2026-08-14`) and normalise to
`Friday 14th August 2026`, and timings like `18:00 - 22:00 (TBC)` to
`18:00hrs – 22:00hrs (TBC)`.

## Vessel profiles

Replace the placeholder PDFs in `assets/vessels/` with the real single-page
vessel profile PDFs (same page size as the template). The engine swaps
Page 9 for the selected `vessel` id.

## Brand bold

Drop a licensed `CenturyGothic-Bold.ttf` into `assets/fonts/` to unlock true
bold. Until then, bold fields reuse the regular brand face (better metric
match than a mismatched fallback at ~4.6pt).

## Re-measure coordinates

```bash
python tools/inspect_page.py template.pdf 12
```
