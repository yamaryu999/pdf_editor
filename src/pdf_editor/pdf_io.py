from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import List, Tuple
import fitz  # PyMuPDF
from PIL import Image

from .document import DocumentModel, PageModel, ImageElement, TextElement


@dataclass
class PagePreview:
    """Holds rendered preview data for a PDF page."""

    page_id: str
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
            page_model = PageModel(
                width=rect.width,
                height=rect.height,
                rotation=page.rotation,
                source_index=index,
            )
            pages.append(page_model)

            pix = page.get_pixmap(matrix=render_matrix, alpha=False)
            previews.append(PagePreview(page_id=page_model.uid, image_bytes=pix.tobytes("png")))

        pdf_doc.close()
        return DocumentModel(source_path=pdf_path, pages=pages), previews


class PdfExporter:
    """Writes the document model back to a PDF file."""

    def export(self, document: DocumentModel, target_path: Path) -> None:
        source_doc = fitz.open(document.source_path)
        output = fitz.open()
        try:
            for page_model in document.pages:
                new_page = output.new_page(width=page_model.width, height=page_model.height)
                if page_model.source_index is not None:
                    new_page.show_pdf_page(new_page.rect, source_doc, page_model.source_index)

                for element in page_model.elements:
                    if isinstance(element, ImageElement):
                        if not element.visible:
                            continue
                        rect = fitz.Rect(
                            element.rect.x,
                            element.rect.y,
                            element.rect.x + element.rect.width,
                            element.rect.y + element.rect.height,
                        )
                        if element.image_bytes:
                            stream = self._prepare_image_stream(element)
                            new_page.insert_image(
                                rect,
                                stream=stream,
                                keep_proportion=False,
                            )
                    elif isinstance(element, TextElement):
                        if not element.visible:
                            continue
                        rect = fitz.Rect(
                            element.rect.x,
                            element.rect.y,
                            element.rect.x + element.rect.width,
                            element.rect.y + element.rect.height,
                        )
                        color = self._color_to_rgb(element.color)
                        new_page.insert_textbox(
                            rect,
                            element.text,
                            fontsize=element.font_size,
                            fontname="helv",
                            color=color,
                            align=0,
                        )
            output.save(target_path)
        finally:
            output.close()
            source_doc.close()

    def _prepare_image_stream(self, element: ImageElement) -> bytes:
        """Apply opacity if needed before embedding."""

        if element.opacity >= 0.999:
            return element.image_bytes

        with Image.open(BytesIO(element.image_bytes)) as img:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            alpha = img.split()[3]
            alpha = alpha.point(lambda p: int(p * element.opacity))
            img.putalpha(alpha)
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            return buffer.getvalue()

    def _color_to_rgb(self, color: str) -> tuple[float, float, float]:
        color = color.lstrip("#")
        if len(color) != 6:
            return (0, 0, 0)
        r = int(color[0:2], 16) / 255
        g = int(color[2:4], 16) / 255
        b = int(color[4:6], 16) / 255
        return (r, g, b)
