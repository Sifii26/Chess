"""Vertical evaluation bar (White's share grows from the bottom)."""

from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget


class EvalBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(26)
        self.white_share = 0.5
        self.text = "0.0"
        self.flipped = False

    def set_eval(self, cp_white: int | None, mate_white: int | None) -> None:
        if mate_white is not None:
            self.white_share = 1.0 if mate_white > 0 else 0.0
            self.text = f"M{abs(mate_white)}"
        elif cp_white is not None:
            self.white_share = 1 / (1 + math.exp(-cp_white / 250))
            self.text = f"{abs(cp_white) / 100:.1f}"
        else:
            self.white_share, self.text = 0.5, ""
        self.update()

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        h, w = self.height(), self.width()
        white_h = h * self.white_share
        if self.flipped:
            p.fillRect(QRectF(0, 0, w, white_h), QColor("#f0f0f0"))
            p.fillRect(QRectF(0, white_h, w, h - white_h), QColor("#2b2b2b"))
        else:
            p.fillRect(QRectF(0, 0, w, h - white_h), QColor("#2b2b2b"))
            p.fillRect(QRectF(0, h - white_h, w, white_h), QColor("#f0f0f0"))
        f = QFont()
        f.setPixelSize(10)
        f.setBold(True)
        p.setFont(f)
        white_ahead = self.white_share >= 0.5
        at_bottom = white_ahead != self.flipped
        p.setPen(QColor("#2b2b2b") if white_ahead else QColor("#f0f0f0"))
        rect = QRectF(0, h - 22, w, 20) if at_bottom else QRectF(0, 2, w, 20)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text)
        p.end()
