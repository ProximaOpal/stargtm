# WEOTT PDF Proposal Engine (vendored from stargtm)

Pixel-aligned proposal PDF generator for West End on the Thames.

This package lives in the Nexus monorepo as `artifacts/pdf-engine` and is kept
in sync with [ProximaOpal/stargtm](https://github.com/ProximaOpal/stargtm).

## MVP behaviour (Meera Priority 1)

1. **Manual template selection** — pass `template_id` in the payload (salesperson picks in the UI). Auto event-type matching remains as fallback only.
2. **Optional inserts** — pass `selectedInserts: string[]` of insert ids from `assets/inserts/manifest.json`.
3. **Placement rules**
   - `vessel` → replace page index 8 (Vessel Details)
   - `staff` → replace page index 15 (Contact / page 16), shifted if maps were inserted
   - `map` → insert after vessel page
4. **Finances are not calculated here** — `calculations.package_cost / vat / grand_total` come from the Quote Sheet SoT in the UI (`quoteFinance.ts`).

## Quick start

```bash
cd artifacts/pdf-engine
pip install -r requirements.txt
python app.py
# GET  /templates
# GET  /inserts
# POST /generate
```

## Adding templates / inserts

- **Templates:** drop PDFs under `assets/templates/`, run `python tools/build_catalog.py`.
- **Inserts:** add PDF to `assets/inserts/files/{id}.pdf` and append an entry to `assets/inserts/manifest.json`.

## Deploy

Same as upstream stargtm (`render.yaml` / gunicorn `app:app`).
