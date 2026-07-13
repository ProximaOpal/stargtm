# WEOTT Dynamic PDF Proposal Orchestrator

A working implementation of the spec you laid out — built and tested against
your real 18-page template (`template.pdf`), not a mock-up.

## Run it

```bash
pip install pymupdf
python3 engine.py data/sample_payload.json template.pdf output.pdf
```

`sample_payload.json` is a full worked example. The script prints a JSON
report (warnings, final page count, whether the brand font was found) and
exits non-zero-worthy warnings to stderr — wire that into your n8n workflow
as a "route to human review" branch.

## What's implemented and verified working

| Spec requirement | File | Status |
|---|---|---|
| Font embedding with fallback | `fonts.py` | ✅ Embeds real font files via `fitz.Font`; falls back to a bundled OFL geometric sans (not Helvetica) if Century Gothic isn't present |
| Precision baseline alignment | `pdf_ops.draw_field` | ✅ Same redact-then-insert-at-original-baseline approach as your original script, generalised |
| Bespoke package stacking | `bespoke.py` → `render_package_columns` | ✅ Flows wrapped bullet groups into the 3 real columns measured from your template; verified against real financial and description data |
| Overflow to a continuation page | `bespoke.py` → `_create_continuation_page` | ✅ Stress-tested: forcing ~14 extra lines correctly pushed the document from 18 → 19 pages and flagged the one case where even the continuation page wasn't enough |
| Financials (cost/VAT/total) | `bespoke.py` → `render_financials` | ✅ |
| Conditional upgrade filtering | `bespoke.py` → `render_upgrade_list` | ✅ Only selected items are drawn, stacked back-to-back — verified no gaps left behind for skipped items |
| Contact page update | `cover_contact.py` → `fill_contact_page` | ⚠️ Wired up, but the bbox coordinates in `config.CONTACT_FIELDS` are **placeholders** — see "What still needs your input" below |
| Redaction safety (`images=PDF_REDACT_IMAGE_NONE`) | `pdf_ops.redact_zone` | ✅ Same safety setting as your original script, centralised in one function so every page handler inherits it |
| Font-scaling validation alert | `fonts.py` → `fit_font_size` | ✅ but recalibrated — see note below |

## Fixes from visual QA (this round)

Three real issues were found by comparing rendered output against the actual
template at high zoom, not by inspection alone:

1. **Page 13 financial numbers were black; the template prints them in
   white** on the orange cells. Confirmed by sampling actual pixel colour
   from `template.pdf` (glyph colour was exactly `(255,255,255)`). Fixed in
   `config.FINANCIAL_FIELDS` — all four value fields now draw in white.
2. **The "50 guests" number was visibly smaller and off-baseline.** Root
   cause: the auto-shrink logic was constraining text width to the
   *original* redacted box (measured for the old two-digit value in the real
   Century Gothic font). The fallback font's digits render a hair wider, so
   the constraint forced a shrink from 4.63pt down to 4.1pt — smaller and
   sitting differently than the surrounding text. Fixed by giving that field
   an explicit `max_width` reflecting the real available space before the
   next word, instead of the tight original glyph box.
3. **Fallback bold was too heavy.** Poppins Bold is a noticeably heavier
   weight than Century Gothic Bold. Switched `assets/fonts/Fallback-Bold.ttf`
   to Poppins **Medium**, which is a much closer visual match — and, as a
   side effect, also needs less width, reducing how often auto-shrink kicks
   in at all.
4. **Page 9 vessel-swap feature removed entirely**, per instruction. Page 9
   is now left as the original template page, untouched.

## One deliberate deviation from the literal spec, and why

The brief says "trigger a validation alert if font-scaling drops below 8pt."
Your actual template's body copy is natively ~4.6–4.7pt (this PDF's page
coordinate space is a scaled-down surface, not full-size points) — an
absolute 8pt floor would fire on literally every field, which makes the
alert useless. I replaced it with a **relative** check: flag a field if it
had to shrink more than 15% from its designed size to fit. That's the signal
that actually means "this wording is too long for its box," which is what
the requirement is really trying to catch. Confirmed working: the sample
payload's `quote_date` field intentionally overflows and gets flagged.

## What still needs your input before this goes to production

1. **Century Gothic font files.** Drop `CenturyGothic-Regular.ttf` and
   `CenturyGothic-Bold.ttf` into `assets/fonts/` and the engine will use them
   automatically — no code change needed. It's a commercial Monotype font so
   I couldn't bundle it; everything currently renders with the bundled OFL
   fallback (visually close, same family as your previous Jost approach).
2. **Real vessel profile PDFs.** Not applicable -- the Page 9 vessel-swap
   feature has been removed. Page 9 is left as the original template page
   untouched; if you want vessel-specific profiles back in later, this is a
   small, separate feature to re-add.
3. **Contact page (Page 16) coordinates.** I didn't have a second real name/
   title length to diff against, so `config.CONTACT_FIELDS` bboxes are
   placeholders. Run `python3 tools/inspect_page.py template.pdf 15` and
   correct the four bboxes the same way the other three pages were measured.
4. **Continuation page branding.** The overflow page (`_create_continuation_page`
   in `bespoke.py`) currently generates a plain page with a title and a
   coral rule — it does not match your background art because I don't have
   that asset. If you'd like it pixel-matched, send over a blank branded
   page (same background as "Added Extras") and I'll swap the one function
   that builds it to `insert_pdf()` that asset instead.

## Re-measuring coordinates if the template changes

Don't eyeball new coordinates from a screenshot. Run:

```bash
python3 tools/inspect_page.py template.pdf <page_index_0based>
```

It prints every text span's exact bbox and font size straight from the PDF's
internal structure — that's how every number in `config.py` was derived.

## Files

```
engine.py           orchestrator + JSON schema + CLI entry point
config.py           every coordinate, page index, and catalogue — edit here first
fonts.py            font embedding + measurement + shrink validation
pdf_ops.py          shared redact-then-insert primitives
cover_contact.py     Page 1 + Page 16 field filling
bespoke.py           Page 13 financials, upgrade filtering, stacking + overflow
tools/inspect_page.py  re-measurement helper
assets/fonts/        font files (brand + fallback)
data/sample_payload.json  full worked example matching the JSON schema
```
