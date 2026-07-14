"""
vessel.py
---------
Page 9 "Vessel Details" page-swap protocol.

Staff previously deleted the generic vessel profile and inserted the
vessel-specific PDF (WEOTT I / Avon Tour / London Rose). This module does
the same: replace template page 9 with the matching single-page profile
from assets/vessels/.
"""

import os

import fitz

import config


def swap_vessel_page(doc: "fitz.Document", vessel_id: str, warnings: list, page_index=None) -> bool:
    """
    Replace the vessel details page with the profile PDF for `vessel_id`.
    Returns True if a swap was performed.
    """
    if not vessel_id:
        vessel_id = config.VESSEL_DEFAULT

    key = str(vessel_id).strip().lower().replace(" ", "_").replace("-", "_")
    aliases = {
        "weott": "weott_i",
        "weotti": "weott_i",
        "weott1": "weott_i",
        "avon": "avon_tour",
        "rose": "london_rose",
        "londonrose": "london_rose",
    }
    key = aliases.get(key, key)

    path = config.VESSEL_PROFILES.get(key)
    if not path or not os.path.exists(path):
        warnings.append(
            type("ValidationWarning", (), {"field": "vessel", "message": (
                f"Vessel profile '{vessel_id}' not found under assets/vessels/ -- "
                f"leaving vessel page unchanged. Known ids: {list(config.VESSEL_PROFILES)}"
            )})()
        )
        return False

    profile = fitz.open(path)
    try:
        if profile.page_count < 1:
            warnings.append(
                type("ValidationWarning", (), {"field": "vessel", "message": (
                    f"Vessel profile '{path}' has no pages."
                )})()
            )
            return False

        target = page_index if page_index is not None else config.PAGE_VESSEL
        doc.insert_pdf(profile, from_page=0, to_page=0, start_at=target)
        doc.delete_page(target + 1)
    finally:
        profile.close()

    return True
