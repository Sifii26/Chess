"""Optional transparent always-on-top window that draws the recommended move.

It only paints an arrow; it never clicks, types or otherwise interacts with
the page underneath. It is updated only when *you* analyse a position in the
app — it does not watch the screen.

Usage: unlock it, drag/resize it so it covers the board, then lock it
(locked = mouse clicks pass through to the window below).
"""

from __future__ import annotations

import chess
from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from .board_widget import draw_arrow


class OverlayWindow(QWidget):
    def __init__(self):
        super().__init__(None)
        self.setWindowTitle("Chess Coach Overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.flipped = False
        self.move_: chess.Move | None = None
        self.label = ""
        self.locked = False
        self._drag_offset: QPoint | None = None
        self._resizing = False
        self._apply_flags()
        self.resize(480, 480)

    def _apply_flags(self) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        if self.locked:
            flags |= Qt.WindowType.WindowTransparentForInput
        visible = self.isVisible()
        self.setWindowFlags(flags)
        if visible:
            self.show()

    def set_locked(self, locked: bool) -> None:
        self.locked = locked
        self._apply_flags()
        self.update()

    def set_move(self, move: chess.Move | None, flipped: bool, label: str = "") -> None:
        self.move_ = move
        self.flipped = flipped
        self.label = label
        self.update()

    def align_to(self, rect: QRect) -> None:
        """Place the overlay exactly over a board region (logical screen coords)."""
        self.setGeometry(rect)

    def _center(self, square: chess.Square) -> tuple[float, float]:
        s = min(self.width(), self.height()) / 8
        f, r = chess.square_file(square), chess.square_rank(square)
        col, row = (7 - f, r) if self.flipped else (f, 7 - r)
        return (col + 0.5) * s, (row + 0.5) * s

    def paintEvent(self, _e) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        size = min(self.width(), self.height())
        s = size / 8
        if not self.locked:
            # Visible frame + grid while positioning.
            p.fillRect(self.rect(), QColor(20, 20, 30, 60))
            p.setPen(QPen(QColor(0, 200, 255, 200), 2))
            p.drawRect(QRectF(1, 1, size - 2, size - 2))
            p.setPen(QPen(QColor(0, 200, 255, 90), 1))
            for i in range(1, 8):
                p.drawLine(int(i * s), 0, int(i * s), size)
                p.drawLine(0, int(i * s), size, int(i * s))
            p.setPen(QColor("white"))
            f = QFont()
            f.setPointSize(10)
            p.setFont(f)
            p.drawText(QRectF(6, 6, size - 12, 40), Qt.AlignmentFlag.AlignLeft,
                       "Drag to move · drag bottom-right corner to resize · lock in the app")
            p.fillRect(QRectF(size - 18, size - 18, 16, 16), QColor(0, 200, 255, 200))
        if self.move_ is not None:
            ax, ay = self._center(self.move_.from_square)
            bx, by = self._center(self.move_.to_square)
            for sqr, col in ((self.move_.from_square, QColor(255, 214, 10, 110)),
                             (self.move_.to_square, QColor(46, 204, 113, 110))):
                cx, cy = self._center(sqr)
                p.fillRect(QRectF(cx - s / 2, cy - s / 2, s, s), col)
            draw_arrow(p, QPointF(ax, ay), QPointF(bx, by), QColor(46, 204, 113, 200), s * 0.22)
            if self.label:
                f = QFont()
                f.setPointSize(12)
                f.setBold(True)
                p.setFont(f)
                p.fillRect(QRectF(0, size - 26, size, 26), QColor(0, 0, 0, 140))
                p.setPen(QColor("white"))
                p.drawText(QRectF(8, size - 26, size - 16, 26), Qt.AlignmentFlag.AlignVCenter, self.label)
        p.end()

    # Move / resize while unlocked.
    def mousePressEvent(self, e) -> None:
        if self.locked:
            return
        pos = e.position().toPoint()
        size = min(self.width(), self.height())
        self._resizing = pos.x() > size - 24 and pos.y() > size - 24
        self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e) -> None:
        if self.locked or self._drag_offset is None:
            return
        if self._resizing:
            pos = e.position().toPoint()
            side = max(120, max(pos.x(), pos.y()))
            self.resize(side, side)
        else:
            self.move(e.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, _e) -> None:
        self._drag_offset = None
        self._resizing = False
