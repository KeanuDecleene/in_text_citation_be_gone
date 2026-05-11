from __future__ import annotations

import fitz

from app.services.citation_cleaner import clean_pdf_bytes, strip_citations_from_text


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
