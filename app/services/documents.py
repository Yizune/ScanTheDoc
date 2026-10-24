from __future__ import annotations

import difflib
import io
import re
from dataclasses import dataclass

import pymupdf
import pypdfium2 as pdfium
import pytesseract
from ftfy import fix_text
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pytesseract import Output

SUPPORTED_MEDIA_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/tiff",
    "image/webp",
}


@dataclass(slots=True)
class ExtractedDocument:
    text: str
    page_count: int


@dataclass(slots=True)
class PdfWord:
    text: str
    page: int
    x: float
    y: float
    width: float
    height: float


def normalize_text(text: str) -> str:
    return fix_text(text).strip()


def validate_upload(data: bytes, declared_type: str) -> str:
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    try:
        with Image.open(io.BytesIO(data)) as image:
            detected = image.format
            image.verify()
    except Exception as error:
        raise ValueError("Only valid PDF and image files are supported") from error
    media_type = Image.MIME.get(detected or "")
    if media_type not in SUPPORTED_MEDIA_TYPES:
        raise ValueError("Only PDF, PNG, JPEG, TIFF, and WebP files are supported")
    return media_type or declared_type


def extract_document(
    data: bytes, media_type: str, tesseract_cmd: str = ""
) -> ExtractedDocument:
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    if media_type != "application/pdf":
        with Image.open(io.BytesIO(data)) as image:
            text = pytesseract.image_to_string(image)
        return ExtractedDocument(text=normalize_text(text), page_count=1)

    reader = PdfReader(io.BytesIO(data))
    pages = [normalize_text(page.extract_text() or "") for page in reader.pages]
    if sum(len(page) for page in pages) < max(40, len(pages) * 15):
        pages = _ocr_pdf(data)
    return ExtractedDocument(
        text="\n\n".join(filter(None, pages)), page_count=len(reader.pages)
    )


def _ocr_pdf(data: bytes) -> list[str]:
    document = pdfium.PdfDocument(data)
    text = []
    for page in document:
        image = page.render(scale=2).to_pil()
        text.append(normalize_text(pytesseract.image_to_string(image)))
    return text


def merge_pdfs(items: list[bytes]) -> bytes:
    writer = PdfWriter()
    for item in items:
        writer.append(io.BytesIO(item))
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def parse_page_selection(selection: str, page_count: int) -> list[int]:
    pages: list[int] = []
    seen: set[int] = set()

    for part in selection.replace(" ", "").split(","):
        if not part:
            raise ValueError("Enter page numbers such as 1-3, 5")
        try:
            if "-" in part:
                start_text, end_text = part.split("-", 1)
                start = int(start_text)
                end = int(end_text)
                if start > end:
                    raise ValueError
                selected = range(start, end + 1)
            else:
                selected = [int(part)]
        except ValueError as error:
            raise ValueError("Enter page numbers such as 1-3, 5") from error

        for page in selected:
            if page < 1 or page > page_count:
                raise ValueError(f"Page {page} is outside this {page_count}-page PDF")
            if page not in seen:
                pages.append(page)
                seen.add(page)

    return pages


def extract_pdf_pages(data: bytes, pages: list[int]) -> bytes:
    reader = PdfReader(io.BytesIO(data))
    writer = PdfWriter()
    for page in pages:
        writer.add_page(reader.pages[page - 1])
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def split_pdf(data: bytes) -> list[bytes]:
    reader = PdfReader(io.BytesIO(data))
    results = []
    for page in reader.pages:
        writer = PdfWriter()
        writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        results.append(output.getvalue())
    return results


