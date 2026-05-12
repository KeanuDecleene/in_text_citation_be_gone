from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

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
SUSPECT_PAIRED_QUESTION_RE = re.compile(
    r"(?:(?<=^)|(?<=[\s(\[{]))\?([^\?\n]{1,80}?)\?(?=(?:[\s)\]},.;:!?]|$))"
)
INLINE_SUSPECT_PAIRED_QUESTION_RE = re.compile(
    r"(?<=\w)\?([A-Za-z0-9][^\?\n]{0,80}?)\?(?=(?:[\s)\]},.;:!?]|$))"
)
CONTRACTION_QUESTION_RE = re.compile(
    r"(?i)\b([A-Za-z]+)\?(s|t|re|ve|ll|d|m)\b"
)
JOINED_CLAUSE_QUESTION_RE = re.compile(r"(?<=[\w)\]])\?(?=\w)")
PDF_SAFE_PUNCTUATION_MAP = str.maketrans(
    {
        "\u2018": "'",
        "\u2019": "'",
        "\u201a": "'",
        "\u201b": "'",
        "\u2032": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u201e": '"',
        "\u201f": '"',
        "\u2033": '"',
        "\u2010": "-",
        "\u2011": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2026": "...",
        "\u00a0": " ",
        "\u00ad": "-",
        "\u0091": "'",
        "\u0092": "'",
        "\u0093": '"',
        "\u0094": '"',
        "\u0096": "-",
        "\u0097": "-",
        "\u0085": "...",
    }
)
UNICODE_FONT_VARIANTS = {
    (False, False): Path(r"C:\Windows\Fonts\segoeui.ttf"),
    (True, False): Path(r"C:\Windows\Fonts\segoeuib.ttf"),
    (False, True): Path(r"C:\Windows\Fonts\segoeuii.ttf"),
    (True, True): Path(r"C:\Windows\Fonts\segoeuiz.ttf"),
}


class PDFCleaningError(Exception):
    """Raised when a PDF cannot be processed safely."""


@dataclass(frozen=True)
class TextStyle:
    fontname: str
    fontsize: float
    color: tuple[float, float, float]
    lineheight: float
    fontfile: str | None = None


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

        text = "".join(span.get("text", "") for span in spans).strip()
        if text:
            line_texts.append(MULTI_SPACE_RE.sub(" ", text))

    if not line_texts:
        return ""

    merged_lines = [line_texts[0]]
    for line in line_texts[1:]:
        if merged_lines[-1].endswith("-") and line[:1].islower():
            merged_lines[-1] = f"{merged_lines[-1][:-1]}{line.lstrip()}"
        else:
            merged_lines.append(line.lstrip())

    return "\n".join(merged_lines).strip()


def _is_reference_heading(text: str) -> bool:
    normalized = re.sub(r"[^A-Za-z ]+", "", text).strip().lower()
    return normalized in REFERENCE_HEADINGS


def _style_from_block(block: dict) -> TextStyle:
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = span.get("text", "").strip()
            if not text:
                continue

            fontname, fontfile = _resolve_font_for_replacement(
                span.get("font", "Times-Roman")
            )

            return TextStyle(
                fontname=fontname,
                fontsize=max(float(span.get("size", 12.0)), 8.0),
                color=_rgb_tuple_from_int(int(span.get("color", 0))),
                lineheight=_lineheight_from_block(
                    block, max(float(span.get("size", 12.0)), 8.0)
                ),
                fontfile=fontfile,
            )

    return TextStyle(
        fontname="Times-Roman",
        fontsize=12.0,
        color=(0, 0, 0),
        lineheight=1.2,
    )


def _lineheight_from_block(block: dict, fontsize: float) -> float:
    line_boxes = [
        fitz.Rect(line["bbox"])
        for line in block.get("lines", [])
        if any(span.get("text", "").strip() for span in line.get("spans", []))
    ]
    if not line_boxes:
        return 1.2

    if len(line_boxes) == 1:
        return max(line_boxes[0].height / fontsize, 1.0)

    distances = [
        line_boxes[index + 1].y0 - line_boxes[index].y0
        for index in range(len(line_boxes) - 1)
        if line_boxes[index + 1].y0 > line_boxes[index].y0
    ]
    if not distances:
        return max(line_boxes[0].height / fontsize, 1.0)

    average_distance = sum(distances) / len(distances)
    return max(average_distance / fontsize, 1.0)


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


def _resolve_font_for_replacement(original_font: str) -> tuple[str, str | None]:
    lower_name = original_font.lower()
    is_bold = "bold" in lower_name
    is_italic = "italic" in lower_name or "oblique" in lower_name

    unicode_font_path = UNICODE_FONT_VARIANTS[(is_bold, is_italic)]
    if unicode_font_path.exists():
        alias = f"citation-cleaner-{'b' if is_bold else 'r'}{'i' if is_italic else 'n'}"
        return alias, str(unicode_font_path)

    return _map_font_name(original_font), None


def _rgb_tuple_from_int(color_value: int) -> tuple[float, float, float]:
    red = (color_value >> 16) & 255
    green = (color_value >> 8) & 255
    blue = color_value & 255
    return (red / 255, green / 255, blue / 255)


def _repair_extracted_text(text: str) -> str:
    repaired = text.translate(PDF_SAFE_PUNCTUATION_MAP)
    repaired = SUSPECT_PAIRED_QUESTION_RE.sub(r"'\1'", repaired)
    repaired = INLINE_SUSPECT_PAIRED_QUESTION_RE.sub(r" '\1'", repaired)
    repaired = CONTRACTION_QUESTION_RE.sub(r"\1'\2", repaired)
    repaired = JOINED_CLAUSE_QUESTION_RE.sub("-", repaired)
    repaired = MULTI_SPACE_RE.sub(" ", repaired)
    repaired = re.sub(r" \n", "\n", repaired)
    return repaired


def _normalize_text_for_pdf_font(text: str) -> str:
    return _repair_extracted_text(text)


def _write_replacement(page: fitz.Page, replacement: BlockReplacement) -> None:
    text = _repair_extracted_text(replacement.text)
    fallback_text = _normalize_text_for_pdf_font(replacement.text)
    rect = fitz.Rect(
        replacement.rect.x0,
        replacement.rect.y0 - 1,
        replacement.rect.x1,
        replacement.rect.y1 + 2,
    )

    for scale in (1.0, 0.98, 0.95, 0.92, 0.88, 0.84):
        result = page.insert_textbox(
            rect,
            text,
            fontname=replacement.style.fontname,
            fontfile=replacement.style.fontfile,
            fontsize=replacement.style.fontsize * scale,
            color=replacement.style.color,
            align=fitz.TEXT_ALIGN_LEFT,
            lineheight=replacement.style.lineheight,
        )
        if result >= 0:
            return

    page.insert_textbox(
        rect,
        fallback_text,
        fontname="Times-Roman",
        fontsize=max(replacement.style.fontsize * 0.8, 8.0),
        color=replacement.style.color,
        align=fitz.TEXT_ALIGN_LEFT,
        lineheight=replacement.style.lineheight,
    )
