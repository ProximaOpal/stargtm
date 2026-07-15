"""
config.py
---------
All coordinate maps, brand constants, and structural configuration for the
WEOTT Dynamic PDF Proposal Orchestrator.

Every coordinate below was measured directly from the real 18-page template
(`template.pdf`) using PyMuPDF's `get_text("dict")`, not eyeballed from a
screenshot. If West End on the Thames changes the template's layout, re-run
`tools/inspect_page.py <page_index>` (included) to re-measure and update
this file — the engine code itself never needs to change.
"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(BASE_DIR, "assets", "fonts")
VESSEL_DIR = os.path.join(BASE_DIR, "assets", "vessels")

# ---------------------------------------------------------------------------
# FONTS
# ---------------------------------------------------------------------------
# Brand-correct pairing. CenturyGothic-Regular.ttf + CenturyGothic-Bold.ttf
# are derived from the template's embedded Century Gothic subsets.
FONT_PRIMARY_REGULAR = os.path.join(FONT_DIR, "CenturyGothic-Regular.ttf")
FONT_PRIMARY_BOLD = os.path.join(FONT_DIR, "CenturyGothic-Bold.ttf")

FONT_FALLBACK_REGULAR = os.path.join(FONT_DIR, "Fallback-Regular.ttf")
FONT_FALLBACK_BOLD = os.path.join(FONT_DIR, "Fallback-Bold.ttf")

MIN_ACCEPTABLE_FONT_SIZE = 8.0  # pt -- absolute floor kept for API compat

# Template body text colour #323232 (not pure black)
TEXT_COLOR = (50 / 255, 50 / 255, 50 / 255)
# Cover panel ink as stored in catalog templates (RGB 230,242,243).
# Page-13 pure white is separate — do not reuse that for the cover.
COVER_TEXT_COLOR = (230 / 255, 242 / 255, 243 / 255)
# Orange "click here" link colour from template (0xEE7B31)
TEXT_COLOR_ORANGE_LINK = (0xEE / 255, 0x7B / 255, 0x31 / 255)

# ---------------------------------------------------------------------------
# PAGE INDICES (0-based)
# ---------------------------------------------------------------------------
PAGE_COVER = 0
PAGE_VESSEL = 8                 # "Vessel Details"
PAGE_BESPOKE_PACKAGE = 12       # "Your Bespoke Package" -- financials + upgrades
PAGE_ADDED_EXTRAS = 13          # "Added Extras" -- overflow target
PAGE_CONTACT = 15               # "Your Contact"

# ---------------------------------------------------------------------------
# PAGE 1 -- COVER FIELDS
# Baselines measured from template span origins (not bbox.y1 guesses).
# ---------------------------------------------------------------------------
# Cover fields — always near-white on the photo panels
COVER_FIELDS = {
    "proposal_ref":  dict(bbox=(284.4, 39.3, 340, 45.7), origin=(284.4, 44.2), size=4.63, bold=False, color=COVER_TEXT_COLOR),
    "prepared_by":   dict(bbox=(256.8, 48.4, 295.6, 55.0), origin=(256.8, 53.4), size=4.63, bold=True, color=COVER_TEXT_COLOR),
    "quote_date":    dict(bbox=(227.3, 67.1, 264.1, 73.7), origin=(227.3, 72.3), size=4.63, bold=True, color=COVER_TEXT_COLOR),
    "client_name":   dict(bbox=(260.0, 82.9, 320, 89.2), origin=(260.0, 87.8), size=4.63, bold=False, color=COVER_TEXT_COLOR),
    "organisation":  dict(bbox=(260.7, 92.2, 340, 98.5), origin=(260.7, 97.1), size=4.63, bold=False, color=COVER_TEXT_COLOR),
    "telephone":     dict(bbox=(254.9, 101.6, 310, 107.9), origin=(254.9, 106.5), size=4.63, bold=False, color=COVER_TEXT_COLOR),
    "email":         dict(bbox=(243.4, 110.9, 320, 117.2), origin=(243.4, 115.8), size=4.63, bold=False, color=COVER_TEXT_COLOR),
    "event_type":    dict(bbox=(385.6, 39.8, 470, 46.2), origin=(385.6, 44.8), size=4.63, bold=False, color=COVER_TEXT_COLOR),
    "event_date":    dict(bbox=(410.4, 47.0, 470, 53.4), origin=(410.4, 52.0), size=4.63, bold=False, color=COVER_TEXT_COLOR),
    "event_timings": dict(bbox=(391.5, 113.1, 470, 119.4), origin=(391.5, 118.0), size=4.63, bold=False, color=COVER_TEXT_COLOR),
    "guest_range":   dict(bbox=(391.0, 134.4, 420, 140.7), origin=(391.0, 139.3), size=4.63, bold=False, color=COVER_TEXT_COLOR),
    "guest_quote_n": dict(bbox=(435.5, 141.3, 441, 147.9), origin=(435.5, 146.5), size=4.63, bold=True, max_width=6.5, color=COVER_TEXT_COLOR),
}

# ---------------------------------------------------------------------------
# PAGE 9 -- VESSEL PROFILES
# Map vessel ids from the payload to single-page PDF profiles. Drop real
# profile PDFs into assets/vessels/ (same page size as the template).
# ---------------------------------------------------------------------------
VESSEL_PROFILES = {
    "weott_i": os.path.join(VESSEL_DIR, "weott_i.pdf"),
    "avon_tour": os.path.join(VESSEL_DIR, "avon_tour.pdf"),
    "london_rose": os.path.join(VESSEL_DIR, "london_rose.pdf"),
}
VESSEL_DEFAULT = "weott_i"

# ---------------------------------------------------------------------------
# PAGE 13 -- FINANCIALS (right-aligned inside the orange summary table)
# ---------------------------------------------------------------------------
FINANCIAL_FIELDS = {
    "pkg_guests": dict(bbox=(115, 89.5, 135, 95.5), size=4.16, bold=True, align="center", color=(1, 1, 1)),
    "pkg_cost":   dict(bbox=(195, 89.5, 226, 95.5), size=4.16, bold=True, align="right", right_x=225.9, y=94.7, color=(1, 1, 1)),
    "pkg_vat":    dict(bbox=(195, 119.9, 226, 125.8), size=4.16, bold=True, align="right", right_x=225.4, y=125.1, color=(1, 1, 1)),
    "pkg_total":  dict(bbox=(195, 130.5, 226, 136.4), size=4.16, bold=True, align="right", right_x=225.3, y=135.7, color=(1, 1, 1)),
}

# ---------------------------------------------------------------------------
# PAGE 13 -- "Consider upgrading..." column (right-hand side)
# ---------------------------------------------------------------------------
UPGRADE_CATALOGUE = [
    dict(id="drink_tokens",        label="Drink tokens - £7.50 per token"),
    dict(id="unlimited_drinks",    label="Unlimited drinks for 4 hrs - £50.00 per guest"),
    dict(id="street_food_upgrade", label="Upgrade to street food station - additional £3.50 per guest"),
    dict(id="mingling_guide",      label="Mingling tour guide - from £420.00"),
    dict(id="live_dj",             label="Live DJ - from £500.00"),
    dict(id="karaoke",             label="Karaoke - from £550.00"),
    dict(id="saxophonist",         label="Saxophonist - from £550.00"),
    dict(id="acoustic_artist",     label="Acoustic artist - from £650.00"),
    dict(id="jazz_sax_duo",        label="Jazz and sax duo - from £650.00"),
    dict(id="other_live_music",    label="Other live music - options from £550.00"),
    dict(id="photo_booth",         label="Photo booth - from £650.00"),
    dict(id="casino_table",        label="Casino table with croupier - from £700.00"),
    dict(id="close_up_magician",   label="Close up magician - from £700.00"),
    dict(id="social_highlight_reel", label="Social media highlight reel - £450.00"),
    dict(id="branded_vessel_flag", label="Branded vessel flag - £150.00"),
    dict(id="logo_bunting",        label="Bespoke logo bunting - from £230.00"),
    dict(id="extra_hour",          label="Additional hour on board - from £650.00"),
]

UPGRADE_LIST = dict(
    page=PAGE_BESPOKE_PACKAGE,
    # clear_zone MUST start below the full instructional header (never redact it)
    clear_zone=(365, 90, 481, 240),
    bullet_x=369.6,
    text_x=375.3,
    # Measured from last header baseline + UPGRADE_HEADER_GAP_PT
    first_baseline_y=104.2,
    header_baseline_y=84.2,
    header_bottom=85.6,
    row_pitch=8.4,
    bullet_size=4.0,
    text_size=4.7,
    max_width=105,
    bold=False,
)

# Permanent layout gap between the instructional header baseline and the first
# Added Extras bullet. Conditional inclusion must never move the header.
UPGRADE_HEADER_GAP_PT = 20.0
UPGRADE_HEADER_TEXT = (
    "Consider upgrading your bespoke package to the left with the below items..."
)

# ---------------------------------------------------------------------------
# PAGE 13 -- Bespoke package description columns
# ---------------------------------------------------------------------------
PACKAGE_COLUMNS = [
    dict(name="venue_and_management", x=24.2, text_x=28.6, top_y=164.2, max_y=263.5, width=100),
    dict(name="entertainment_and_decor", x=130.3, text_x=134.7, top_y=164.1, max_y=263.5, width=98),
    dict(name="stationery_and_catering", x=249.0, text_x=254.5, top_y=164.0, max_y=263.5, width=98),
]
PACKAGE_ROW_PITCH = 7.2
PACKAGE_HEADING_GAP = 5.5
PACKAGE_TEXT_SIZE = 4.68
PACKAGE_HEADING_BOLD = False

# Stops above the "Click here to view our seasonal mood board" line (~y=264.1)
PACKAGE_CLEAR_ZONE = (22.0, 156.0, 360.0, 263.8)

# Menu / mood-board link hotspots on Page 13 (orange "click here" spans)
# uri in payload.menuLinks overrides these defaults when present.
MENU_LINK_TARGETS = {
    # barbecue / primary food menu "click here" in stationery_and_catering column
    "food_menu": dict(
        click_bbox=(310.9, 242.7, 332.9, 249.1),
        label_bbox=(259.7, 248.4, 301.6, 254.8),
        default_uri=None,  # not a real link in the stock template — we create one
    ),
    # street-food upgrade "click here" (only relevant if that upgrade row is shown;
    # kept for URI rewriting if the span survives)
    "street_food_menu": dict(
        click_bbox=(413.9, 113.4, 435.9, 119.8),
        default_uri=None,
    ),
    "mood_board": dict(
        click_bbox=(131.2, 264.1, 153.9, 270.5),
        default_uri="https://drive.google.com/file/d/14oh2y9yaorz4Rds8jDh6VQx1Q7bX2xzt/view",
    ),
}

# ---------------------------------------------------------------------------
# PAGE 16 -- CONTACT (measured from template.pdf page 15)
# ---------------------------------------------------------------------------
CONTACT_FIELDS = {
    "contact_name":  dict(bbox=(22.7, 243.1, 120, 249.2), origin=(22.7, 248.0), size=5.0, bold=True, page=PAGE_CONTACT),
    "contact_title": dict(bbox=(22.7, 251.7, 140, 257.8), origin=(22.7, 256.6), size=5.0, bold=True, page=PAGE_CONTACT, color=(0.89, 0.51, 0.21)),
    "contact_phone": dict(bbox=(274.4, 36.3, 340, 43.5), origin=(274.4, 42.1), size=6.0, bold=False, page=PAGE_CONTACT),
    # Email is split across three spans in the template; clear the whole value zone
    # after "E: " and redraw as one string.
    "contact_email": dict(bbox=(202.9, 44.8, 340, 53.0), origin=(202.9, 51.0), size=6.0, bold=False, page=PAGE_CONTACT, prefix="E: "),
}
