from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import uuid


@dataclass
class Rect:
    """Axis aligned rectangle helper."""

    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass
class Element:
    """Base element placed on a PDF page."""

    id: str
    rect: Rect
    rotation: float = 0.0
    opacity: float = 1.0

    def move_to(self, x: float, y: float) -> None:
        self.rect.x = x
        self.rect.y = y

    def resize(self, width: float, height: float) -> None:
        self.rect.width = max(1.0, width)
        self.rect.height = max(1.0, height)


@dataclass
class ImageElement(Element):
    """Image drawn on the PDF page."""

    source_path: Path = Path()
    image_bytes: bytes = b""


@dataclass
class PageModel:
    """Represents a single page of a PDF document."""

    index: int
    width: float
    height: float
    rotation: int = 0
    elements: List[Element] = field(default_factory=list)

    def add_element(self, element: Element) -> None:
        self.elements.append(element)

    def remove_element(self, element_id: str) -> None:
        self.elements = [elem for elem in self.elements if elem.id != element_id]

    def find_element(self, element_id: str) -> Optional[Element]:
        for element in self.elements:
            if element.id == element_id:
                return element
        return None


@dataclass
class DocumentModel:
    """Editable PDF document."""

    source_path: Path
    pages: List[PageModel] = field(default_factory=list)

    def get_page(self, index: int) -> PageModel:
        return self.pages[index]

    @property
    def page_count(self) -> int:
        return len(self.pages)


def create_image_element(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    source_path: Path,
    image_bytes: bytes,
) -> ImageElement:
    """Factory helper for image elements."""

    return ImageElement(
        id=str(uuid.uuid4()),
        rect=Rect(x=x, y=y, width=width, height=height),
        source_path=source_path,
        image_bytes=image_bytes,
    )
