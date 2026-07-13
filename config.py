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

# ---------------------------------------------------------------------------
# FONTS
# ---------------------------------------------------------------------------
# Brand-correct pairing. If the licensed Century Gothic .ttf files are placed
# here, the engine automatically prefers them over the fallback. Century
# Gothic is a commercial font (Monotype) and is NOT bundled in this repo for
# licensing reasons -- drop the two files in to unlock true brand fidelity.
FONT_PRIMARY_REGULAR = os.path.join(FONT_DIR, "CenturyGothic-Regular.ttf")
FONT_PRIMARY_BOLD = os.path.join(FONT_DIR, "CenturyGothic-Bold.ttf")

# Bundled, licence-clean (SIL OFL) geometric sans used automatically when the
# primary brand font isn't present. Visually closer to Century Gothic than
# Helvetica (which is what the previous version of this tool fell back to).
FONT_FALLBACK_REGULAR = os.path.join(FONT_DIR, "Fallback-Regular.ttf")
FONT_FALLBACK_BOLD = os.path.join(FONT_DIR, "Fallback-Bold.ttf")

MIN_ACCEPTABLE_FONT_SIZE = 8.0  # pt -- below this, flag for manual review (per spec)

# ---------------------------------------------------------------------------
# PAGE INDICES (0-based)
# ---------------------------------------------------------------------------
PAGE_COVER = 0
PAGE_BESPOKE_PACKAGE = 12        # "Your Bespoke Package" -- financials + upgrades
PAGE_ADDED_EXTRAS = 13           # "Added Extras" -- overflow target
PAGE_CONTACT = 15                # "Your Contact"

# ---------------------------------------------------------------------------
# PAGE 1 -- COVER FIELDS
# bbox = region of the OLD value to redact. origin = baseline (x, y) for the
# NEW text, measured against the *original* baseline so replacement text
# sits on the exact same line as the template text it replaces.
# ---------------------------------------------------------------------------
COVER_FIELDS = {
    "proposal_ref":  dict(bbox=(284.4, 39.3, 340, 45.7), origin=(284.4, 44.8), size=4.63, bold=False),
    "prepared_by":   dict(bbox=(256.8, 48.4, 295.6, 55.0), origin=(256.8, 53.6), size=4.63, bold=True),
    "quote_date":    dict(bbox=(227.3, 67.1, 264.1, 73.7), origin=(227.3, 72.9), size=4.63, bold=True),
    "client_name":   dict(bbox=(260.0, 82.9, 320, 89.2), origin=(260.0, 88.4), size=4.63, bold=False),
    "organisation":  dict(bbox=(260.7, 92.2, 340, 98.5), origin=(260.7, 97.7), size=4.63, bold=False),
    "telephone":     dict(bbox=(254.9, 101.6, 310, 107.9), origin=(254.9, 107.1), size=4.63, bold=False),
    "email":         dict(bbox=(243.4, 110.9, 320, 117.2), origin=(243.4, 116.4), size=4.63, bold=False),
    "event_type":    dict(bbox=(385.6, 39.8, 470, 46.2), origin=(385.6, 45.4), size=4.63, bold=False),
    "event_date":    dict(bbox=(410.4, 47.0, 470, 53.4), origin=(410.4, 52.6), size=4.63, bold=False),
    "event_timings": dict(bbox=(391.5, 113.1, 470, 119.4), origin=(391.5, 118.6), size=4.63, bold=False),
    "guest_range":   dict(bbox=(391.0, 134.4, 420, 140.7), origin=(391.0, 139.9), size=4.63, bold=False),
    # max_width is the *real* available gap before the next static word
    # ("guests"), not the tight bbox measured for the old two-digit value --
    # using the bbox alone was forcing an unnecessary shrink whenever the
    # fallback font's digits render a fraction wider than the original.
    "guest_quote_n": dict(bbox=(435.5, 141.3, 441, 147.9), origin=(435.5, 147.1), size=4.63, bold=True, max_width=6.5),
}

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
# This is the master ORDERED catalogue of every possible upgrade item WEOTT
# offers, in the order they appear on the template, with its price label
# already formatted exactly as printed. `selectedUpgrades` in the incoming
# JSON is a list of these `id` values; anything not selected is dropped and
# everything below it shifts up so there's no gap (Conditional Inclusion).
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

# Geometry measured from the template's real bullet list (page 13, right col)
UPGRADE_LIST = dict(
    page=PAGE_BESPOKE_PACKAGE,
    # Zone that must be fully cleared before re-stacking (covers the whole
    # printed list, from the first bullet down to below the last one).
    clear_zone=(365, 88, 481, 240),
    bullet_x=369.6,
    text_x=375.3,
    first_baseline_y=97.2,   # baseline of the first bullet's text
    row_pitch=8.4,           # vertical distance between consecutive rows
    bullet_size=4.0,
    text_size=4.7,
    max_width=105,           # text column width in pt before wrapping
    bold=False,
)

# ---------------------------------------------------------------------------
# PAGE 13 -- Bespoke package description (left + centre columns). This is the
# "temperamental" area: 3 columns of bullet groups (Venue Hire / Entertainment
# / Stationery, etc.) whose combined length varies proposal to proposal.
# Rather than 30+ fixed bboxes, each column is a flow region; the Stacking
# Algorithm lays out bullet groups top-to-bottom and overflows to Page 14
# (Added Extras) if a column would run past `max_y`.
# ---------------------------------------------------------------------------
PACKAGE_COLUMNS = [
    dict(name="venue_and_management", x=24.2, text_x=28.6, top_y=164.2, max_y=270, width=100),
    dict(name="entertainment_and_decor", x=130.3, text_x=134.7, top_y=164.1, max_y=270, width=98),
    dict(name="stationery_and_catering", x=249.0, text_x=254.5, top_y=164.0, max_y=270, width=98),
]
PACKAGE_ROW_PITCH = 7.4       # body line pitch
PACKAGE_HEADING_GAP = 5.5     # extra gap consumed by a sub-heading line
PACKAGE_TEXT_SIZE = 4.68
PACKAGE_HEADING_BOLD = False

# ---------------------------------------------------------------------------
# PAGE 16 -- CONTACT
# ---------------------------------------------------------------------------
CONTACT_FIELDS = {
    "contact_phone": dict(bbox=(756, 106, 900, 113), origin=(756, 112.4), size=4.7, bold=False, page=PAGE_CONTACT),
    "contact_email": dict(bbox=(590, 116, 900, 123), origin=(590, 122.4), size=4.7, bold=False, page=PAGE_CONTACT),
    "contact_name":  dict(bbox=(64, 555, 200, 563), origin=(64, 562), size=5.2, bold=True, page=PAGE_CONTACT),
    "contact_title": dict(bbox=(64, 567, 260, 575), origin=(64, 574), size=4.7, bold=False, page=PAGE_CONTACT),
}
# NOTE: the contact-page coordinates above are placeholders pending a
# measurement pass identical to the one done for pages 1 and 13 (the supplied
# template renders "Katherine Bulaon / Client Relationship Manager" as part
# of a signature block whose exact bbox depends on name length). Run
# `tools/inspect_page.py 15` and adjust before relying on this in production.
