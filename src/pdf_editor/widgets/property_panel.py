from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets

from ..document import ImageElement


class PropertyPanel(QtWidgets.QWidget):
    """Panel that exposes the numeric geometry controls for an element."""

    geometryEdited = QtCore.Signal(float, float, float, float)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._active_element: Optional[ImageElement] = None
        self._updating = False

        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        self.x_spin = self._create_spin_box()
        self.y_spin = self._create_spin_box()
        self.width_spin = self._create_spin_box()
        self.height_spin = self._create_spin_box()

        layout.addRow("X", self.x_spin)
        layout.addRow("Y", self.y_spin)
        layout.addRow("Width", self.width_spin)
        layout.addRow("Height", self.height_spin)

        for spin in (self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            spin.valueChanged.connect(self._handle_value_changed)

        self._set_enabled(False)

    def set_page_size(self, width: float, height: float) -> None:
        x_max = max(width, 1000)
        y_max = max(height, 1000)
        for spin in (self.x_spin, self.width_spin):
            spin.setMaximum(x_max)
        for spin in (self.y_spin, self.height_spin):
            spin.setMaximum(y_max)

    def set_element(self, element: Optional[ImageElement]) -> None:
        self._active_element = element
        self._set_enabled(element is not None)
        if not element:
            return
        self._updating = True
        self.x_spin.setValue(element.rect.x)
        self.y_spin.setValue(element.rect.y)
        self.width_spin.setValue(element.rect.width)
        self.height_spin.setValue(element.rect.height)
        self._updating = False

    def _create_spin_box(self) -> QtWidgets.QDoubleSpinBox:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setDecimals(1)
        spin.setRange(0.0, 5000.0)
        spin.setSingleStep(5.0)
        spin.setMinimumWidth(120)
        return spin

    def _handle_value_changed(self, _value: float) -> None:
        if not self._active_element or self._updating:
            return
        self.geometryEdited.emit(
            self.x_spin.value(),
            self.y_spin.value(),
            max(1.0, self.width_spin.value()),
            max(1.0, self.height_spin.value()),
        )

    def _set_enabled(self, enabled: bool) -> None:
        for spin in (self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            spin.setEnabled(enabled)
