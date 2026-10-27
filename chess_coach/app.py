"""Application entry point."""

from __future__ import annotations

import sys


def main() -> int:
    from PySide6.QtWidgets import QApplication

    from .config import APP_NAME, Settings
    from .gui.fairplay import CONTEXT_ANALYSIS, FairPlayDialog
    from .gui.main_window import MainWindow
    from .gui.styles import DARK_QSS

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_QSS)

    settings = Settings.load()
    preselect = settings.extra.get("context", CONTEXT_ANALYSIS)
    dlg = FairPlayDialog(preselect=preselect, acknowledged=settings.fair_play_acknowledged)
    if not dlg.exec():
        return 0
    settings.fair_play_acknowledged = True
    settings.extra["context"] = dlg.context
    settings.save()

    window = MainWindow(settings, dlg.context)
    window.show()
    return app.exec()
