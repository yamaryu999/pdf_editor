from __future__ import annotations

from typing import Dict, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ..document import Element, PageModel, ImageElement, TextElement


class ImageGraphicsItem(QtWidgets.QGraphicsPixmapItem):
    """Interactive graphics item that represents an ImageElement."""

    HANDLE_SIZE = 12
    MIN_SIZE = 12
    CURSOR_MAP = {
        "top-left": QtCore.Qt.SizeFDiagCursor,
        "bottom-right": QtCore.Qt.SizeFDiagCursor,
        "top-right": QtCore.Qt.SizeBDiagCursor,
        "bottom-left": QtCore.Qt.SizeBDiagCursor,
        "top": QtCore.Qt.SizeVerCursor,
        "bottom": QtCore.Qt.SizeVerCursor,
        "left": QtCore.Qt.SizeHorCursor,
        "right": QtCore.Qt.SizeHorCursor,
    }

    def __init__(
        self,
        element: ImageElement,
        pixmap: QtGui.QPixmap,
        *,
        on_geometry_changed,
        on_snap_request,
        on_snap_finished,
    ):
        super().__init__()
        self.element_id = element.id
        self._on_geometry_changed = on_geometry_changed
        self._on_snap_request = on_snap_request
        self._on_snap_finished = on_snap_finished
        self._source_pixmap = pixmap
        self._resizing = False
        self._active_handle: Optional[str] = None
        self._initial_rect: Optional[QtCore.QRectF] = None
        self._initial_mouse_scene: Optional[QtCore.QPointF] = None
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setTransformationMode(QtCore.Qt.SmoothTransformation)
        self.apply_model_geometry(element)

    def apply_model_geometry(self, element: ImageElement) -> None:
        width = max(self.MIN_SIZE, int(element.rect.width))
        height = max(self.MIN_SIZE, int(element.rect.height))
        scaled = self._source_pixmap.scaled(
            width,
            height,
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setPos(element.rect.x, element.rect.y)
        self.setOpacity(element.opacity)

    def set_size(self, width: float, height: float) -> None:
        width = max(self.MIN_SIZE, int(width))
        height = max(self.MIN_SIZE, int(height))
        scaled = self._source_pixmap.scaled(
            width,
            height,
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setOpacity(self.opacity())  # keep current opacity

    def _emit_geometry_changed(self) -> None:
        if not self._on_geometry_changed:
            return
        geo = self.pixmap().rect()
        pos = self.pos()
        self._on_geometry_changed(
            self.element_id,
            float(pos.x()),
            float(pos.y()),
            float(geo.width()),
            float(geo.height()),
        )

    def _handle_rects(self) -> Dict[str, QtCore.QRectF]:
        pix_rect = self.pixmap().rect()
        w = float(pix_rect.width())
        h = float(pix_rect.height())
        s = float(self.HANDLE_SIZE)
        half = s / 2.0
        return {
            "top-left": QtCore.QRectF(0.0, 0.0, s, s),
            "top": QtCore.QRectF(max(0.0, w / 2.0 - half), 0.0, s, s),
            "top-right": QtCore.QRectF(max(0.0, w - s), 0.0, s, s),
            "right": QtCore.QRectF(max(0.0, w - s), max(0.0, h / 2.0 - half), s, s),
            "bottom-right": QtCore.QRectF(max(0.0, w - s), max(0.0, h - s), s, s),
            "bottom": QtCore.QRectF(max(0.0, w / 2.0 - half), max(0.0, h - s), s, s),
            "bottom-left": QtCore.QRectF(0.0, max(0.0, h - s), s, s),
            "left": QtCore.QRectF(0.0, max(0.0, h / 2.0 - half), s, s),
        }

    def _hit_handle(self, pos: QtCore.QPointF) -> Optional[str]:
        for name, rect in self._handle_rects().items():
            if rect.contains(pos):
                return name
        return None

    def _update_cursor(self, pos: QtCore.QPointF) -> None:
        handle = self._hit_handle(pos)
        if handle:
            cursor = self.CURSOR_MAP.get(handle, QtCore.Qt.SizeAllCursor)
            self.setCursor(cursor)
        else:
            self.unsetCursor()

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._update_cursor(event.pos())
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        handle = self._hit_handle(event.pos())
        if handle:
            self._resizing = True
            self._active_handle = handle
            self._initial_rect = QtCore.QRectF(
                self.pos().x(),
                self.pos().y(),
                float(self.pixmap().width()),
                float(self.pixmap().height()),
            )
            self._initial_mouse_scene = QtCore.QPointF(event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if self._resizing:
            if self._initial_mouse_scene is None:
                return
            delta = event.scenePos() - self._initial_mouse_scene
            self._resize_with_delta(delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if self._resizing:
            self._resizing = False
            self._active_handle = None
            self._initial_rect = None
            self._initial_mouse_scene = None
            self._emit_geometry_changed()
            event.accept()
        super().mouseReleaseEvent(event)

    def _resize_with_delta(self, delta: QtCore.QPointF) -> None:
        if not self._initial_rect or not self._active_handle:
            return
        handle = self._active_handle
        left = self._initial_rect.left()
        right = self._initial_rect.right()
        top = self._initial_rect.top()
        bottom = self._initial_rect.bottom()

        if "left" in handle:
            new_left = left + delta.x()
            max_left = right - self.MIN_SIZE
            left = min(new_left, max_left)
        if "right" in handle:
            new_right = right + delta.x()
            min_right = left + self.MIN_SIZE
            right = max(new_right, min_right)
        if "top" in handle:
            new_top = top + delta.y()
            max_top = bottom - self.MIN_SIZE
            top = min(new_top, max_top)
        if "bottom" in handle:
            new_bottom = bottom + delta.y()
            min_bottom = top + self.MIN_SIZE
            bottom = max(new_bottom, min_bottom)

        new_width = max(self.MIN_SIZE, right - left)
        new_height = max(self.MIN_SIZE, bottom - top)
        self.setPos(QtCore.QPointF(left, top))
        self.set_size(new_width, new_height)
        self._emit_geometry_changed()

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        if self.isSelected():
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter.setPen(QtGui.QPen(QtGui.QColor("#1e88e5"), 1.2))
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#ffffff")))
            for handle_rect in self._handle_rects().values():
                painter.drawRect(handle_rect)
            painter.restore()

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and self._on_snap_request:
            pos: QtCore.QPointF = value
            width = float(self.pixmap().width())
            height = float(self.pixmap().height())
            snapped_x, snapped_y = self._on_snap_request(
                self.element_id,
                float(pos.x()),
                float(pos.y()),
                width,
                height,
            )
            return QtCore.QPointF(snapped_x, snapped_y)
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
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if self._on_snap_finished:
            self._on_snap_finished()
        super().mouseReleaseEvent(event)


class TextGraphicsItem(QtWidgets.QGraphicsRectItem):
    """Resizable graphics item for text elements."""

    HANDLE_SIZE = 12
    MIN_SIZE = 20
    CURSOR_MAP = ImageGraphicsItem.CURSOR_MAP

    def __init__(
        self,
        element: TextElement,
        *,
        on_geometry_changed,
        on_snap_request,
        on_snap_finished,
    ):
        super().__init__(0, 0, element.rect.width, element.rect.height)
        self.element_id = element.id
        self._on_geometry_changed = on_geometry_changed
        self._on_snap_request = on_snap_request
        self._on_snap_finished = on_snap_finished
        self._resizing = False
        self._active_handle: Optional[str] = None
        self._initial_rect: Optional[QtCore.QRectF] = None
        self._initial_mouse_scene: Optional[QtCore.QPointF] = None
        self.text = element.text
        self.font_family = element.font_family
        self.font_size = element.font_size
        self.color = element.color
        self.setAcceptedMouseButtons(QtCore.Qt.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsSelectable
            | QtWidgets.QGraphicsItem.ItemIsMovable
            | QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setPos(element.rect.x, element.rect.y)
        self.setOpacity(element.opacity)

    def apply_model_geometry(self, element: TextElement) -> None:
        self.prepareGeometryChange()
        width = max(self.MIN_SIZE, element.rect.width)
        height = max(self.MIN_SIZE, element.rect.height)
        self.setRect(0, 0, width, height)
        self.setPos(element.rect.x, element.rect.y)
        self.text = element.text
        self.font_family = element.font_family
        self.font_size = element.font_size
        self.color = element.color
        self.setOpacity(element.opacity)

    def set_content(self, text: str, font_family: str, font_size: float, color: str) -> None:
        self.text = text
        self.font_family = font_family
        self.font_size = font_size
        self.color = color
        self.update()

    def _emit_geometry_changed(self) -> None:
        if not self._on_geometry_changed:
            return
        rect = self.rect()
        pos = self.pos()
        self._on_geometry_changed(
            self.element_id,
            float(pos.x()),
            float(pos.y()),
            float(rect.width()),
            float(rect.height()),
        )

    def _handle_rects(self) -> Dict[str, QtCore.QRectF]:
        rect = self.rect()
        w = float(rect.width())
        h = float(rect.height())
        s = float(self.HANDLE_SIZE)
        half = s / 2.0
        return {
            "top-left": QtCore.QRectF(0.0, 0.0, s, s),
            "top": QtCore.QRectF(max(0.0, w / 2.0 - half), 0.0, s, s),
            "top-right": QtCore.QRectF(max(0.0, w - s), 0.0, s, s),
            "right": QtCore.QRectF(max(0.0, w - s), max(0.0, h / 2.0 - half), s, s),
            "bottom-right": QtCore.QRectF(max(0.0, w - s), max(0.0, h - s), s, s),
            "bottom": QtCore.QRectF(max(0.0, w / 2.0 - half), max(0.0, h - s), s, s),
            "bottom-left": QtCore.QRectF(0.0, max(0.0, h - s), s, s),
            "left": QtCore.QRectF(0.0, max(0.0, h / 2.0 - half), s, s),
        }

    def _hit_handle(self, pos: QtCore.QPointF) -> Optional[str]:
        for name, rect in self._handle_rects().items():
            if rect.contains(pos):
                return name
        return None

    def _update_cursor(self, pos: QtCore.QPointF) -> None:
        handle = self._hit_handle(pos)
        if handle:
            cursor = self.CURSOR_MAP.get(handle, QtCore.Qt.SizeAllCursor)
            self.setCursor(cursor)
        else:
            self.unsetCursor()

    def hoverMoveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._update_cursor(event.pos())
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self.unsetCursor()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        handle = self._hit_handle(event.pos())
        if handle:
            self._resizing = True
            self._active_handle = handle
            self._initial_rect = QtCore.QRectF(
                self.pos().x(),
                self.pos().y(),
                self.rect().width(),
                self.rect().height(),
            )
            self._initial_mouse_scene = QtCore.QPointF(event.scenePos())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if self._resizing and self._initial_mouse_scene is not None:
            delta = event.scenePos() - self._initial_mouse_scene
            self._resize_with_delta(delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if self._resizing:
            self._resizing = False
            self._active_handle = None
            self._initial_rect = None
            self._initial_mouse_scene = None
            self._emit_geometry_changed()
            if self._on_snap_finished:
                self._on_snap_finished()
            event.accept()
            return
        if self._on_snap_finished:
            self._on_snap_finished()
        super().mouseReleaseEvent(event)

    def _resize_with_delta(self, delta: QtCore.QPointF) -> None:
        if not self._initial_rect or not self._active_handle:
            return
        rect = QtCore.QRectF(self._initial_rect)
        handle = self._active_handle
        if "left" in handle:
            rect.setLeft(min(rect.right() - self.MIN_SIZE, rect.left() + delta.x()))
        if "right" in handle:
            rect.setRight(max(rect.left() + self.MIN_SIZE, rect.right() + delta.x()))
        if "top" in handle:
            rect.setTop(min(rect.bottom() - self.MIN_SIZE, rect.top() + delta.y()))
        if "bottom" in handle:
            rect.setBottom(max(rect.top() + self.MIN_SIZE, rect.bottom() + delta.y()))
        self.prepareGeometryChange()
        self.setRect(0, 0, rect.width(), rect.height())
        self.setPos(rect.left(), rect.top())
        self._emit_geometry_changed()

    def paint(self, painter: QtGui.QPainter, option, widget=None) -> None:
        rect = self.rect()
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtGui.QColor(0, 0, 0, 0))
        painter.setBrush(QtGui.QColor(0, 0, 0, 0))
        painter.drawRect(rect)
        painter.restore()

        painter.save()
        font = QtGui.QFont(self.font_family, max(1, int(self.font_size)))
        painter.setFont(font)
        color = QtGui.QColor(self.color)
        painter.setPen(color)
        painter.drawText(rect, QtCore.Qt.TextWordWrap | QtCore.Qt.AlignLeft | QtCore.Qt.AlignTop, self.text)
        painter.restore()

        if self.isSelected():
            painter.save()
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            painter.setPen(QtGui.QPen(QtGui.QColor("#1e88e5"), 1.2))
            painter.setBrush(QtGui.QBrush(QtGui.QColor("#ffffff")))
            for handle_rect in self._handle_rects().values():
                painter.drawRect(handle_rect)
            painter.restore()

    def itemChange(self, change: QtWidgets.QGraphicsItem.GraphicsItemChange, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and self._on_snap_request:
            pos: QtCore.QPointF = value
            snapped_x, snapped_y = self._on_snap_request(
                self.element_id,
                float(pos.x()),
                float(pos.y()),
                float(self.rect().width()),
                float(self.rect().height()),
            )
            return QtCore.QPointF(snapped_x, snapped_y)
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            self._emit_geometry_changed()
        return super().itemChange(change, value)


class PageCanvas(QtWidgets.QGraphicsView):
    """Displays a PDF page preview with editable elements."""

    selectionChanged = QtCore.Signal(list)
    elementGeometryEdited = QtCore.Signal(object)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QtGui.QColor("#f0f0f0"))
        self.setDragMode(QtWidgets.QGraphicsView.RubberBandDrag)
        self.setAlignment(QtCore.Qt.AlignCenter)

        self._scene = QtWidgets.QGraphicsScene(self)
        self.setScene(self._scene)
        self._scene.selectionChanged.connect(self._handle_scene_selection_changed)

        self._page_model: Optional[PageModel] = None
        self._element_items: Dict[str, ImageGraphicsItem] = {}
        self._background_item: Optional[QtWidgets.QGraphicsPixmapItem] = None
        self._guide_lines: list[QtWidgets.QGraphicsLineItem] = []
        self._grid_lines: list[QtWidgets.QGraphicsLineItem] = []
        self._grid_visible = False

    def set_page(self, page: PageModel, pixmap: QtGui.QPixmap) -> None:
        self._page_model = page
        self._scene.clear()
        self._element_items.clear()
        self._background_item = self._scene.addPixmap(pixmap)
        self._background_item.setZValue(-1)
        self._scene.setSceneRect(0, 0, page.width, page.height)
        self._rebuild_elements()
        self.fitInView(self._scene.sceneRect(), QtCore.Qt.KeepAspectRatio)
        self._update_grid_lines()

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
                    on_snap_request=self._request_snap_position,
                    on_snap_finished=self._clear_guides,
                )
                item.setVisible(element.visible)
                item.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, not element.locked)
                self._scene.addItem(item)
                self._element_items[element.id] = item
            elif isinstance(element, TextElement):
                item = TextGraphicsItem(
                    element,
                    on_geometry_changed=self._handle_geometry_changed,
                    on_snap_request=self._request_snap_position,
                    on_snap_finished=self._clear_guides,
                )
                item.setVisible(element.visible)
                item.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, not element.locked)
                self._scene.addItem(item)
                self._element_items[element.id] = item

    def sync_from_model(self, element: Element) -> None:
        """Refresh an item's geometry after external edits."""
        item = self._element_items.get(element.id)
        if not item:
            return
        if isinstance(item, ImageGraphicsItem) and isinstance(element, ImageElement):
            item.setPos(element.rect.x, element.rect.y)
            item.set_size(element.rect.width, element.rect.height)
            item.setOpacity(element.opacity)
        elif isinstance(item, TextGraphicsItem) and isinstance(element, TextElement):
            item.apply_model_geometry(element)

    def clear(self) -> None:
        self._scene.clear()
        self._element_items.clear()
        self._page_model = None
        self._clear_guides()
        self._grid_lines.clear()
        self.selectionChanged.emit([])

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
            self._scene.clearSelection()
            item.setSelected(True)
            self.centerOn(item)

    def select_elements(self, element_ids: list[str]) -> None:
        self._scene.clearSelection()
        last_item = None
        for element_id in element_ids:
            item = self._element_items.get(element_id)
            if item:
                item.setSelected(True)
                last_item = item
        if last_item:
            self.centerOn(last_item)

    def _handle_scene_selection_changed(self) -> None:
        if not self._page_model:
            self.selectionChanged.emit([])
            return
        selected_ids = []
        for item in self._scene.selectedItems():
            if isinstance(item, ImageGraphicsItem):
                selected_ids.append(item.element_id)
        elements = []
        for element in self._page_model.elements:
            if element.id in selected_ids:
                elements.append(element)
        self.selectionChanged.emit(elements)

    def _request_snap_position(
        self,
        element_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> tuple[float, float]:
        if not self._page_model:
            self._clear_guides()
            return x, y
        x_snapped, y_snapped, guides = self._compute_snap_guides(element_id, x, y, width, height)
        self._show_guides(guides)
        return x_snapped, y_snapped

    def _compute_snap_guides(
        self,
        element_id: str,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> tuple[float, float, list[tuple[str, float]]]:
        threshold = 6
        guides: list[tuple[str, float]] = []
        page = self._page_model
        center_x = page.width / 2
        center_y = page.height / 2
        element_center_x = x + width / 2
        element_center_y = y + height / 2

        if abs(element_center_x - center_x) < threshold:
            x = center_x - width / 2
            guides.append(("v", center_x))
        elif abs(x) < threshold:
            x = 0.0
            guides.append(("v", 0.0))
        elif abs((x + width) - page.width) < threshold:
            x = page.width - width
            guides.append(("v", page.width))

        if abs(element_center_y - center_y) < threshold:
            y = center_y - height / 2
            guides.append(("h", center_y))
        elif abs(y) < threshold:
            y = 0.0
            guides.append(("h", 0.0))
        elif abs((y + height) - page.height) < threshold:
            y = page.height - height
            guides.append(("h", page.height))

        for element in page.elements:
            if element.id == element_id:
                continue
            if hasattr(element, "visible") and not element.visible:
                continue
            # vertical matching
            other_positions = [
                element.rect.x,
                element.rect.x + element.rect.width / 2,
                element.rect.x + element.rect.width,
            ]
            for target in other_positions:
                if abs(x - target) < threshold:
                    x = target
                    guides.append(("v", target))
                elif abs((x + width) - target) < threshold:
                    x = target - width
                    guides.append(("v", target))
            # horizontal matching
            other_y_positions = [
                element.rect.y,
                element.rect.y + element.rect.height / 2,
                element.rect.y + element.rect.height,
            ]
            for target in other_y_positions:
                if abs(y - target) < threshold:
                    y = target
                    guides.append(("h", target))
                elif abs((y + height) - target) < threshold:
                    y = target - height
                    guides.append(("h", target))

        return x, y, guides

    def _show_guides(self, guides: list[tuple[str, float]]) -> None:
        self._clear_guides()
        if not self._page_model:
            return
        pen = QtGui.QPen(QtGui.QColor("#ff7043"))
        pen.setWidth(1)
        pen.setStyle(QtCore.Qt.DashLine)
        for orientation, coord in guides:
            if orientation == "v":
                line = self._scene.addLine(
                    coord,
                    0,
                    coord,
                    self._page_model.height,
                    pen,
                )
            else:
                line = self._scene.addLine(
                    0,
                    coord,
                    self._page_model.width,
                    coord,
                    pen,
                )
            line.setZValue(999)
            self._guide_lines.append(line)

    def _clear_guides(self) -> None:
        for line in self._guide_lines:
            self._scene.removeItem(line)
        self._guide_lines.clear()

    def set_grid_visible(self, visible: bool) -> None:
        self._grid_visible = visible
        self._update_grid_lines()

    def _update_grid_lines(self) -> None:
        for line in self._grid_lines:
            self._scene.removeItem(line)
        self._grid_lines.clear()
        if not self._grid_visible or not self._page_model:
            return
        pen = QtGui.QPen(QtGui.QColor("#d0d0d0"))
        pen.setStyle(QtCore.Qt.DotLine)
        pen.setWidth(1)
        step = 50
        width = int(self._page_model.width)
        height = int(self._page_model.height)
        for x in range(step, width, step):
            line = self._scene.addLine(x, 0, x, height, pen)
            line.setZValue(-0.5)
            self._grid_lines.append(line)
        for y in range(step, height, step):
            line = self._scene.addLine(0, y, width, y, pen)
            line.setZValue(-0.5)
            self._grid_lines.append(line)

    def update_element_visibility(self, element_id: str, visible: bool) -> None:
        item = self._element_items.get(element_id)
        if item:
            item.setVisible(visible)

    def update_element_lock(self, element_id: str, locked: bool) -> None:
        item = self._element_items.get(element_id)
        if item:
            item.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable, not locked)
