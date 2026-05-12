from __future__ import annotations

import fitz

from app.services.citation_cleaner import (
    BlockReplacement,
    TextStyle,
    _extract_block_text,
    _normalize_text_for_pdf_font,
    _write_replacement,
    clean_pdf_bytes,
    strip_citations_from_text,
)


def test_strip_citations_from_text_handles_common_patterns() -> None:
    source = (
        "Evidence improved over time (Smith, 2020; Jones, 2021). "
        "Johnson (2022) argued the same point [12]."
    )

    cleaned = strip_citations_from_text(source)

    assert "(Smith, 2020; Jones, 2021)" not in cleaned
    assert "(2022)" not in cleaned
    assert "[12]" not in cleaned
    assert "Johnson argued the same point." in cleaned


def test_extract_block_text_preserves_line_breaks_for_stable_reflow() -> None:
    block = {
        "lines": [
            {"bbox": (72, 72, 200, 84), "spans": [{"text": "First line of text"}]},
            {"bbox": (72, 86, 200, 98), "spans": [{"text": "Second line of text"}]},
            {"bbox": (72, 100, 200, 112), "spans": [{"text": "hyphen-"}]},
            {"bbox": (72, 114, 200, 126), "spans": [{"text": "ated ending"}]},
        ]
    }

    extracted = _extract_block_text(block)

    assert extracted == "First line of text\nSecond line of text\nhyphenated ending"


def test_clean_pdf_bytes_preserves_images_and_reference_section() -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 24, 24), 0)
    pixmap.clear_with(0xCC6633)
    page.insert_text(
        (72, 96),
        "This paragraph cites a source (Smith, 2020) but should stay readable.",
        fontname="Times-Roman",
        fontsize=12,
    )
    page.insert_text(
        (72, 120),
        "Johnson (2021) also supports the claim.",
        fontname="Times-Roman",
        fontsize=12,
    )
    page.insert_text((72, 168), "References", fontname="Times-Bold", fontsize=14)
    page.insert_text(
        (72, 192),
        "Smith, J. (2020). Example article title.",
        fontname="Times-Roman",
        fontsize=12,
    )
    page.insert_image(fitz.Rect(72, 220, 120, 268), pixmap=pixmap)

    original_bytes = document.tobytes()
    document.close()

    cleaned_bytes = clean_pdf_bytes(original_bytes)
    cleaned_document = fitz.open(stream=cleaned_bytes, filetype="pdf")
    cleaned_page = cleaned_document[0]
    cleaned_text = cleaned_page.get_text()

    assert "(Smith, 2020)" not in cleaned_text
    assert "(2021)" not in cleaned_text
    assert "Johnson also supports the claim." in cleaned_text
    assert "Smith, J. (2020). Example article title." in cleaned_text
    assert len(cleaned_page.get_images()) == 1
    assert cleaned_document.page_count == 1

    cleaned_document.close()


def test_normalize_text_for_pdf_font_converts_smart_punctuation() -> None:
    text = "She said \u201cread this\u201d, don\u2019t skim it \u2014 ever\u2026"

    normalized = _normalize_text_for_pdf_font(text)

    assert normalized == 'She said "read this", don\'t skim it - ever...'


def test_normalize_text_for_pdf_font_repairs_suspicious_question_mark_placeholders() -> None:
    text = (
        "?with whom? in the responsibility conditions. "
        "the so-called?black-box? AI systems. "
        "developers?let alone further users. "
        "don?t skim it. "
        "you do it?if you are the agent."
    )

    normalized = _normalize_text_for_pdf_font(text)

    assert "'with whom'" in normalized
    assert "so-called 'black-box' AI systems" in normalized
    assert "developers-let alone further users" in normalized
    assert "don't skim it" in normalized
    assert "you do it-if you are the agent" in normalized


def test_write_replacement_preserves_readable_quotes_in_cleaned_output() -> None:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    replacement = BlockReplacement(
        rect=fitz.Rect(72, 72, 500, 140),
        text="She said \u201cread this\u201d, don\u2019t skim it \u2014 ever\u2026",
        style=TextStyle(
            fontname="Times-Roman",
            fontsize=12,
            color=(0, 0, 0),
            lineheight=1.2,
        ),
    )
    _write_replacement(page, replacement)
    cleaned_text = page.get_text().strip()

    assert "?" not in cleaned_text
    assert '"read this"' in cleaned_text
    assert "don't skim it - ever..." in cleaned_text

    document.close()
