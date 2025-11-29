from __future__ import annotations

from typing import Optional

from PySide6 import QtCore, QtWidgets

from ..document import ImageElement


class PropertyPanel(QtWidgets.QWidget):
    """Panel that exposes the numeric geometry controls for an element."""

    geometryEdited = QtCore.Signal(float, float, float, float)
    opacityEdited = QtCore.Signal(float)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self._active_element: Optional[ImageElement] = None
        self._updating = False

        main_layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tabs)

        geometry_widget = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(geometry_widget)
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
        self.tabs.addTab(geometry_widget, "位置/サイズ")

        style_widget = QtWidgets.QWidget()
        style_layout = QtWidgets.QVBoxLayout(style_widget)
        style_layout.setContentsMargins(16, 16, 16, 16)
        style_layout.setSpacing(12)
        opacity_row = QtWidgets.QHBoxLayout()
        opacity_label = QtWidgets.QLabel("透明度")
        self.opacity_value_label = QtWidgets.QLabel("100%")
        opacity_row.addWidget(opacity_label)
        opacity_row.addStretch()
        opacity_row.addWidget(self.opacity_value_label)
        style_layout.addLayout(opacity_row)
        self.opacity_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setSingleStep(5)
        self.opacity_slider.setValue(100)
        style_layout.addWidget(self.opacity_slider)
        style_layout.addStretch()
        self.tabs.addTab(style_widget, "スタイル")

        for spin in (self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            spin.valueChanged.connect(self._handle_value_changed)
        self.opacity_slider.valueChanged.connect(self._handle_opacity_changed)

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
        opacity_value = int(element.opacity * 100)
        self.opacity_slider.setValue(opacity_value)
        self.opacity_value_label.setText(f"{opacity_value}%")
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

    def _handle_opacity_changed(self, value: int) -> None:
        if not self._active_element or self._updating:
            return
        self.opacity_value_label.setText(f"{value}%")
        self.opacityEdited.emit(max(0.1, value / 100.0))

    def _set_enabled(self, enabled: bool) -> None:
        for spin in (self.x_spin, self.y_spin, self.width_spin, self.height_spin):
            spin.setEnabled(enabled)
        self.opacity_slider.setEnabled(enabled)
        self.opacity_value_label.setEnabled(enabled)
