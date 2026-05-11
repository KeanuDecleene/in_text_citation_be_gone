from __future__ import annotations

import re
from dataclasses import dataclass

import fitz

REFERENCE_HEADINGS = {
    "references",
    "bibliography",
    "works cited",
    "literature cited",
}

NUMERIC_BRACKET_CITATION_RE = re.compile(
    r"\[(?:\s*\d+\s*(?:[-,;]\s*\d+\s*)*)\]"
)
NARRATIVE_YEAR_RE = re.compile(
    r"(?P<author>\b[A-Z][A-Za-z'`-]+(?:\s+(?:and|&)\s+[A-Z][A-Za-z'`-]+|\s+et al\.)?)"
    r"\s*\((?P<year>(?:19|20)\d{2}[a-z]?)(?:,\s*(?:p|pp)\.?\s*\d+(?:[-–]\d+)?)?\)"
)
PARENTHETICAL_CITATION_RE = re.compile(
    r"\((?=[^)]*\b(?:19|20)\d{2}[a-z]?\b)(?:[^()]|(?<=\b)(?:e\.g\.|i\.e\.|et al\.))*\)"
)
MULTI_SPACE_RE = re.compile(r"[ \t]{2,}")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
EMPTY_BRACKETS_RE = re.compile(r"(\(\s*\)|\[\s*\])")
BROKEN_PUNCT_RE = re.compile(r"([,;:])([,;:.!?])")


class PDFCleaningError(Exception):
    """Raised when a PDF cannot be processed safely."""


@dataclass(frozen=True)
class TextStyle:
    fontname: str
    fontsize: float
    color: tuple[float, float, float]


@dataclass(frozen=True)
class BlockReplacement:
    rect: fitz.Rect
    text: str
    style: TextStyle


def strip_citations_from_text(text: str) -> str:
    cleaned = text
    cleaned = NARRATIVE_YEAR_RE.sub(lambda match: match.group("author"), cleaned)
    cleaned = PARENTHETICAL_CITATION_RE.sub("", cleaned)
    cleaned = NUMERIC_BRACKET_CITATION_RE.sub("", cleaned)
    cleaned = EMPTY_BRACKETS_RE.sub("", cleaned)
    cleaned = SPACE_BEFORE_PUNCT_RE.sub(r"\1", cleaned)
    cleaned = BROKEN_PUNCT_RE.sub(r"\2", cleaned)
    cleaned = MULTI_SPACE_RE.sub(" ", cleaned)
    cleaned = re.sub(r"\s+\n", "\n", cleaned)
    cleaned = re.sub(r"\n\s+", "\n", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


def clean_pdf_bytes(pdf_bytes: bytes) -> bytes:
    try:
        document = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as exc:  # pragma: no cover - PyMuPDF-specific parser failure
        raise PDFCleaningError("The uploaded file could not be parsed as a PDF.") from exc

    try:
        reached_references = False

        for page in document:
            replacements: list[BlockReplacement] = []

            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue

                block_text = _extract_block_text(block)
                if not block_text.strip():
                    continue

                if _is_reference_heading(block_text):
                    reached_references = True
                    continue

                if reached_references:
                    continue

                cleaned_text = strip_citations_from_text(block_text)
                if cleaned_text == block_text:
                    continue

                rect = fitz.Rect(block["bbox"])
                if rect.is_empty or rect.width <= 0 or rect.height <= 0:
                    continue

                replacements.append(
                    BlockReplacement(
                        rect=rect,
                        text=cleaned_text,
                        style=_style_from_block(block),
                    )
                )

            for replacement in replacements:
                page.add_redact_annot(replacement.rect, fill=(1, 1, 1))

            if replacements:
                page.apply_redactions()
                for replacement in replacements:
                    _write_replacement(page, replacement)

        return document.tobytes(garbage=4, deflate=True)
    finally:
        document.close()


def _extract_block_text(block: dict) -> str:
    line_texts: list[str] = []

    for line in block.get("lines", []):
        spans = line.get("spans", [])
        if not spans:
            continue

        text = "".join(span.get("text", "") for span in spans).rstrip()
        if text:
            line_texts.append(text)

    if not line_texts:
        return ""

    merged = line_texts[0]
    for line in line_texts[1:]:
        if merged.endswith("-") and line[:1].islower():
            merged = f"{merged[:-1]}{line.lstrip()}"
        else:
            merged = f"{merged} {line.lstrip()}"

    return MULTI_SPACE_RE.sub(" ", merged).strip()


def _is_reference_heading(text: str) -> bool:
    normalized = re.sub(r"[^A-Za-z ]+", "", text).strip().lower()
    return normalized in REFERENCE_HEADINGS


def _style_from_block(block: dict) -> TextStyle:
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = span.get("text", "").strip()
            if not text:
                continue

            return TextStyle(
                fontname=_map_font_name(span.get("font", "Times-Roman")),
                fontsize=max(float(span.get("size", 12.0)), 8.0),
                color=_rgb_tuple_from_int(int(span.get("color", 0))),
            )

    return TextStyle(fontname="Times-Roman", fontsize=12.0, color=(0, 0, 0))


def _map_font_name(original_font: str) -> str:
    lower_name = original_font.lower()

    if "courier" in lower_name:
        family = "Courier"
    elif any(name in lower_name for name in ("helvetica", "arial", "calibri", "sans")):
        family = "Helvetica"
    else:
        family = "Times"

    is_bold = "bold" in lower_name
    is_italic = "italic" in lower_name or "oblique" in lower_name

    if family == "Times":
        if is_bold and is_italic:
            return "Times-BoldItalic"
        if is_bold:
            return "Times-Bold"
        if is_italic:
            return "Times-Italic"
        return "Times-Roman"

    if family == "Helvetica":
        if is_bold and is_italic:
            return "Helvetica-BoldOblique"
        if is_bold:
            return "Helvetica-Bold"
        if is_italic:
            return "Helvetica-Oblique"
        return "Helvetica"

    if is_bold and is_italic:
        return "Courier-BoldOblique"
    if is_bold:
        return "Courier-Bold"
    if is_italic:
        return "Courier-Oblique"
    return "Courier"


def _rgb_tuple_from_int(color_value: int) -> tuple[float, float, float]:
    red = (color_value >> 16) & 255
    green = (color_value >> 8) & 255
    blue = color_value & 255
    return (red / 255, green / 255, blue / 255)


def _write_replacement(page: fitz.Page, replacement: BlockReplacement) -> None:
    rect = fitz.Rect(
        replacement.rect.x0,
        replacement.rect.y0 - 1,
        replacement.rect.x1,
        replacement.rect.y1 + 2,
    )

    for scale in (1.0, 0.98, 0.95, 0.92, 0.88, 0.84):
        result = page.insert_textbox(
            rect,
            replacement.text,
            fontname=replacement.style.fontname,
            fontsize=replacement.style.fontsize * scale,
            color=replacement.style.color,
            align=fitz.TEXT_ALIGN_LEFT,
        )
        if result >= 0:
            return

    page.insert_textbox(
        rect,
        replacement.text,
        fontname="Times-Roman",
        fontsize=max(replacement.style.fontsize * 0.8, 8.0),
        color=replacement.style.color,
        align=fitz.TEXT_ALIGN_LEFT,
    )
