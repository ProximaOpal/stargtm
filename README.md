# WEOTT Dynamic PDF Proposal Orchestrator

Generates pixel-aligned proposal PDFs across **all Corporate and Wedding**
templates. Event type (plus optional category/slot) selects the right PDF.

## Quick start

```bash
pip install -r requirements.txt
python engine.py data/sample_payload.json AUTO output.pdf
python engine.py data/sample_wedding_payload.json AUTO wedding.pdf
```

## Event-type → template selection

Pass any of:

| Field | Example | Notes |
|---|---|---|
| `event_type` | `"Summer Event"` | Primary selector (also read from `lead.event_type`) |
| `category` | `"corporate"` / `"wedding"` | Disambiguates shared names |
| `slot` / `time_of_day` | `"daytime"` / `"evening"` / `"any"` | Day/evening variants |
| `template_id` | `"corporate/networking_event/evening"` | Explicit override |
| Transfer guests | `calculations.guests` | Auto-picks `above_12` / `below_12` |

List everything the engine knows:

```bash
python -c "from catalog import get_catalog; c=get_catalog(); print(c.list_event_types())"
```

Or `GET /templates` when the Flask app is running.

### Catalogued templates (24)

**Corporate:** Award Ceremony, Christmas Event, Client Event, Company Anniversary,
Conference or Workshop, Meeting, Networking Event, Social Gathering, Summer Event,
Team Building, Transfer (above/below 12 guests) — with daytime/evening slots where present.

**Wedding:** Engagement Celebration, Wedding Anniversary or Pre-Wedding Party,
Wedding Reception, Wedding Transfer.

Templates live under `assets/templates/catalog/` with `manifest.json`.

## How it stays accurate across variants

Cover / contact / finance / upgrade geometry is **measured per template at
runtime** (`measure.py`), so the ~1pt drift between Summer / Wedding /
Engagement covers does not break field injection.

## Payload shape

```json
{
  "category": "corporate",
  "event_type": "Networking Event",
  "slot": "evening",
  "lead": { "...cover + contact fields..." },
  "calculations": { "guests": 50, "package_cost": 4600, "vat": 920, "grand_total": 5520 },
  "selectedUpgrades": ["live_dj", "photo_booth"],
  "packageWording": { "venue_and_management": [], "entertainment_and_decor": [], "stationery_and_catering": [] },
  "vessel": "weott_i",
  "menuLinks": { "food_menu": "https://..." }
}
```

## API

```bash
python app.py
# GET  /templates
# POST /generate   (resolves template from event_type automatically)
```

## Rebuild catalog after adding PDFs

```bash
# unzip new packs into assets/templates/_scratch then:
python tools/build_catalog.py
```
