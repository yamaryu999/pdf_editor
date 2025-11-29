from __future__ import annotations

from typing import Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ..document import PageModel, ImageElement


class ImageGraphicsItem(QtWidgets.QGraphicsPixmapItem):
    """Interactive graphics item that represents an ImageElement."""

    def __init__(
        self,
        element: ImageElement,
        pixmap: QtGui.QPixmap,
        *,
        on_geometry_changed,
        on_selection_toggled,
    ):
        super().__init__()
        self.element_id = element.id
        self._on_geometry_changed = on_geometry_changed
        self._on_selection_toggled = on_selection_toggled
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self._source_pixmap = pixmap
        self.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self.apply_model_geometry(element)

    def apply_model_geometry(self, element: ImageElement) -> None:
        width = max(1, int(element.rect.width))
        height = max(1, int(element.rect.height))
        scaled = self._source_pixmap.scaled(
            width,
            height,
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setPos(element.rect.x, element.rect.y)

    def set_size(self, width: float, height: float) -> None:
        width = max(1, int(width))
        height = max(1, int(height))
        scaled = self._source_pixmap.scaled(
            width,
            height,
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            pos: QtCore.QPointF = value
            geo = self.pixmap().rect()
            if self._on_geometry_changed:
                self._on_geometry_changed(
                    self.element_id,
                    float(pos.x()),
                    float(pos.y()),
                    float(geo.width()),
                    float(geo.height()),
                )
        elif change == QtWidgets.QGraphicsItem.ItemSelectedHasChanged:
            if self._on_selection_toggled:
                self._on_selection_toggled(self.element_id, bool(value))
        return super().itemChange(change, value)


class PageCanvas(QtWidgets.QGraphicsView):
    """Displays a PDF page preview with editable elements."""

    elementSelected = QtCore.Signal(object)  # ImageElement | None
    elementGeometryEdited = QtCore.Signal(object)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QtGui.QColor("#f0f0f0"))
        self.setDragMode(QtWidgets.QGraphicsView.NoDrag)
        self.setAlignment(QtCore.Qt.AlignCenter)

        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)

        self._page_model: Optional[PageModel] = None
        self._element_items: Dict[str, ImageGraphicsItem] = {}
        self._background_item: Optional[QtWidgets.QGraphicsPixmapItem] = None

    def set_page(self, page: PageModel, pixmap: QtGui.QPixmap) -> None:
        self._page_model = page
        self._scene.clear()
        self._element_items.clear()
        self._background_item = self._scene.addPixmap(pixmap)
        self._background_item.setZValue(-1)
        self._scene.setSceneRect(0, 0, page.width, page.height)
        self._rebuild_elements()
        self.fitInView(self._scene.sceneRect(), QtCore.Qt.KeepAspectRatio)

    def _rebuild_elements(self) -> None:
        if not self._page_model:
            return
        for element in self._page_model.elements:
            if isinstance(element, ImageElement):
                pixmap = QtGui.QPixmap()
                pixmap.loadFromData(element.image_bytes)
                item = ImageGraphicsItem(
                    element,
                    pixmap,
                    on_geometry_changed=self._handle_geometry_changed,
                    on_selection_toggled=self._handle_selection_toggled,
                )
                self._scene.addItem(item)
                self._element_items[element.id] = item

    def sync_from_model(self, element: ImageElement) -> None:
        """Refresh an item's geometry after external edits."""
        item = self._element_items.get(element.id)
        if not item:
            return
        item.setPos(element.rect.x, element.rect.y)
        item.set_size(element.rect.width, element.rect.height)

    def clear(self) -> None:
        self._scene.clear()
        self._element_items.clear()
        self._page_model = None
        self.elementSelected.emit(None)

    def _handle_geometry_changed(self, element_id: str, x: float, y: float, width: float, height: float) -> None:
        if not self._page_model:
            return
        element = self._page_model.find_element(element_id)
        if not element:
            return
        element.move_to(x, y)
        element.resize(width, height)
        self.elementGeometryEdited.emit(element)

    def select_element(self, element_id: str) -> None:
        item = self._element_items.get(element_id)
        if item:
            item.setSelected(True)
            self.centerOn(item)

    def _handle_selection_toggled(self, element_id: str, selected: bool) -> None:
        if not self._page_model:
            return
        if selected:
            element = self._page_model.find_element(element_id)
            self.elementSelected.emit(element)
        else:
            # Emit None only if nothing else remains selected.
            any_selected = any(item.isSelected() for item in self._element_items.values())
            if not any_selected:
                self.elementSelected.emit(None)
