from __future__ import annotations

import sys

from PySide6 import QtWidgets

from .widgets.main_window import MainWindow


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)

    # Use Fusion as a base style for consistency across platforms.
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
