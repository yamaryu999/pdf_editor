from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets
from qt_material import apply_stylesheet

from ..document import (
    DocumentModel,
    Element,
    ImageElement,
    PageModel,
    TextElement,
    clone_element,
    create_image_element,
    create_text_element,
)
from ..pdf_io import PdfExporter, PdfImporter, PagePreview
from .canvas import PageCanvas
from .property_panel import PropertyPanel


@dataclass
class HistoryCommand:
    action: str  # "insert" or "delete"
    page_id: str
    element: Element


class SettingsDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        themes: List[str],
        current_theme: str,
        thumbnail_size: int,
        page_width: float,
        page_height: float,
    ):
        super().__init__(parent)
        self.setWindowTitle("設定")
        layout = QtWidgets.QFormLayout(self)

        self.theme_combo = QtWidgets.QComboBox()
        self.theme_combo.addItems(themes)
        if current_theme in themes:
            self.theme_combo.setCurrentText(current_theme)
        layout.addRow("テーマ", self.theme_combo)

        self.thumb_spin = QtWidgets.QSpinBox()
        self.thumb_spin.setRange(60, 200)
        self.thumb_spin.setValue(thumbnail_size)
        layout.addRow("サムネイルサイズ", self.thumb_spin)

        page_size_layout = QtWidgets.QHBoxLayout()
        self.page_width_spin = QtWidgets.QDoubleSpinBox()
        self.page_width_spin.setRange(100.0, 2000.0)
        self.page_width_spin.setValue(page_width)
        self.page_height_spin = QtWidgets.QDoubleSpinBox()
        self.page_height_spin.setRange(100.0, 2000.0)
        self.page_height_spin.setValue(page_height)
        page_size_layout.addWidget(QtWidgets.QLabel("幅"))
        page_size_layout.addWidget(self.page_width_spin)
        page_size_layout.addWidget(QtWidgets.QLabel("高さ"))
        page_size_layout.addWidget(self.page_height_spin)
        layout.addRow("新規ページサイズ", page_size_layout)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def values(self) -> dict:
        return {
            "theme": self.theme_combo.currentText(),
            "thumbnail_size": self.thumb_spin.value(),
            "default_page_width": self.page_width_spin.value(),
            "default_page_height": self.page_height_spin.value(),
        }


class TextEditDialog(QtWidgets.QDialog):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        *,
        text: str = "",
        font_size: float = 14.0,
        color: str = "#000000",
    ):
        super().__init__(parent)
        self.setWindowTitle("テキスト入力")
        layout = QtWidgets.QFormLayout(self)

        self.text_edit = QtWidgets.QPlainTextEdit()
        self.text_edit.setPlainText(text)
        layout.addRow("内容", self.text_edit)

        self.font_spin = QtWidgets.QSpinBox()
        self.font_spin.setRange(6, 200)
        self.font_spin.setValue(int(font_size))
        layout.addRow("フォントサイズ", self.font_spin)

        self.color_combo = QtWidgets.QComboBox()
        colors = [
            ("黒", "#000000"),
            ("白", "#ffffff"),
            ("赤", "#e53935"),
            ("青", "#1e88e5"),
            ("緑", "#43a047"),
        ]
        for label, value in colors:
            self.color_combo.addItem(label, value)
        index = self.color_combo.findData(color)
        if index >= 0:
            self.color_combo.setCurrentIndex(index)
        layout.addRow("色", self.color_combo)

        button_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addRow(button_box)

    def values(self) -> dict:
        return {
            "text": self.text_edit.toPlainText().strip(),
            "font_size": float(self.font_spin.value()),
            "color": self.color_combo.currentData(),
        }


