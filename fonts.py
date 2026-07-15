"""
fonts.py
--------
Handles brand-font embedding with a graceful, clearly-logged fallback, and
the font-scaling validation safety check.
"""

import os
from dataclasses import dataclass

import fitz

import config


@dataclass
class ValidationWarning:
    field: str
    message: str


_FONT_MGR_SINGLETON = None


def get_font_manager() -> "FontManager":
    """Process-wide FontManager (font file IO + fitz.Font construction is costly)."""
    global _FONT_MGR_SINGLETON
    if _FONT_MGR_SINGLETON is None:
        _FONT_MGR_SINGLETON = FontManager()
    return _FONT_MGR_SINGLETON


def _font_embeds_digits(path: str) -> bool:
    """True if insert_font/insert_text can round-trip ASCII digits (subset fonts often can't)."""
    if not path or not os.path.exists(path):
        return False
    try:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_font(fontname="Probe", fontfile=path)
        page.insert_text((20, 40), "0123456789", fontname="Probe", fontsize=10)
        text = page.get_text("text")
        doc.close()
        return all(ch in text for ch in "0123456789")
    except Exception:
        return False


class FontManager:
    """
    Resolves which font family to embed (brand Century Gothic if the files are
    present, otherwise a bundled geometric-sans fallback), and registers them
    once per document.
    """

    def __init__(self):
        has_regular = os.path.exists(config.FONT_PRIMARY_REGULAR)
        has_bold = os.path.exists(config.FONT_PRIMARY_BOLD)

        if has_regular:
            self.regular_path = config.FONT_PRIMARY_REGULAR
            self.regular_name = "BrandRegular"
            self.using_brand_font = True
        else:
            self.regular_path = config.FONT_FALLBACK_REGULAR
            self.regular_name = "FallbackRegular"
            self.using_brand_font = False

        if has_bold and _font_embeds_digits(config.FONT_PRIMARY_BOLD):
            self.bold_path = config.FONT_PRIMARY_BOLD
            self.bold_name = "BrandBold"
        elif os.path.exists(config.FONT_FALLBACK_BOLD):
            # Template-extracted CG Bold subsets often lack embeddable digit
            # outlines — use Fallback Bold so finance cells stay deep/white.
            self.bold_path = config.FONT_FALLBACK_BOLD
            self.bold_name = "FallbackBold"
        elif has_regular:
            self.bold_path = config.FONT_PRIMARY_REGULAR
            self.bold_name = "BrandBoldAsRegular"
        else:
            self.bold_path = config.FONT_FALLBACK_BOLD
            self.bold_name = "FallbackBold"

        if not (os.path.exists(self.regular_path) and os.path.exists(self.bold_path)):
            raise FileNotFoundError(
                "Neither Century Gothic nor the bundled fallback font could be found. "
                f"Checked: {config.FONT_PRIMARY_REGULAR}, {config.FONT_FALLBACK_REGULAR}"
            )

        self._registered_docs = set()
        self._measure_regular = fitz.Font(fontfile=self.regular_path)
        self._measure_bold = fitz.Font(fontfile=self.bold_path)

    def font_name(self, bold: bool) -> str:
        return self.bold_name if bold else self.regular_name

    def ensure_registered(self, page: "fitz.Page"):
        doc_id = id(page.parent)
        if doc_id in self._registered_docs:
            return
        page.insert_font(fontname=self.regular_name, fontfile=self.regular_path)
        page.insert_font(fontname=self.bold_name, fontfile=self.bold_path)
        self._registered_docs.add(doc_id)

    def reset_doc_registry(self):
        """Call after a document is closed so the next doc re-embeds fonts."""
        self._registered_docs.clear()

    def text_length(self, text: str, size: float, bold: bool) -> float:
        font = self._measure_bold if bold else self._measure_regular
        return font.text_length(text, fontsize=size)

    def fit_font_size(
        self, text: str, max_width: float, base_size: float, bold: bool, field_name: str,
        warnings: list, shrink_ratio_floor: float = 0.85,
    ) -> float:
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
