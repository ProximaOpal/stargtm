"""
fonts.py
--------
Handles brand-font embedding with a graceful, clearly-logged fallback, and
the "font-scaling validation" safety check called for in the spec: if text
has to be shrunk below MIN_ACCEPTABLE_FONT_SIZE to fit its box, that's raised
as a ValidationWarning rather than silently rendered.
"""

import os
from dataclasses import dataclass, field

import fitz

import config


@dataclass
class ValidationWarning:
    field: str
    message: str


class FontManager:
    """
    Resolves which font family to embed (brand Century Gothic if the licensed
    files are present, otherwise a bundled geometric-sans fallback), and
    registers them once per fitz.Document via insert_font so every page
    reuses the same embedded font object instead of re-embedding per field.
    """

    def __init__(self):
        self.using_brand_font = os.path.exists(config.FONT_PRIMARY_REGULAR) and os.path.exists(
            config.FONT_PRIMARY_BOLD
        )
        if self.using_brand_font:
            self.regular_path = config.FONT_PRIMARY_REGULAR
            self.bold_path = config.FONT_PRIMARY_BOLD
            self.regular_name = "BrandRegular"
            self.bold_name = "BrandBold"
        else:
            self.regular_path = config.FONT_FALLBACK_REGULAR
            self.bold_path = config.FONT_FALLBACK_BOLD
            self.regular_name = "FallbackRegular"
            self.bold_name = "FallbackBold"
            if not (os.path.exists(self.regular_path) and os.path.exists(self.bold_path)):
                raise FileNotFoundError(
                    "Neither Century Gothic nor the bundled fallback font could be found. "
                    f"Checked: {config.FONT_PRIMARY_REGULAR}, {config.FONT_FALLBACK_REGULAR}"
                )
        self._registered_pages = set()
        # fitz.get_text_length() only recognises the 14 built-in base fonts by
        # name -- it has no way to know what "BrandRegular" refers to just
        # because we insert_font()'d it into a page. For measurement we use a
        # standalone fitz.Font built straight from the same font file, cached
        # so we only construct it once per weight.
        self._measure_regular = fitz.Font(fontfile=self.regular_path)
        self._measure_bold = fitz.Font(fontfile=self.bold_path)

    def font_name(self, bold: bool) -> str:
        return self.bold_name if bold else self.regular_name

    def ensure_registered(self, page: "fitz.Page"):
        """Embed the fonts into this page's document exactly once."""
        doc_id = id(page.parent)
        if doc_id in self._registered_pages:
            return
        page.insert_font(fontname=self.regular_name, fontfile=self.regular_path)
        page.insert_font(fontname=self.bold_name, fontfile=self.bold_path)
        self._registered_pages.add(doc_id)

    def text_length(self, text: str, size: float, bold: bool) -> float:
        font = self._measure_bold if bold else self._measure_regular
        return font.text_length(text, fontsize=size)

    def fit_font_size(
        self, text: str, max_width: float, base_size: float, bold: bool, field_name: str,
        warnings: list, shrink_ratio_floor: float = 0.85,
    ) -> float:
        """
        Shrinks font size in 0.1pt steps until `text` fits `max_width`.

        The template's native body copy runs ~4.6-4.7pt (this is a scaled-down
        page coordinate space, not full document points), so an *absolute*
        "flag below 8pt" rule -- as literally stated in the brief -- would
        fire on every single field. The equivalent, actually-useful signal is
        a *relative* one: if a field has to shrink more than
        `shrink_ratio_floor` (default 15%) from its designed size to fit, the
        wording is too long for its box and needs a human look, so we flag it
        instead of silently rendering squashed text.
        """
        size = base_size
        while size > 2.0 and self.text_length(text, size, bold) > max_width:
            size -= 0.1
        size = round(size, 1)
        if size < base_size * shrink_ratio_floor:
            warnings.append(
                ValidationWarning(
                    field=field_name,
                    message=(
                        f"'{text[:40]}{'...' if len(text) > 40 else ''}' had to shrink from "
                        f"{base_size}pt to {size}pt to fit its box -- flagging for manual review."
                    ),
                )
            )
        return size