def compare_pdf_documents(
    original: bytes,
    compared: bytes,
    tesseract_cmd: str = "",
) -> dict:
    original_words, original_pages = _extract_pdf_words(original, tesseract_cmd)
    compared_words, compared_pages = _extract_pdf_words(compared, tesseract_cmd)
    original_tokens = [_comparison_token(word.text) for word in original_words]
    compared_tokens = [_comparison_token(word.text) for word in compared_words]
    matcher = difflib.SequenceMatcher(
        None, original_tokens, compared_tokens, autojunk=False
    )
    similarity = matcher.ratio()

    changes = []
    changed_pages: set[int] = set()
    total_changes = 0

    for (
        tag,
        original_start,
        original_end,
        compared_start,
        compared_end,
    ) in matcher.get_opcodes():
        if tag == "equal":
            continue

        original_group = original_words[original_start:original_end]
        compared_group = compared_words[compared_start:compared_end]
        for original_section, compared_section in _change_sections(
            original_group, compared_group
        ):
            total_changes += 1
            changed_pages.update(word.page for word in original_section)
            changed_pages.update(word.page for word in compared_section)

            if len(changes) == 200:
                continue

            changes.append(
                {
                    "id": f"change-{total_changes}",
                    "kind": "replaced"
                    if original_section and compared_section
                    else "removed"
                    if original_section
                    else "added",
                    "original_text": _change_text(original_section),
                    "compared_text": _change_text(compared_section),
                    "original_highlights": [
                        _word_json(word) for word in original_section
                    ],
                    "compared_highlights": [
                        _word_json(word) for word in compared_section
                    ],
                }
            )

    return {
        "similarity_percent": round(similarity * 100, 1),
        "change_count": total_changes,
        "changed_pages": sorted(changed_pages),
        "changes": changes,
        "changes_truncated": total_changes > len(changes),
        "original_pages": original_pages,
        "compared_pages": compared_pages,
    }


def render_pdf_page(data: bytes, page_number: int, scale: float = 1.5) -> bytes:
    with pymupdf.open(stream=data, filetype="pdf") as document:
        if page_number < 1 or page_number > document.page_count:
            raise ValueError("Page number is outside this PDF")
        page = document[page_number - 1]
        pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return pixmap.tobytes("png")


def _extract_pdf_words(
    data: bytes, tesseract_cmd: str
) -> tuple[list[PdfWord], list[dict]]:
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    words: list[PdfWord] = []
    pages = []
    with pymupdf.open(stream=data, filetype="pdf") as document:
        for page_index, page in enumerate(document):
            page_number = page_index + 1
            pages.append(
                {
                    "page": page_number,
                    "width": round(page.rect.width, 2),
                    "height": round(page.rect.height, 2),
                }
            )
            page_words = page.get_text("words", sort=True)
            if page_words:
                for x0, y0, x1, y1, text, *_ in page_words:
                    normalized = normalize_text(text)
                    if normalized:
                        words.append(
                            PdfWord(
                                text=normalized,
                                page=page_number,
                                x=round(x0, 2),
                                y=round(y0, 2),
                                width=round(x1 - x0, 2),
                                height=round(y1 - y0, 2),
                            )
                        )
                continue

            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
            image = Image.open(io.BytesIO(pixmap.tobytes("png")))
            ocr = pytesseract.image_to_data(image, output_type=Output.DICT)
            for index, text in enumerate(ocr["text"]):
                normalized = normalize_text(text)
                if not normalized:
                    continue
                words.append(
                    PdfWord(
                        text=normalized,
                        page=page_number,
                        x=round(ocr["left"][index] / 2, 2),
                        y=round(ocr["top"][index] / 2, 2),
                        width=round(ocr["width"][index] / 2, 2),
                        height=round(ocr["height"][index] / 2, 2),
                    )
                )
    return words, pages


def _comparison_token(text: str) -> str:
    return re.sub(r"\s+", " ", text).casefold()


def _change_text(words: list[PdfWord]) -> str:
    text = " ".join(word.text for word in words)
    return text if len(text) <= 4000 else f"{text[:3997]}..."


def _change_sections(
    original_words: list[PdfWord], compared_words: list[PdfWord]
) -> list[tuple[list[PdfWord], list[PdfWord]]]:
    original_sections = _split_words_by_page(original_words)
    compared_sections = _split_words_by_page(compared_words)
    section_count = max(len(original_sections), len(compared_sections))
    return [
        (
            original_sections[index] if index < len(original_sections) else [],
            compared_sections[index] if index < len(compared_sections) else [],
        )
        for index in range(section_count)
    ]


def _split_words_by_page(words: list[PdfWord]) -> list[list[PdfWord]]:
    sections: list[list[PdfWord]] = []
    for word in words:
        if not sections or sections[-1][0].page != word.page:
            sections.append([])
        sections[-1].append(word)
    return sections


def _word_json(word: PdfWord) -> dict:
    return {
        "page": word.page,
        "x": word.x,
        "y": word.y,
        "width": word.width,
        "height": word.height,
    }
