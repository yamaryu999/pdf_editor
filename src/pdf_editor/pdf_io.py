from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple
import fitz  # PyMuPDF

from .document import DocumentModel, PageModel, ImageElement


@dataclass
class PagePreview:
    """Holds rendered preview data for a PDF page."""

    index: int
    image_bytes: bytes


class PdfImporter:
    """Loads PDF files into editable document models."""

    def load(self, pdf_path: Path) -> Tuple[DocumentModel, List[PagePreview]]:
        pdf_doc = fitz.open(pdf_path)
        pages: List[PageModel] = []
        previews: List[PagePreview] = []

        # Matrix 1.0 keeps pixel coordinates identical to PDF points, making
        # it easier to align overlay elements.
        render_matrix = fitz.Matrix(1.0, 1.0)
        for index, page in enumerate(pdf_doc):
            rect = page.rect
            pages.append(
                PageModel(
                    index=index,
                    width=rect.width,
                    height=rect.height,
                    rotation=page.rotation,
                )
            )
            pix = page.get_pixmap(matrix=render_matrix, alpha=False)
            previews.append(PagePreview(index=index, image_bytes=pix.tobytes("png")))

        pdf_doc.close()
        return DocumentModel(source_path=pdf_path, pages=pages), previews


class PdfExporter:
    """Writes the document model back to a PDF file."""

    def export(self, document: DocumentModel, target_path: Path) -> None:
        source_doc = fitz.open(document.source_path)
        output = fitz.open()
        try:
            for page_model in document.pages:
                base_page = source_doc.load_page(page_model.index)
                new_page = output.new_page(width=base_page.rect.width, height=base_page.rect.height)
                new_page.show_pdf_page(new_page.rect, source_doc, page_model.index)

                for element in page_model.elements:
                    if isinstance(element, ImageElement):
                        rect = fitz.Rect(
                            element.rect.x,
                            element.rect.y,
                            element.rect.x + element.rect.width,
                            element.rect.y + element.rect.height,
                        )
                        if element.image_bytes:
                            new_page.insert_image(rect, stream=element.image_bytes, keep_proportion=False)
            output.save(target_path)
        finally:
            output.close()
            source_doc.close()
