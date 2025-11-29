from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from ..document import DocumentModel, ImageElement, PageModel, create_image_element
from ..pdf_io import PdfExporter, PdfImporter, PagePreview
from .canvas import PageCanvas
from .property_panel import PropertyPanel


class MainWindow(QtWidgets.QMainWindow):
    """Main entry window for the PDF editor."""

    def __init__(self):
        super().__init__()
        self.importer = PdfImporter()
        self.exporter = PdfExporter()

        self.document: Optional[DocumentModel] = None
        self.page_pixmaps: Dict[int, QtGui.QPixmap] = {}
        self.current_page_index: Optional[int] = None
        self._selected_element: Optional[ImageElement] = None

        self.setWindowTitle("PDF Editor")
        self.resize(1280, 820)

        self._build_ui()

    def _build_ui(self) -> None:
        self._create_actions()
        self._create_menu()

        self.page_list = QtWidgets.QListWidget()
        self.page_list.currentRowChanged.connect(self._handle_page_change)
        self.page_list.setMaximumWidth(220)

        self.canvas = PageCanvas()
        self.canvas.elementSelected.connect(self._handle_element_selected)
        self.canvas.elementGeometryEdited.connect(self._handle_canvas_geometry_edited)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        splitter.addWidget(self.page_list)
        splitter.addWidget(self.canvas)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self.property_panel = PropertyPanel()
        self.property_panel.geometryEdited.connect(self._handle_property_geometry_edited)

        dock = QtWidgets.QDockWidget("Properties", self)
        dock.setWidget(self.property_panel)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, dock)

        self.statusBar().showMessage("PDF を開いて編集を開始してください。")

    def _create_actions(self) -> None:
        self.open_action = QtGui.QAction("開く...", self)
        self.open_action.setShortcut(QtGui.QKeySequence.Open)
        self.open_action.triggered.connect(self._open_pdf)

        self.save_action = QtGui.QAction("名前を付けて保存...", self)
        self.save_action.setShortcut(QtGui.QKeySequence.SaveAs)
        self.save_action.triggered.connect(self._export_pdf)
        self.save_action.setEnabled(False)

        self.insert_image_action = QtGui.QAction("画像挿入", self)
        self.insert_image_action.setShortcut("Ctrl+I")
        self.insert_image_action.triggered.connect(self._insert_image)
        self.insert_image_action.setEnabled(False)

    def _create_menu(self) -> None:
        file_menu = self.menuBar().addMenu("ファイル")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)

        edit_menu = self.menuBar().addMenu("編集")
        edit_menu.addAction(self.insert_image_action)

        toolbar = self.addToolBar("Main")
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.insert_image_action)

    def _open_pdf(self) -> None:
        file_dialog = QtWidgets.QFileDialog(self, "PDF を開く")
        file_dialog.setFileMode(QtWidgets.QFileDialog.ExistingFile)
        file_dialog.setNameFilter("PDF Files (*.pdf)")
        if not file_dialog.exec():
            return
        file_path = file_dialog.selectedFiles()[0]
        path = Path(file_path)
        try:
            document, previews = self.importer.load(path)
        except RuntimeError as exc:
            QtWidgets.QMessageBox.critical(self, "読み込みエラー", str(exc))
            return

        self.document = document
        self.page_pixmaps = self._build_pixmaps(previews)
        self._populate_page_list()
        self.save_action.setEnabled(True)
        self.insert_image_action.setEnabled(True)
        self.statusBar().showMessage(f"{path.name} を読み込みました。")

        if self.document.page_count:
            self.page_list.setCurrentRow(0)

    def _build_pixmaps(self, previews: List[PagePreview]) -> Dict[int, QtGui.QPixmap]:
        pixmaps: Dict[int, QtGui.QPixmap] = {}
        for preview in previews:
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(preview.image_bytes, "PNG")
            pixmaps[preview.index] = pixmap
        return pixmaps

    def _populate_page_list(self) -> None:
        self.page_list.clear()
        if not self.document:
            return
        for page in self.document.pages:
            pixmap = self.page_pixmaps.get(page.index, QtGui.QPixmap())
            icon = QtGui.QIcon(pixmap.scaled(80, 110, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
            item = QtWidgets.QListWidgetItem(icon, f"Page {page.index + 1}")
            self.page_list.addItem(item)

    def _handle_page_change(self, index: int) -> None:
        if not self.document or index < 0:
            self.current_page_index = None
            self.canvas.clear()
            self.property_panel.set_element(None)
            self._selected_element = None
            return
        self.current_page_index = index
        page = self.document.get_page(index)
        pixmap = self.page_pixmaps.get(index, QtGui.QPixmap())
        self.property_panel.set_page_size(page.width, page.height)
        self.canvas.set_page(page, pixmap)
        self.property_panel.set_element(None)
        self._selected_element = None

    def _insert_image(self) -> None:
        if not self.document or self.current_page_index is None:
            return
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "挿入する画像ファイルを選択",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp)",
        )
        if not file_path:
            return
        path = Path(file_path)
        data = path.read_bytes()
        pixmap = QtGui.QPixmap()
        if not pixmap.loadFromData(data):
            QtWidgets.QMessageBox.warning(self, "画像エラー", "画像を読み込めませんでした。")
            return
        page = self.document.get_page(self.current_page_index)
        target_width = min(pixmap.width(), page.width * 0.6)
        scale = target_width / max(1, pixmap.width())
        target_height = max(1, pixmap.height() * scale)
        x = max(0.0, (page.width - target_width) / 2)
        y = max(0.0, (page.height - target_height) / 2)

        element = create_image_element(
            x=x,
            y=y,
            width=target_width,
            height=target_height,
            source_path=path,
            image_bytes=data,
        )
        page.add_element(element)
        self._refresh_canvas(select_element_id=element.id)

    def _export_pdf(self) -> None:
        if not self.document:
            return
        target_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "編集済み PDF を保存",
            "",
            "PDF Files (*.pdf)",
        )
        if not target_path:
            return
        try:
            self.exporter.export(self.document, Path(target_path))
        except RuntimeError as exc:
            QtWidgets.QMessageBox.critical(self, "保存エラー", str(exc))
            return
        self.statusBar().showMessage(f"{target_path} に保存しました。")

    def _refresh_canvas(self, select_element_id: Optional[str] = None) -> None:
        if not self.document or self.current_page_index is None:
            return
        page = self.document.get_page(self.current_page_index)
        pixmap = self.page_pixmaps.get(self.current_page_index, QtGui.QPixmap())
        self.canvas.set_page(page, pixmap)
        if select_element_id:
            self.canvas.select_element(select_element_id)
            element = page.find_element(select_element_id)
            if element:
                self.property_panel.set_element(element)
                self._selected_element = element

    def _handle_element_selected(self, element: Optional[ImageElement]) -> None:
        self._selected_element = element
        self.property_panel.set_element(element)

    def _handle_canvas_geometry_edited(self, element: ImageElement) -> None:
        self._selected_element = element
        self.property_panel.set_element(element)

    def _handle_property_geometry_edited(self, x: float, y: float, width: float, height: float) -> None:
        if not self.document or self.current_page_index is None:
            return
        element = self._selected_element
        if not element:
            return
        element.move_to(x, y)
        element.resize(width, height)
        self.canvas.sync_from_model(element)