class MainWindow(QtWidgets.QMainWindow):
    """Main entry window for the PDF editor."""

    def __init__(self):
        super().__init__()
        self.importer = PdfImporter()
        self.exporter = PdfExporter()

        self.settings = QtCore.QSettings("yamaryu", "PDFEditor")
        self.available_themes = [
            "dark_teal.xml",
            "light_blue.xml",
            "dark_blue.xml",
            "light_cyan.xml",
            "dark_pink.xml",
            "light_cyan_500.xml",
        ]
        theme_pref = self.settings.value("theme", None)
        env_theme = os.getenv("PDF_EDITOR_THEME")
        self.current_theme = theme_pref or env_theme or "dark_teal.xml"
        self._palette = self._palette_for_theme(self.current_theme)

        self.thumbnail_size = int(self.settings.value("thumbnail_size", 110))
        self.default_page_width = float(self.settings.value("default_page_width", 595.0))
        self.default_page_height = float(self.settings.value("default_page_height", 842.0))

        self.document: Optional[DocumentModel] = None
        self.page_pixmaps: Dict[str, QtGui.QPixmap] = {}
        self.current_page_index: Optional[int] = None
        self._selected_element: Optional[ImageElement] = None
        self._selected_elements: List[Element] = []
        self._layer_panel_updating = False
        self.current_tool = "select"
        self.undo_stack: List[HistoryCommand] = []
        self.redo_stack: List[HistoryCommand] = []
        self.page_filter_text = ""
        self._page_metadata_updating = False
        self._unsaved_changes = False

        self.setWindowTitle("PDF Editor")
        self.resize(1280, 820)

        self._build_ui()
        self._apply_theme(self.current_theme)
        self.autosave_timer = QtCore.QTimer(self)
        self.autosave_timer.setInterval(120000)
        self.autosave_timer.timeout.connect(self._handle_autosave_timeout)
        self.autosave_timer.start()

    def _build_ui(self) -> None:
        self._create_actions()
        self._create_menu()

        self.page_list = QtWidgets.QListWidget()
        self.page_list.setObjectName("PageList")
        self.page_list.setSpacing(8)
        self.page_list.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.page_list.currentRowChanged.connect(self._handle_page_change)
        self.page_list.setIconSize(QtCore.QSize(self.thumbnail_size, int(self.thumbnail_size * 1.4)))

        self.page_search = QtWidgets.QLineEdit()
        self.page_search.setPlaceholderText("ページ番号でジャンプ")
        self.page_search.setClearButtonEnabled(True)
        self.page_search.returnPressed.connect(self._handle_page_jump)

        self.page_zoom_slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.page_zoom_slider.setRange(60, 200)
        self.page_zoom_slider.setValue(self.thumbnail_size)
        self.page_zoom_slider.setTickInterval(10)
        self.page_zoom_slider.valueChanged.connect(self._handle_thumbnail_resize)

        self.page_filter_input = QtWidgets.QLineEdit()
        self.page_filter_input.setPlaceholderText("ラベルでフィルター")
        self.page_filter_input.setClearButtonEnabled(True)
        self.page_filter_input.textChanged.connect(self._handle_page_filter_changed)

        self.page_label_input = QtWidgets.QLineEdit()
        self.page_label_input.setPlaceholderText("ページラベル")
        self.page_label_input.setClearButtonEnabled(True)
        self.page_label_input.editingFinished.connect(self._handle_page_label_edited)

        self.page_note_input = QtWidgets.QPlainTextEdit()
        self.page_note_input.setPlaceholderText("メモ")
        self.page_note_input.setMinimumHeight(110)
        self.page_note_input.textChanged.connect(self._handle_page_note_changed)

        page_panel = QtWidgets.QWidget()
        page_panel.setMinimumWidth(320)
        page_panel.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Expanding)
        page_panel.setObjectName("SidePanel")
        page_layout = QtWidgets.QVBoxLayout(page_panel)
        page_layout.setContentsMargins(12, 12, 12, 12)
        page_layout.setSpacing(12)

        nav_card, nav_layout = self._create_card("ページを探す")
        nav_layout.addWidget(self.page_search)

        slider_layout = QtWidgets.QHBoxLayout()
        slider_label = QtWidgets.QLabel("サムネイルサイズ")
        slider_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        slider_layout.addWidget(slider_label)
        value_label = QtWidgets.QLabel(f"{self.thumbnail_size}px")
        value_label.setObjectName("ThumbnailValueLabel")
        slider_layout.addWidget(value_label, alignment=QtCore.Qt.AlignRight)
        self.thumbnail_value_label = value_label
        nav_layout.addLayout(slider_layout)
        nav_layout.addWidget(self.page_zoom_slider)
        nav_layout.addWidget(self.page_filter_input)
        page_layout.addWidget(nav_card)

        list_card, list_layout = self._create_card("ページ一覧")
        list_layout.addWidget(self.page_list)
        list_tab = QtWidgets.QWidget()
        list_tab_layout = QtWidgets.QVBoxLayout(list_tab)
        list_tab_layout.setContentsMargins(0, 0, 0, 0)
        list_tab_layout.setSpacing(12)
        list_tab_layout.addWidget(nav_card)
        list_tab_layout.addWidget(list_card, stretch=1)

        meta_card, meta_layout = self._create_card("ページメモ")
        meta_layout.addWidget(self._create_field_label("ラベル"))
        meta_layout.addWidget(self.page_label_input)
        meta_layout.addWidget(self._create_field_label("メモ"))
        meta_layout.addWidget(self.page_note_input)
        meta_tab = QtWidgets.QWidget()
        meta_tab_layout = QtWidgets.QVBoxLayout(meta_tab)
        meta_tab_layout.setContentsMargins(0, 0, 0, 0)
        meta_tab_layout.setSpacing(12)
        meta_tab_layout.addWidget(meta_card)
        meta_tab_layout.addStretch(1)

        page_tabs = QtWidgets.QTabWidget()
        page_tabs.setObjectName("PageTabs")
        page_tabs.addTab(list_tab, "一覧")
        page_tabs.addTab(meta_tab, "メモ")
        page_layout.addWidget(page_tabs, stretch=1)

        self.canvas = PageCanvas()
        self.canvas.setObjectName("PageCanvas")
        self.canvas.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.canvas.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.canvas.selectionChanged.connect(self._handle_selection_changed)
        self.canvas.elementGeometryEdited.connect(self._handle_canvas_geometry_edited)
        self.canvas.customContextMenuRequested.connect(self._show_canvas_context_menu)

        self.setCentralWidget(self.canvas)

        pages_dock = QtWidgets.QDockWidget("Pages", self)
        pages_dock.setObjectName("PagesDock")
        pages_dock.setWidget(page_panel)
        pages_dock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        pages_dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetMovable
            | QtWidgets.QDockWidget.DockWidgetFloatable
            | QtWidgets.QDockWidget.DockWidgetClosable
        )
        pages_dock.setMinimumWidth(340)
        self.addDockWidget(QtCore.Qt.LeftDockWidgetArea, pages_dock)
        self.resizeDocks([pages_dock], [360], QtCore.Qt.Horizontal)

        self.property_panel = PropertyPanel()
        self.property_panel.setObjectName("PropertyPanel")
        self.property_panel.geometryEdited.connect(self._handle_property_geometry_edited)
        self.property_panel.opacityEdited.connect(self._handle_property_opacity_changed)

        prop_dock = QtWidgets.QDockWidget("Properties", self)
        prop_dock.setObjectName("PropertiesDock")
        prop_dock.setWidget(self.property_panel)
        prop_dock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, prop_dock)

        self.layer_tree = QtWidgets.QTreeWidget()
        self.layer_tree.setColumnCount(3)
        self.layer_tree.setHeaderLabels(["要素", "表示", "ロック"])
        self.layer_tree.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.layer_tree.setAlternatingRowColors(True)
        self.layer_tree.setRootIsDecorated(False)
        self.layer_tree.itemChanged.connect(self._handle_layer_item_changed)
        self.layer_tree.itemSelectionChanged.connect(self._handle_layer_selection_changed)
        layers_dock = QtWidgets.QDockWidget("Layers", self)
        layers_dock.setObjectName("LayersDock")
        layers_dock.setWidget(self.layer_tree)
        layers_dock.setAllowedAreas(QtCore.Qt.RightDockWidgetArea)
        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, layers_dock)
        self.tabifyDockWidget(prop_dock, layers_dock)
        prop_dock.raise_()

        if hasattr(self, "view_menu") and self.view_menu:
            self.view_menu.addSeparator()
            self.view_menu.addAction(pages_dock.toggleViewAction())
            self.view_menu.addAction(prop_dock.toggleViewAction())
            self.view_menu.addAction(layers_dock.toggleViewAction())

        status = self.statusBar()
        status.showMessage("PDF を開いて編集を開始してください。")
        self.page_status_label = QtWidgets.QLabel("Page 0/0")
        self.selection_status_label = QtWidgets.QLabel("選択なし")
        status.addPermanentWidget(self.page_status_label)
        status.addPermanentWidget(self.selection_status_label)
        self.autosave_status_label = QtWidgets.QLabel("AutoSave: Idle")
        status.addPermanentWidget(self.autosave_status_label)
        self.autosave_status_label.setText("AutoSave: 保存済み")

    def _create_card(self, title: str) -> tuple[QtWidgets.QFrame, QtWidgets.QVBoxLayout]:
        card = QtWidgets.QFrame()
        card.setObjectName("Card")
        layout = QtWidgets.QVBoxLayout(card)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        heading = QtWidgets.QLabel(title)
        heading.setObjectName("CardTitle")
        heading.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        layout.addWidget(heading)
        return card, layout

    def _create_field_label(self, text: str) -> QtWidgets.QLabel:
        label = QtWidgets.QLabel(text)
        label.setObjectName("FieldLabel")
        label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        return label

    def _create_actions(self) -> None:
        self.open_action = QtGui.QAction("開く...", self)
        self.open_action.setShortcut(QtGui.QKeySequence.Open)
        self.open_action.setToolTip("PDFファイルを開く")
        self.open_action.triggered.connect(self._open_pdf)

        self.save_action = QtGui.QAction("名前を付けて保存...", self)
        self.save_action.setShortcut(QtGui.QKeySequence.SaveAs)
        self.save_action.setToolTip("編集済みPDFを保存")
        self.save_action.triggered.connect(self._export_pdf)
        self.save_action.setEnabled(False)

        self.insert_image_action = QtGui.QAction("画像挿入", self)
        self.insert_image_action.setShortcut("Ctrl+I")
        self.insert_image_action.setToolTip("画像をページへ挿入 (Ctrl+I)")
        self.insert_image_action.triggered.connect(self._trigger_image_insertion)
        self.insert_image_action.setEnabled(False)

        self.delete_element_action = QtGui.QAction("選択要素を削除", self)
        self.delete_element_action.setShortcut(QtGui.QKeySequence.Delete)
        self.delete_element_action.setToolTip("選択した要素を削除 (Delete)")
        self.delete_element_action.triggered.connect(self._delete_selected_element)
        self.delete_element_action.setEnabled(False)

        self.duplicate_element_action = QtGui.QAction("選択要素を複製", self)
        self.duplicate_element_action.setShortcut("Ctrl+D")
        self.duplicate_element_action.setToolTip("選択した要素を複製 (Ctrl+D)")
        self.duplicate_element_action.triggered.connect(self._duplicate_selected_element)
        self.duplicate_element_action.setEnabled(False)

        self.edit_text_action = QtGui.QAction("テキスト編集", self)
        self.edit_text_action.setShortcut("Ctrl+T")
        self.edit_text_action.triggered.connect(self._edit_selected_text)
        self.edit_text_action.setEnabled(False)

        self.undo_action = QtGui.QAction("元に戻す", self)
        self.undo_action.setShortcut(QtGui.QKeySequence.Undo)
        self.undo_action.setToolTip("直前の操作を取り消す (Ctrl+Z)")
        self.undo_action.triggered.connect(self._undo)
        self.undo_action.setEnabled(False)

        self.redo_action = QtGui.QAction("やり直し", self)
        self.redo_action.setShortcut(QtGui.QKeySequence.Redo)
        self.redo_action.setToolTip("取り消した操作をやり直す (Ctrl+Shift+Z)")
        self.redo_action.triggered.connect(self._redo)
        self.redo_action.setEnabled(False)

        self.select_tool_action = QtGui.QAction("選択", self)
        self.select_tool_action.setCheckable(True)
        self.select_tool_action.setChecked(True)
        self.select_tool_action.triggered.connect(lambda: self._set_tool_mode("select"))

        self.text_tool_action = QtGui.QAction("テキスト", self)
        self.text_tool_action.setCheckable(True)
        self.text_tool_action.triggered.connect(lambda: self._set_tool_mode("text"))

        self.image_tool_mode_action = QtGui.QAction("画像", self)
        self.image_tool_mode_action.setCheckable(True)
        self.image_tool_mode_action.triggered.connect(lambda: self._set_tool_mode("image"))

        self.shape_tool_action = QtGui.QAction("図形", self)
        self.shape_tool_action.setCheckable(True)
        self.shape_tool_action.triggered.connect(lambda: self._set_tool_mode("shape"))

        self.tool_action_group = QtGui.QActionGroup(self)
        self.tool_action_group.setExclusive(True)
        for action in (
            self.select_tool_action,
            self.text_tool_action,
            self.image_tool_mode_action,
            self.shape_tool_action,
        ):
            self.tool_action_group.addAction(action)

        self.add_page_action = QtGui.QAction("ページ追加", self)
        self.add_page_action.setShortcut("Ctrl+Shift+N")
        self.add_page_action.triggered.connect(self._add_blank_page)
        self.add_page_action.setEnabled(False)

        self.remove_page_action = QtGui.QAction("ページ削除", self)
        self.remove_page_action.triggered.connect(self._remove_current_page)
        self.remove_page_action.setEnabled(False)

        self.move_page_up_action = QtGui.QAction("ページを上へ", self)
        self.move_page_up_action.setShortcut("Ctrl+PgUp")
        self.move_page_up_action.triggered.connect(self._move_page_up)
        self.move_page_up_action.setEnabled(False)

        self.move_page_down_action = QtGui.QAction("ページを下へ", self)
        self.move_page_down_action.setShortcut("Ctrl+PgDown")
        self.move_page_down_action.triggered.connect(self._move_page_down)
        self.move_page_down_action.setEnabled(False)

        self.bring_forward_action = QtGui.QAction("前面へ移動", self)
        self.bring_forward_action.triggered.connect(self._bring_selected_to_front)
        self.bring_forward_action.setEnabled(False)

        self.send_backward_action = QtGui.QAction("背面へ移動", self)
        self.send_backward_action.triggered.connect(self._send_selected_to_back)
        self.send_backward_action.setEnabled(False)

        self.shortcut_help_action = QtGui.QAction("ショートカット一覧", self)
        self.shortcut_help_action.setShortcut("F1")
        self.shortcut_help_action.triggered.connect(self._show_shortcut_overlay)

        self.toggle_grid_action = QtGui.QAction("グリッドを表示", self)
        self.toggle_grid_action.setCheckable(True)
        self.toggle_grid_action.toggled.connect(self._set_grid_visible)
        self.toggle_grid_action.setEnabled(False)

        self.settings_action = QtGui.QAction("設定...", self)
        self.settings_action.triggered.connect(self._open_settings_dialog)

        style = self.style()
        self.open_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_DialogOpenButton))
        self.save_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_DialogSaveButton))
        self.insert_image_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_FileIcon))
        self.delete_element_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_TrashIcon))
        self.duplicate_element_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        self.undo_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_ArrowBack))
        self.redo_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_ArrowForward))
        self.add_page_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_FileDialogNewFolder))
        self.remove_page_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_DialogCancelButton))
        self.move_page_up_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_ArrowUp))
        self.move_page_down_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_ArrowDown))
        self.bring_forward_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_ArrowUp))
        self.send_backward_action.setIcon(style.standardIcon(QtWidgets.QStyle.SP_ArrowDown))

    def _create_menu(self) -> None:
        file_menu = self.menuBar().addMenu("ファイル")
        file_menu.addAction(self.open_action)
        file_menu.addAction(self.save_action)

        edit_menu = self.menuBar().addMenu("編集")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.insert_image_action)
        edit_menu.addAction(self.duplicate_element_action)
        edit_menu.addAction(self.edit_text_action)
        edit_menu.addAction(self.delete_element_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.bring_forward_action)
        edit_menu.addAction(self.send_backward_action)

        page_menu = self.menuBar().addMenu("ページ")
        page_menu.addAction(self.add_page_action)
        page_menu.addAction(self.remove_page_action)
        page_menu.addSeparator()
        page_menu.addAction(self.move_page_up_action)
        page_menu.addAction(self.move_page_down_action)

        self.view_menu = self.menuBar().addMenu("表示")
        self.view_menu.addAction(self.toggle_grid_action)

        settings_menu = self.menuBar().addMenu("設定")
        settings_menu.addAction(self.settings_action)

        help_menu = self.menuBar().addMenu("ヘルプ")
        help_menu.addAction(self.shortcut_help_action)

        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setIconSize(QtCore.QSize(22, 22))
        toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        toolbar.addAction(self.open_action)
        toolbar.addAction(self.save_action)
        toolbar.addSeparator()
        toolbar.addAction(self.insert_image_action)
        toolbar.addAction(self.duplicate_element_action)
        toolbar.addAction(self.edit_text_action)
        toolbar.addAction(self.delete_element_action)
        toolbar.addSeparator()
        toolbar.addAction(self.add_page_action)
        toolbar.addAction(self.remove_page_action)
        toolbar.addAction(self.move_page_up_action)
        toolbar.addAction(self.move_page_down_action)
        toolbar.addAction(self.toggle_grid_action)
        toolbar.addSeparator()
        toolbar.addAction(self.bring_forward_action)
        toolbar.addAction(self.send_backward_action)
        toolbar.addSeparator()
        toolbar.addAction(self.undo_action)
        toolbar.addAction(self.redo_action)

        tool_mode_toolbar = QtWidgets.QToolBar("Tools")
        tool_mode_toolbar.setMovable(False)
        tool_mode_toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextUnderIcon)
        tool_mode_toolbar.addAction(self.select_tool_action)
        tool_mode_toolbar.addAction(self.text_tool_action)
        tool_mode_toolbar.addAction(self.image_tool_mode_action)
        tool_mode_toolbar.addAction(self.shape_tool_action)
        self.addToolBar(QtCore.Qt.TopToolBarArea, tool_mode_toolbar)

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
        self.toggle_grid_action.setEnabled(True)
        self.toggle_grid_action.setChecked(False)
        self.canvas.set_grid_visible(False)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self._update_history_actions()
        self._selected_elements = []
        self._selected_element = None
        self._update_selection_actions()
        self.statusBar().showMessage(f"{path.name} を読み込みました。")
        self._update_page_actions()
        self._update_status_labels()

        if self.document.page_count:
            self._select_page_row(0)
        else:
            self._update_status_labels()
            self._update_page_metadata_fields()

    def _build_pixmaps(self, previews: List[PagePreview]) -> Dict[str, QtGui.QPixmap]:
        pixmaps: Dict[str, QtGui.QPixmap] = {}
        for preview in previews:
            pixmap = QtGui.QPixmap()
            pixmap.loadFromData(preview.image_bytes, "PNG")
            pixmaps[preview.page_id] = pixmap
        return pixmaps

    def _populate_page_list(self) -> None:
        self.page_list.clear()
        if not self.document:
            return
        filter_text = self.page_filter_text or ""
        filter_text_lower = filter_text.lower()
        for index, page in enumerate(self.document.pages):
            if filter_text_lower and filter_text_lower not in page.label.lower():
                continue
            pixmap = self._get_page_pixmap(page)
            icon = QtGui.QIcon(
                pixmap.scaled(
                    self.thumbnail_size,
                    int(self.thumbnail_size * 1.4),
                    QtCore.Qt.KeepAspectRatio,
                    QtCore.Qt.SmoothTransformation,
                )
            )
            label = f"Page {index + 1}"
            if page.label:
                label += f": {page.label}"
            item = QtWidgets.QListWidgetItem(icon, label)
            item.setData(QtCore.Qt.UserRole, page.uid)
            if page.note:
                item.setToolTip(page.note)
            self.page_list.addItem(item)
        if self.page_list.count() == 0:
            self._handle_page_change(-1)
        elif self.current_page_index is not None:
            self._select_page_row(self.current_page_index)

    def _handle_page_change(self, index: int) -> None:
        if not self.document or index < 0:
            self.current_page_index = None
            self.canvas.clear()
            self.property_panel.set_element(None)
            self._selected_element = None
            self._selected_elements = []
            self.delete_element_action.setEnabled(False)
            self.duplicate_element_action.setEnabled(False)
            self.bring_forward_action.setEnabled(False)
            self.send_backward_action.setEnabled(False)
            self._update_page_actions()
            self._update_status_labels()
            if hasattr(self, "layer_tree"):
                self.layer_tree.clear()
            self._update_page_metadata_fields()
            return
        item = self.page_list.item(index)
        if not item:
            return
        page_id = item.data(QtCore.Qt.UserRole)
        page_index = self.document.index_of_page(page_id) if page_id else None
        if page_index is None:
            return
        self.current_page_index = page_index
        page = self.document.get_page(page_index)
        pixmap = self._get_page_pixmap(page)
        self.property_panel.set_page_size(page.width, page.height)
        self.canvas.set_page(page, pixmap)
        self.property_panel.set_element(None)
        self._selected_element = None
        self._selected_elements = []
        self.delete_element_action.setEnabled(False)
        self.duplicate_element_action.setEnabled(False)
        self.bring_forward_action.setEnabled(False)
        self.send_backward_action.setEnabled(False)
        self._update_page_actions()
        self._update_status_labels()
        self._update_page_metadata_fields()

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
        self._push_history("insert", page.uid, element)
        self._mark_unsaved()
        self._refresh_canvas([element.id])

    def _trigger_image_insertion(self) -> None:
        if not self.insert_image_action.isEnabled():
            return
        self.image_tool_mode_action.setChecked(True)
        self._set_tool_mode("image")

    def _insert_text(self) -> None:
        if not self.document or self.current_page_index is None:
            QtWidgets.QMessageBox.information(self, "テキスト挿入", "PDFを開いてからテキストを追加できます。")
            return
        dialog = TextEditDialog(self)
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        values = dialog.values()
        text = values["text"]
        if not text:
            return
        font_size = values["font_size"]
        font = QtGui.QFont("Noto Sans", int(font_size))
        metrics = QtGui.QFontMetrics(font)
        lines = text.splitlines() or [" "]
        width = max(metrics.horizontalAdvance(line) for line in lines) + 20
        height = metrics.lineSpacing() * len(lines) + 20
        page = self.document.get_page(self.current_page_index)
        width = min(width, page.width * 0.9)
        height = min(height, page.height * 0.9)
        x = max(0.0, (page.width - width) / 2)
        y = max(0.0, (page.height - height) / 2)
        element = create_text_element(
            x=x,
            y=y,
            width=width,
            height=height,
            text=text,
            font_size=font_size,
            color=values["color"],
        )
        page.add_element(element)
        self._push_history("insert", page.uid, element)
        self._mark_unsaved()
        self._refresh_canvas([element.id])

    def _set_tool_mode(self, mode: str) -> None:
        self.current_tool = mode
        if mode == "select":
            self.statusBar().showMessage("選択モード", 2000)
            return
        if mode == "image":
            if not self.document or self.current_page_index is None:
                QtWidgets.QMessageBox.information(self, "画像挿入", "画像を挿入するにはページを開いてください。")
                self.select_tool_action.setChecked(True)
                self.current_tool = "select"
                return
            self.statusBar().showMessage("画像挿入モード: 画像ファイルを選択してください。", 3000)
            self._insert_image()
            self.select_tool_action.setChecked(True)
            self.current_tool = "select"
            return
        if mode == "text":
            self._insert_text()
            self.select_tool_action.setChecked(True)
            self.current_tool = "select"
            return
        if mode == "shape":
            QtWidgets.QMessageBox.information(
                self,
                "ツール",
                "このツールは次のアップデートで提供予定です。現在は選択モードをご利用ください。",
            )
            self.select_tool_action.setChecked(True)
            self.current_tool = "select"

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
        self._unsaved_changes = False
        self.autosave_status_label.setText("AutoSave: 保存済み")

    def _refresh_canvas(self, select_element_ids: Optional[List[str]] = None) -> None:
        if not self.document or self.current_page_index is None:
            return
        page = self.document.get_page(self.current_page_index)
        pixmap = self._get_page_pixmap(page)
        self.canvas.set_page(page, pixmap)
        self._rebuild_layer_panel()
        if select_element_ids:
            self.canvas.select_elements(select_element_ids)
        else:
            self.canvas.select_elements([])

    def _handle_selection_changed(self, elements: List[Element]) -> None:
        self._selected_elements = elements
        self._selected_element = elements[0] if elements else None
        if elements:
            self.property_panel.set_element(elements[0])
        else:
            self.property_panel.set_element(None)
        self._update_selection_actions()
        self._update_status_labels()
        self._sync_layer_selection()

    def _handle_canvas_geometry_edited(self, element: Element) -> None:
        if self._selected_element and element.id == self._selected_element.id:
            self._selected_element = element
            self.property_panel.set_element(element)
        self._update_status_labels()
        self._mark_unsaved()

    def _handle_property_geometry_edited(self, x: float, y: float, width: float, height: float) -> None:
        if not self.document or self.current_page_index is None:
            return
        element = self._selected_element
        if not element:
            return
        element.move_to(x, y)
        element.resize(width, height)
        self.canvas.sync_from_model(element)
        self._selected_element = element
        self._update_status_labels()
        self._mark_unsaved()

    def _handle_property_opacity_changed(self, opacity: float) -> None:
        if not self.document or self.current_page_index is None or not self._selected_element:
            return
        self._selected_element.opacity = opacity
        self.canvas.sync_from_model(self._selected_element)
        self._update_status_labels()
        self._mark_unsaved()

    def _delete_selected_element(self) -> None:
        if not self.document or self.current_page_index is None or not self._selected_elements:
            return
        if len(self._selected_elements) > 1:
            reply = QtWidgets.QMessageBox.question(
                self,
                "要素の削除",
                f"{len(self._selected_elements)} 個の要素を削除しますか？",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            )
            if reply != QtWidgets.QMessageBox.Yes:
                return
        page = self.document.get_page(self.current_page_index)
        removed_any = False
        for element in list(self._selected_elements):
            removed = page.remove_element(element.id)
            if removed:
                self._push_history("delete", page.uid, removed)
                removed_any = True
        if removed_any:
            self._selected_elements = []
            self._selected_element = None
            self.property_panel.set_element(None)
            self._update_selection_actions()
            self._refresh_canvas()
            self._update_status_labels()
            self._mark_unsaved()

    def _add_blank_page(self) -> None:
        if not self.document:
            QtWidgets.QMessageBox.information(self, "操作不可", "PDFを開いた後にページを追加できます。")
            return
        insert_index = (
            self.current_page_index + 1 if self.current_page_index is not None else self.document.page_count
        )
        reference_page: Optional[PageModel] = None
        if self.current_page_index is not None and 0 <= self.current_page_index < self.document.page_count:
            reference_page = self.document.get_page(self.current_page_index)
        elif self.document.page_count:
            reference_page = self.document.get_page(0)

        width = reference_page.width if reference_page else self.default_page_width
        height = reference_page.height if reference_page else self.default_page_height

        new_page = PageModel(width=width, height=height, rotation=0, source_index=None)
        self.document.insert_page(insert_index, new_page)
        self.page_pixmaps[new_page.uid] = self._create_blank_pixmap(width, height)

        self._populate_page_list()
        self._select_page_row(insert_index)
        self.statusBar().showMessage("空白ページを追加しました。", 3000)
        self._update_page_actions()
        self._update_status_labels()
        self._mark_unsaved()

    def _remove_current_page(self) -> None:
        if not self.document or self.current_page_index is None:
            return
        if self.document.page_count <= 1:
            QtWidgets.QMessageBox.information(self, "削除不可", "最後の1ページは削除できません。")
            return
        reply = QtWidgets.QMessageBox.question(
            self,
            "ページ削除",
            "選択中のページを削除しますか？",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        removed_page = self.document.remove_page(self.current_page_index)
        self.page_pixmaps.pop(removed_page.uid, None)
        new_index = min(self.current_page_index, self.document.page_count - 1)
        self._populate_page_list()
        if new_index >= 0:
            self._select_page_row(new_index)
        else:
            self.page_list.clearSelection()
            self.canvas.clear()
        self.statusBar().showMessage("ページを削除しました。", 3000)
        self._update_page_actions()
        self._update_status_labels()
        self._mark_unsaved()

    def _move_page_up(self) -> None:
        if not self.document or self.current_page_index in (None, 0):
            return
        idx = self.current_page_index
        self.document.pages[idx - 1], self.document.pages[idx] = self.document.pages[idx], self.document.pages[idx - 1]
        self._populate_page_list()
        self._select_page_row(idx - 1)
        self.statusBar().showMessage("ページを上に移動しました。", 3000)
        self._update_page_actions()
        self._update_status_labels()
        self._mark_unsaved()

    def _move_page_down(self) -> None:
        if (
            not self.document
            or self.current_page_index is None
            or self.current_page_index >= self.document.page_count - 1
        ):
            return
        idx = self.current_page_index
        self.document.pages[idx + 1], self.document.pages[idx] = self.document.pages[idx], self.document.pages[idx + 1]
        self._populate_page_list()
        self._select_page_row(idx + 1)
        self.statusBar().showMessage("ページを下に移動しました。", 3000)
        self._update_page_actions()
        self._update_status_labels()
        self._mark_unsaved()

    def _duplicate_selected_element(self) -> None:
        if not self.document or self.current_page_index is None or not self._selected_elements:
            return
        page = self.document.get_page(self.current_page_index)
        new_ids: List[str] = []
        offset = 20
        for index, element in enumerate(self._selected_elements):
            x = min(page.width - element.rect.width, element.rect.x + offset * (index + 1))
            y = min(page.height - element.rect.height, element.rect.y + offset * (index + 1))
            if isinstance(element, ImageElement):
                new_element = create_image_element(
                    x=x,
                    y=y,
                    width=element.rect.width,
                    height=element.rect.height,
                    source_path=element.source_path,
                    image_bytes=element.image_bytes,
                )
                new_element.opacity = element.opacity
            elif isinstance(element, TextElement):
                new_element = create_text_element(
                    x=x,
                    y=y,
                    width=element.rect.width,
                    height=element.rect.height,
                    text=element.text,
                    font_family=element.font_family,
                    font_size=element.font_size,
                    color=element.color,
                )
                new_element.opacity = element.opacity
            else:
                continue
            page.add_element(new_element)
            self._push_history("insert", page.uid, new_element)
            new_ids.append(new_element.id)
        if new_ids:
            self.statusBar().showMessage("要素を複製しました。", 2000)
            self._refresh_canvas(new_ids)
            self._mark_unsaved()

    def _bring_selected_to_front(self) -> None:
        if not self.document or self.current_page_index is None or not self._selected_elements:
            return
        page = self.document.get_page(self.current_page_index)
        for element in self._selected_elements:
            page.elements = [elem for elem in page.elements if elem.id != element.id]
            page.elements.append(element)
        self._refresh_canvas([elem.id for elem in self._selected_elements])
        self.statusBar().showMessage("要素を前面に移動しました。", 2000)
        self._mark_unsaved()

    def _send_selected_to_back(self) -> None:
        if not self.document or self.current_page_index is None or not self._selected_elements:
            return
        page = self.document.get_page(self.current_page_index)
        for element in reversed(self._selected_elements):
            page.elements = [elem for elem in page.elements if elem.id != element.id]
            page.elements.insert(0, element)
        self._refresh_canvas([elem.id for elem in self._selected_elements])
        self.statusBar().showMessage("要素を背面に移動しました。", 2000)
        self._mark_unsaved()

    def _edit_selected_text(self) -> None:
        if not self._selected_element or not isinstance(self._selected_element, TextElement):
            return
        element: TextElement = self._selected_element
        dialog = TextEditDialog(
            self,
            text=element.text,
            font_size=element.font_size,
            color=element.color,
        )
        if dialog.exec() != QtWidgets.QDialog.Accepted:
            return
        values = dialog.values()
        if not values["text"]:
            QtWidgets.QMessageBox.warning(self, "テキスト", "テキストが空です。")
            return
        element.text = values["text"]
        element.font_size = values["font_size"]
        element.color = values["color"]
        self.canvas.sync_from_model(element)
        self._mark_unsaved()

    def _push_history(self, action: str, page_id: str, element: Element) -> None:
        command = HistoryCommand(
            action=action,
            page_id=page_id,
            element=clone_element(element),
        )
        self.undo_stack.append(command)
        self.redo_stack.clear()
        self._update_history_actions()

    def _undo(self) -> None:
        if not self.document or not self.undo_stack:
            return
        command = self.undo_stack.pop()
        self._apply_history_command(command, undo=True)
        self.redo_stack.append(command)
        self._update_history_actions()

    def _redo(self) -> None:
        if not self.document or not self.redo_stack:
            return
        command = self.redo_stack.pop()
        self._apply_history_command(command, undo=False)
        self.undo_stack.append(command)
        self._update_history_actions()

    def _apply_history_command(self, command: HistoryCommand, undo: bool) -> None:
        if not self.document:
            return
        page = self.document.find_page_by_id(command.page_id)
        if not page:
            return
        element = clone_element(command.element)

        if command.action == "insert":
            if undo:
                page.remove_element(element.id)
                select_id: Optional[str] = None
            else:
                page.add_element(element)
                select_id = element.id
        elif command.action == "delete":
            if undo:
                page.add_element(element)
                select_id = element.id
            else:
                page.remove_element(element.id)
                select_id = None
        else:
            return

        if (
            self.current_page_index is not None
            and self.document.get_page(self.current_page_index).uid == command.page_id
        ):
            if select_id:
                self._refresh_canvas([select_id])
            else:
                self._selected_element = None
                self.property_panel.set_element(None)
                self._refresh_canvas()

    def _update_history_actions(self) -> None:
        self.undo_action.setEnabled(bool(self.undo_stack))
        self.redo_action.setEnabled(bool(self.redo_stack))

    def _handle_thumbnail_resize(self, value: int) -> None:
        self.thumbnail_size = value
        self.thumbnail_value_label.setText(f"{value}px")
        self.page_list.setIconSize(QtCore.QSize(value, int(value * 1.4)))
        if self.document:
            current_index = self.current_page_index
            self._populate_page_list()
            if current_index is not None:
                self._select_page_row(current_index)

    def _handle_page_jump(self) -> None:
        text = self.page_search.text().strip()
        if not text or not self.document:
            return
        try:
            page_number = int(text)
        except ValueError:
            self.statusBar().showMessage("ページ番号を整数で入力してください。", 3000)
            return
        if not (1 <= page_number <= self.document.page_count):
            self.statusBar().showMessage("ページ番号が範囲外です。", 3000)
            return
        target_index = page_number - 1
        if target_index < 0 or target_index >= self.document.page_count:
            return
        target_id = self.document.get_page(target_index).uid
        for row in range(self.page_list.count()):
            item = self.page_list.item(row)
            if item and item.data(QtCore.Qt.UserRole) == target_id:
                self.page_list.setCurrentRow(row)
                self.statusBar().showMessage(f"ページ {page_number} へ移動", 2000)
                return
        self.statusBar().showMessage("フィルターの条件によりページが表示されていません。", 3000)

    def _update_status_labels(self) -> None:
        total = self.document.page_count if self.document else 0
        current = self.current_page_index + 1 if self.document and self.current_page_index is not None else 0
        self.page_status_label.setText(f"Page {current}/{total}")
        if self._selected_element:
            rect = self._selected_element.rect
            if len(self._selected_elements) > 1:
                self.selection_status_label.setText(f"{len(self._selected_elements)} 個選択中")
            else:
                self.selection_status_label.setText(
                    f"選択: {int(rect.width)}×{int(rect.height)} pt @ ({int(rect.x)}, {int(rect.y)})"
                )
        else:
            self.selection_status_label.setText("選択なし")

    def _update_selection_actions(self) -> None:
        has_selection = bool(self._selected_elements)
        self.delete_element_action.setEnabled(has_selection)
        self.duplicate_element_action.setEnabled(has_selection)
        self.bring_forward_action.setEnabled(has_selection)
        self.send_backward_action.setEnabled(has_selection)
        single_text = has_selection and len(self._selected_elements) == 1 and isinstance(
            self._selected_elements[0], TextElement
        )
        self.edit_text_action.setEnabled(single_text)

    def _set_grid_visible(self, checked: bool) -> None:
        self.canvas.set_grid_visible(checked)

    def _rebuild_layer_panel(self) -> None:
        if not self.layer_tree:
            return
        self._layer_panel_updating = True
        self.layer_tree.clear()
        if not self.document or self.current_page_index is None:
            self._layer_panel_updating = False
            return
        page = self.document.get_page(self.current_page_index)
        for element in reversed(page.elements):
            if isinstance(element, TextElement):
                preview = element.text.splitlines()[0] if element.text else "Text"
                label = f"Text: {preview[:15]}"
            elif isinstance(element, ImageElement):
                label = element.source_path.name if element.source_path else f"Image {element.id[:6]}"
            else:
                label = f"Element {element.id[:6]}"
            item = QtWidgets.QTreeWidgetItem([label, "", ""])
            item.setData(0, QtCore.Qt.UserRole, element.id)
            item.setFlags(
                QtCore.Qt.ItemIsEnabled
                | QtCore.Qt.ItemIsSelectable
                | QtCore.Qt.ItemIsUserCheckable
            )
            item.setCheckState(1, QtCore.Qt.Checked if element.visible else QtCore.Qt.Unchecked)
            item.setCheckState(2, QtCore.Qt.Checked if element.locked else QtCore.Qt.Unchecked)
            self.layer_tree.addTopLevelItem(item)
        self.layer_tree.resizeColumnToContents(0)
        self._layer_panel_updating = False
        self._sync_layer_selection()

    def _handle_layer_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if self._layer_panel_updating or not self.document or self.current_page_index is None:
            return
        element_id = item.data(0, QtCore.Qt.UserRole)
        if not element_id:
            return
        page = self.document.get_page(self.current_page_index)
        element = page.find_element(element_id)
        if not element:
            return
        if column == 1:
            visible = item.checkState(1) == QtCore.Qt.Checked
            element.visible = visible
            self.canvas.update_element_visibility(element_id, visible)
            self._mark_unsaved()
        elif column == 2:
            locked = item.checkState(2) == QtCore.Qt.Checked
            element.locked = locked
            self.canvas.update_element_lock(element_id, locked)
            self._mark_unsaved()

    def _handle_layer_selection_changed(self) -> None:
        if self._layer_panel_updating:
            return
        ids = []
        for item in self.layer_tree.selectedItems():
            element_id = item.data(0, QtCore.Qt.UserRole)
            if element_id:
                ids.append(element_id)
        if ids:
            self.canvas.select_elements(ids)
        else:
            self.canvas.select_elements([])

    def _sync_layer_selection(self) -> None:
        if self._layer_panel_updating:
            return
        self._layer_panel_updating = True
        self.layer_tree.blockSignals(True)
        self.layer_tree.clearSelection()
        selected_ids = {element.id for element in self._selected_elements}
        for index in range(self.layer_tree.topLevelItemCount()):
            item = self.layer_tree.topLevelItem(index)
            if item.data(0, QtCore.Qt.UserRole) in selected_ids:
                item.setSelected(True)
        self.layer_tree.blockSignals(False)
        self._layer_panel_updating = False

    def _handle_page_filter_changed(self, text: str) -> None:
        self.page_filter_text = text.strip().lower()
        self._populate_page_list()
        self._update_page_metadata_fields()

    def _handle_page_label_edited(self) -> None:
        if (
            self._page_metadata_updating
            or not self.document
            or self.current_page_index is None
        ):
            return
        page = self.document.get_page(self.current_page_index)
        page.label = self.page_label_input.text().strip()
        self._populate_page_list()
        self._mark_unsaved()

    def _handle_page_note_changed(self) -> None:
        if (
            self._page_metadata_updating
            or not self.document
            or self.current_page_index is None
        ):
            return
        page = self.document.get_page(self.current_page_index)
        page.note = self.page_note_input.toPlainText().strip()
        self._mark_unsaved()

    def _update_page_metadata_fields(self) -> None:
        self._page_metadata_updating = True
        if not self.document or self.current_page_index is None:
            self.page_label_input.clear()
            self.page_note_input.clear()
        else:
            page = self.document.get_page(self.current_page_index)
            self.page_label_input.setText(page.label)
            self.page_note_input.setPlainText(page.note)
        self._page_metadata_updating = False

    def _select_page_row(self, page_index: int) -> None:
        if not self.document or page_index < 0 or page_index >= self.document.page_count:
            return
        target_id = self.document.get_page(page_index).uid
        current_item = self.page_list.currentItem()
        current_id = current_item.data(QtCore.Qt.UserRole) if current_item else None
        if current_id == target_id:
            return
        self.page_list.blockSignals(True)
        matched_row = -1
        for row in range(self.page_list.count()):
            item = self.page_list.item(row)
            if item and item.data(QtCore.Qt.UserRole) == target_id:
                self.page_list.setCurrentRow(row)
                matched_row = row
                break
        self.page_list.blockSignals(False)
        if matched_row >= 0:
            self._handle_page_change(matched_row)
        else:
            self.page_list.clearSelection()

    def _open_settings_dialog(self) -> None:
        dialog = SettingsDialog(
            self,
            self.available_themes,
            self.current_theme,
            self.thumbnail_size,
            self.default_page_width,
            self.default_page_height,
        )
        if dialog.exec():
            values = dialog.values()
            self.current_theme = values["theme"]
            self.thumbnail_size = int(values["thumbnail_size"])
            self.default_page_width = float(values["default_page_width"])
            self.default_page_height = float(values["default_page_height"])
            self.settings.setValue("theme", self.current_theme)
            self.settings.setValue("thumbnail_size", self.thumbnail_size)
            self.settings.setValue("default_page_width", self.default_page_width)
            self.settings.setValue("default_page_height", self.default_page_height)
            self.page_zoom_slider.setValue(self.thumbnail_size)
            self._apply_theme(self.current_theme)

    def _apply_theme(self, theme_name: str) -> None:
        app = QtWidgets.QApplication.instance()
        if not app:
            return
        apply_stylesheet(app, theme=theme_name)
        self._palette = self._palette_for_theme(theme_name)
        base_stylesheet = app.styleSheet()
        app.setStyleSheet(base_stylesheet + self._build_stylesheet(self._palette))
        self.canvas.setBackgroundBrush(QtGui.QColor(self._palette["canvas_bg"]))
        self.statusBar().setStyleSheet(
            f"background:{self._palette['panel']};"
            f"color:{self._palette['muted_text']};"
            f"border-top:1px solid {self._palette['border']};"
        )
        self.statusBar().showMessage(f"テーマを {theme_name} に変更しました。", 3000)

    def _palette_for_theme(self, theme_name: str) -> Dict[str, str]:
        is_light = theme_name.startswith("light")
        if is_light:
            return {
                "surface": "#f6f8fb",
                "panel": "#ffffff",
                "card": "#ffffff",
                "border": "#d8e0ea",
                "hover": "#eef3fb",
                "accent": "#2d6cdf",
                "accent_soft": "#dfe9fb",
                "accent_hover": "#1f5fc4",
                "text": "#1f2933",
                "muted_text": "#516076",
                "canvas_bg": "#eef2f7",
                "selection": "#e5edfa",
            }
        return {
            "surface": "#0f172a",
            "panel": "#0b1326",
            "card": "#0e1a2f",
            "border": "#1f2a44",
            "hover": "#15233a",
            "accent": "#5ab3f5",
            "accent_soft": "#12314f",
            "accent_hover": "#74c3ff",
            "text": "#e4edf7",
            "muted_text": "#9fb2c8",
            "canvas_bg": "#0a101e",
            "selection": "#1f3a5f",
        }

    def _build_stylesheet(self, colors: Dict[str, str]) -> str:
        return f"""
        /* Modern surface overrides */
        QWidget {{
            color: {colors['text']};
            font-family: "Inter", "Noto Sans", "Segoe UI", sans-serif;
            font-size: 11pt;
        }}
        QMainWindow {{
            background: {colors['surface']};
        }}
        QFrame#SidePanel {{
            background: {colors['panel']};
            border: 1px solid {colors['border']};
            border-radius: 14px;
        }}
        QFrame#Card {{
            background: {colors['card']};
            border: 1px solid {colors['border']};
            border-radius: 12px;
        }}
        QLabel#CardTitle {{
            font-size: 10pt;
            font-weight: 600;
            color: {colors['muted_text']};
            padding-bottom: 2px;
        }}
        QLabel#FieldLabel {{
            color: {colors['muted_text']};
            font-size: 9.5pt;
            padding-top: 2px;
        }}
        QLabel#ThumbnailValueLabel {{
            color: {colors['muted_text']};
        }}
        QGraphicsView#PageCanvas {{
            background: {colors['canvas_bg']};
            border: 1px solid {colors['border']};
            border-radius: 14px;
        }}
        QLineEdit,
        QPlainTextEdit,
        QSpinBox,
        QDoubleSpinBox,
        QComboBox {{
            background: {colors['surface']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-radius: 8px;
            padding: 8px 10px;
        }}
        QPlainTextEdit {{
            padding: 10px;
        }}
        QLineEdit:focus,
        QPlainTextEdit:focus,
        QSpinBox:focus,
        QDoubleSpinBox:focus,
        QComboBox:focus {{
            border: 1px solid {colors['accent']};
        }}
        QListWidget#PageList {{
            background: {colors['card']};
            border: 1px solid {colors['border']};
            border-radius: 12px;
            padding: 6px;
        }}
        QListWidget#PageList::item {{
            background: transparent;
            margin: 2px;
            padding: 10px 8px;
            border-radius: 10px;
        }}
        QListWidget#PageList::item:selected {{
            background: {colors['accent_soft']};
            border: 1px solid {colors['accent']};
            color: {colors['text']};
        }}
        QListWidget#PageList::item:hover {{
            background: {colors['hover']};
        }}
        QToolBar {{
            background: {colors['panel']};
            border: 1px solid {colors['border']};
            padding: 6px;
            spacing: 8px;
        }}
        QToolBar QToolButton {{
            padding: 6px 10px;
            border-radius: 10px;
        }}
        QToolBar QToolButton:hover {{
            background: {colors['hover']};
        }}
        QToolBar QToolButton:checked {{
            background: {colors['accent_soft']};
            border: 1px solid {colors['accent']};
        }}
        QStatusBar {{
            background: {colors['panel']};
            border-top: 1px solid {colors['border']};
            color: {colors['muted_text']};
        }}
        QDockWidget {{
            background: {colors['panel']};
            border: 1px solid {colors['border']};
        }}
        QDockWidget::title {{
            padding: 8px 10px;
            background: {colors['panel']};
            color: {colors['muted_text']};
            border-bottom: 1px solid {colors['border']};
        }}
        QTabWidget::pane {{
            border: 1px solid {colors['border']};
            border-radius: 10px;
            background: {colors['card']};
        }}
        QTabBar::tab {{
            background: {colors['panel']};
            color: {colors['muted_text']};
            padding: 8px 14px;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            margin-right: 2px;
        }}
        QTabBar::tab:selected {{
            background: {colors['card']};
            color: {colors['text']};
            border: 1px solid {colors['border']};
            border-bottom: 1px solid {colors['card']};
        }}
        QTreeWidget {{
            background: {colors['card']};
            border: 1px solid {colors['border']};
            border-radius: 10px;
        }}
        QTreeWidget::item:selected {{
            background: {colors['accent_soft']};
            color: {colors['text']};
        }}
        QSlider::groove:horizontal {{
            background: {colors['border']};
            height: 6px;
            border-radius: 4px;
        }}
        QSlider::handle:horizontal {{
            background: {colors['accent']};
            width: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        QPushButton {{
            background: {colors['accent']};
            color: #ffffff;
            border-radius: 10px;
            padding: 8px 14px;
            border: none;
        }}
        QPushButton:hover {{
            background: {colors['accent_hover']};
        }}
        QPushButton:disabled {{
            background: {colors['border']};
            color: {colors['muted_text']};
        }}
        QMenuBar {{
            background: {colors['panel']};
            border: none;
        }}
        QMenuBar::item:selected {{
            background: {colors['hover']};
        }}
        QMenu {{
            background: {colors['card']};
            border: 1px solid {colors['border']};
        }}
        QMenu::item:selected {{
            background: {colors['accent_soft']};
        }}
        """

    def _mark_unsaved(self) -> None:
        self._unsaved_changes = True
        self.autosave_status_label.setText("AutoSave: 未保存")

    def _handle_autosave_timeout(self) -> None:
        if not self._unsaved_changes or not self.document:
            return
        try:
            path = self._perform_autosave()
            if path:
                self.autosave_status_label.setText(f"AutoSave: {path.name}")
        except Exception as exc:  # pylint: disable=broad-except
            self.statusBar().showMessage(f"自動保存に失敗しました: {exc}", 5000)

    def _perform_autosave(self) -> Optional[Path]:
        if not self.document:
            return None
        autosave_dir = Path.home() / ".cache" / "pdf_editor"
        autosave_dir.mkdir(parents=True, exist_ok=True)
        source_name = self.document.source_path.stem if self.document.source_path else "document"
        target_path = autosave_dir / f"{source_name}_autosave.pdf"
        self.exporter.export(self.document, target_path)
        return target_path

    def _show_canvas_context_menu(self, position: QtCore.QPoint) -> None:
        if not self._selected_element:
            return
        menu = QtWidgets.QMenu(self)
        menu.addAction(self.duplicate_element_action)
        if len(self._selected_elements) == 1 and isinstance(self._selected_elements[0], TextElement):
            menu.addAction(self.edit_text_action)
        menu.addAction(self.delete_element_action)
        menu.addSeparator()
        menu.addAction(self.bring_forward_action)
        menu.addAction(self.send_backward_action)
        global_pos = self.canvas.mapToGlobal(position)
        menu.exec(global_pos)

    def _show_shortcut_overlay(self) -> None:
        shortcuts = [
            ("Ctrl+O", "PDFを開く"),
            ("Ctrl+S / Ctrl+Shift+S", "保存 / 名前を付けて保存"),
            ("Ctrl+I", "画像を挿入"),
            ("Ctrl+D", "選択要素を複製"),
            ("Delete", "選択要素を削除"),
            ("Ctrl+Z / Ctrl+Shift+Z", "元に戻す / やり直す"),
            ("Ctrl+Shift+N", "ページ追加"),
            ("Ctrl+PgUp / Ctrl+PgDn", "ページ移動 (上/下)"),
            ("F1", "ショートカット一覧を表示"),
            ("Ctrl+Mouse Wheel", "ズーム"),
        ]
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle("ショートカット一覧")
        layout = QtWidgets.QVBoxLayout(dialog)
        table = QtWidgets.QTableWidget(len(shortcuts), 2)
        table.setHorizontalHeaderLabels(["キー", "説明"])
        table.horizontalHeader().setStretchLastSection(True)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        for row, (keys, desc) in enumerate(shortcuts):
            table.setItem(row, 0, QtWidgets.QTableWidgetItem(keys))
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(desc))
        layout.addWidget(table)
        close_button = QtWidgets.QPushButton("閉じる")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button, alignment=QtCore.Qt.AlignRight)
        dialog.resize(420, 300)
        dialog.exec()

    def _get_page_pixmap(self, page: PageModel) -> QtGui.QPixmap:
        pixmap = self.page_pixmaps.get(page.uid)
        if pixmap is None or pixmap.isNull():
            pixmap = self._create_blank_pixmap(page.width, page.height)
            self.page_pixmaps[page.uid] = pixmap
        return pixmap

    def _create_blank_pixmap(self, width: float, height: float) -> QtGui.QPixmap:
        width_px = max(1, int(width))
        height_px = max(1, int(height))
        pixmap = QtGui.QPixmap(width_px, height_px)
        pixmap.fill(QtGui.QColor("#ffffff"))
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        pen = QtGui.QPen(QtGui.QColor("#c5c5c5"))
        pen.setStyle(QtCore.Qt.DotLine)
        pen.setWidth(2)
        painter.setPen(pen)
        margin = 4
        painter.drawRect(
            margin,
            margin,
            max(1, pixmap.width() - margin * 2),
            max(1, pixmap.height() - margin * 2),
        )
        painter.end()
        return pixmap

    def _update_page_actions(self) -> None:
        has_document = self.document is not None
        page_count = self.document.page_count if self.document else 0
        has_pages = has_document and page_count > 0
        self.add_page_action.setEnabled(has_document)
        can_modify = has_pages and self.current_page_index is not None
        self.remove_page_action.setEnabled(can_modify and page_count > 1)
        self.move_page_up_action.setEnabled(can_modify and self.current_page_index not in (None, 0))
        self.move_page_down_action.setEnabled(
            can_modify and self.current_page_index is not None and self.current_page_index < page_count - 1
        )
        self.toggle_grid_action.setEnabled(has_document)
