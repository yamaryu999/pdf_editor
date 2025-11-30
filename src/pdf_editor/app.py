from __future__ import annotations

import sys

from PySide6 import QtGui, QtWidgets

from .widgets.main_window import MainWindow


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)

    # Use Fusion as a base style for consistency across platforms.
    app.setStyle("Fusion")
    app.setFont(QtGui.QFont("Noto Sans", 10))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
