from __future__ import annotations

import os
import sys

from PySide6 import QtWidgets
from qt_material import apply_stylesheet

from .widgets.main_window import MainWindow


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)

    # Use Fusion as a base style for consistency across platforms.
    app.setStyle("Fusion")

    # Apply a Material Design theme. Users can override via environment
    # variable PDF_EDITOR_THEME (e.g. "light_blue.xml").
    theme_name = os.getenv("PDF_EDITOR_THEME", "dark_teal.xml")
    apply_stylesheet(app, theme=theme_name)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
