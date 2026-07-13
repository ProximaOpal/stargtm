"""
cover_contact.py
----------------
Handlers for the two "simple field" pages: Page 1 (cover) and Page 16
(contact/relationship-manager sign-off). Both are just redact-and-replace
against a fixed field map, so they share one small module.
"""

import fitz

import config
from pdf_ops import draw_field


def fill_cover_page(doc: "fitz.Document", data: dict, font_mgr, warnings: list):
    page = doc[config.PAGE_COVER]
    font_mgr.ensure_registered(page)
    for field_name, spec in config.COVER_FIELDS.items():
        if field_name not in data:
            continue
        draw_field(page, spec, str(data[field_name]), font_mgr, warnings, field_name)


def fill_contact_page(doc: "fitz.Document", data: dict, font_mgr, warnings: list):
    for field_name, spec in config.CONTACT_FIELDS.items():
        if field_name not in data:
            continue
        page = doc[spec["page"]]
        font_mgr.ensure_registered(page)
        draw_field(page, spec, str(data[field_name]), font_mgr, warnings, field_name)
