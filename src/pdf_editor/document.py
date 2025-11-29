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
    locked: bool = False
    visible: bool = True

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
class TextElement(Element):
    """Text drawn on the PDF page."""

    text: str = ""
    font_family: str = "Noto Sans"
    font_size: float = 14.0
    color: str = "#000000"


@dataclass
class PageModel:
    """Represents a single page of a PDF document."""

    width: float
    height: float
    rotation: int = 0
    source_index: Optional[int] = None
    elements: List[Element] = field(default_factory=list)
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    label: str = ""
    note: str = ""

    def add_element(self, element: Element) -> None:
        self.elements.append(element)

    def remove_element(self, element_id: str) -> Optional[Element]:
        for index, elem in enumerate(self.elements):
            if elem.id == element_id:
                return self.elements.pop(index)
        return None

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

    def insert_page(self, index: int, page: PageModel) -> None:
        self.pages.insert(index, page)

    def append_page(self, page: PageModel) -> None:
        self.pages.append(page)

    def remove_page(self, index: int) -> PageModel:
        return self.pages.pop(index)

    def find_page_by_id(self, page_id: str) -> Optional[PageModel]:
        for page in self.pages:
            if page.uid == page_id:
                return page
        return None

    def index_of_page(self, page_id: str) -> Optional[int]:
        for idx, page in enumerate(self.pages):
            if page.uid == page_id:
                return idx
        return None

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


def create_text_element(
    x: float,
    y: float,
    width: float,
    height: float,
    *,
    text: str,
    font_family: str = "Noto Sans",
    font_size: float = 14.0,
    color: str = "#000000",
) -> TextElement:
    return TextElement(
        id=str(uuid.uuid4()),
        rect=Rect(x=x, y=y, width=width, height=height),
        text=text,
        font_family=font_family,
        font_size=font_size,
        color=color,
    )


def clone_element(element: Element) -> Element:
    """Create a detached copy of an element."""

    rect = Rect(
        x=element.rect.x,
        y=element.rect.y,
        width=element.rect.width,
        height=element.rect.height,
    )

    if isinstance(element, ImageElement):
        return ImageElement(
            id=element.id,
            rect=rect,
            rotation=element.rotation,
            opacity=element.opacity,
            locked=element.locked,
            visible=element.visible,
            source_path=element.source_path,
            image_bytes=element.image_bytes,
        )
    if isinstance(element, TextElement):
        return TextElement(
            id=element.id,
            rect=rect,
            rotation=element.rotation,
            opacity=element.opacity,
            locked=element.locked,
            visible=element.visible,
            text=element.text,
            font_family=element.font_family,
            font_size=element.font_size,
            color=element.color,
        )
    return Element(
        id=element.id,
        rect=rect,
        rotation=element.rotation,
        opacity=element.opacity,
        locked=element.locked,
        visible=element.visible,
    )
