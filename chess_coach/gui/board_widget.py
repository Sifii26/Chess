"""Interactive chessboard widget with arrows, highlights and an edit mode."""

from __future__ import annotations

import math
from dataclasses import dataclass

import chess
import chess.svg
from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPolygonF
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QInputDialog, QSizePolicy, QWidget

LIGHT = QColor("#ebecd0")
DARK = QColor("#739552")
FROM_HL = QColor(255, 214, 10, 150)
TO_HL = QColor(46, 204, 113, 150)
SELECT_HL = QColor(66, 165, 245, 140)
LEGAL_DOT = QColor(0, 0, 0, 60)
WARN_HL = QColor(231, 76, 60, 120)


@dataclass
class Arrow:
    start: chess.Square
    end: chess.Square
    color: QColor
    width: float = 0.22  # fraction of a square


_renderers: dict[str, QSvgRenderer] = {}


def piece_renderer(piece: chess.Piece) -> QSvgRenderer:
    key = piece.symbol()
    if key not in _renderers:
        _renderers[key] = QSvgRenderer(QByteArray(chess.svg.piece(piece).encode()))
    return _renderers[key]


def draw_arrow(p: QPainter, a: QPointF, b: QPointF, color: QColor, width: float) -> None:
    """Draw a filled arrow from a to b (``width`` in pixels)."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    head_len = min(width * 2.4, length * 0.6)
    head_w = width * 1.9
    shaft_end = QPointF(b.x() - ux * head_len, b.y() - uy * head_len)
    w2 = width / 2
    poly = QPolygonF([
        QPointF(a.x() + nx * w2, a.y() + ny * w2),
        QPointF(shaft_end.x() + nx * w2, shaft_end.y() + ny * w2),
        QPointF(shaft_end.x() + nx * head_w / 2, shaft_end.y() + ny * head_w / 2),
        b,
        QPointF(shaft_end.x() - nx * head_w / 2, shaft_end.y() - ny * head_w / 2),
        QPointF(shaft_end.x() - nx * w2, shaft_end.y() - ny * w2),
        QPointF(a.x() - nx * w2, a.y() - ny * w2),
    ])
    path = QPainterPath()
    path.addPolygon(poly)
    path.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawPath(path)


class BoardWidget(QWidget):
    moveMade = Signal(object)        # chess.Move
    positionEdited = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.board = chess.Board()
        self.flipped = False
        self.arrows: list[Arrow] = []
        self.highlights: dict[chess.Square, QColor] = {}
        self.warn_squares: set[chess.Square] = set()
        self.edit_mode = False
        self.edit_piece: chess.Piece | None = chess.Piece(chess.PAWN, chess.WHITE)
        self.interactive = True
        self._selected: chess.Square | None = None
        self._drag_from: chess.Square | None = None
        self._drag_pos: QPointF | None = None
        self.setMinimumSize(320, 320)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    # ------------------------------------------------------------ geometry
    def _geom(self) -> tuple[float, float, float]:
        size = min(self.width(), self.height()) - 4
        sq = size / 8
        x0 = (self.width() - size) / 2
        y0 = (self.height() - size) / 2
        return x0, y0, sq

    def heightForWidth(self, w: int) -> int:
        return w

    def hasHeightForWidth(self) -> bool:
        return True

    def square_rect(self, square: chess.Square) -> QRectF:
        x0, y0, s = self._geom()
        f, r = chess.square_file(square), chess.square_rank(square)
        col, row = (7 - f, r) if self.flipped else (f, 7 - r)
        return QRectF(x0 + col * s, y0 + row * s, s, s)

    def square_at(self, pos: QPointF) -> chess.Square | None:
        x0, y0, s = self._geom()
        col, row = int((pos.x() - x0) // s), int((pos.y() - y0) // s)
        if not (0 <= col < 8 and 0 <= row < 8):
            return None
        return chess.square(7 - col, row) if self.flipped else chess.square(col, 7 - row)

    # ------------------------------------------------------------ API
    def set_board(self, board: chess.Board) -> None:
        self.board = board
        self._selected = None
        self.update()

    def set_annotations(self, arrows: list[Arrow], highlights: dict[chess.Square, QColor]) -> None:
        self.arrows = arrows
        self.highlights = highlights
        self.update()

    def clear_annotations(self) -> None:
        self.set_annotations([], {})

    # ------------------------------------------------------------ painting
    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        x0, y0, s = self._geom()
        font = QFont()
        font.setPixelSize(max(9, int(s * 0.16)))
        font.setBold(True)
        p.setFont(font)
        last = self.board.peek() if self.board.move_stack else None
        for square in chess.SQUARES:
            rect = self.square_rect(square)
            light = (chess.square_file(square) + chess.square_rank(square)) % 2 == 1
            p.fillRect(rect, LIGHT if light else DARK)
            if last and square in (last.from_square, last.to_square):
                p.fillRect(rect, QColor(255, 255, 80, 70))
            if square in self.highlights:
                p.fillRect(rect, self.highlights[square])
            if square in self.warn_squares:
                p.fillRect(rect, WARN_HL)
            if square == self._selected:
                p.fillRect(rect, SELECT_HL)
            # coordinates on the edge squares
            p.setPen(DARK if light else LIGHT)
            f, r = chess.square_file(square), chess.square_rank(square)
            if (r == 0 and not self.flipped) or (r == 7 and self.flipped):
                p.drawText(rect.adjusted(0, 0, -3, -1), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
                           chess.FILE_NAMES[f])
            if (f == 0 and not self.flipped) or (f == 7 and self.flipped):
                p.drawText(rect.adjusted(3, 1, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                           chess.RANK_NAMES[r])

        king_in_check = self.board.king(self.board.turn) if self.board.is_check() else None
        for square, piece in self.board.piece_map().items():
            rect = self.square_rect(square)
            if square == king_in_check:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(231, 76, 60, 170))
                p.drawEllipse(rect.adjusted(s * .05, s * .05, -s * .05, -s * .05))
            if square == self._drag_from and self._drag_pos is not None:
                continue
            piece_renderer(piece).render(p, rect)

        # legal move hints for the selected piece
        if self._selected is not None and not self.edit_mode:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(LEGAL_DOT)
            for mv in self.board.legal_moves:
                if mv.from_square == self._selected:
                    c = self.square_rect(mv.to_square).center()
                    p.drawEllipse(c, s * 0.15, s * 0.15)

        for arrow in self.arrows:
            a = self.square_rect(arrow.start).center()
            b = self.square_rect(arrow.end).center()
            draw_arrow(p, a, b, arrow.color, s * arrow.width)

        if self._drag_from is not None and self._drag_pos is not None:
            piece = self.board.piece_at(self._drag_from)
            if piece:
                r = QRectF(self._drag_pos.x() - s / 2, self._drag_pos.y() - s / 2, s, s)
                piece_renderer(piece).render(p, r)
        p.end()

    # ------------------------------------------------------------ mouse
    def mousePressEvent(self, e) -> None:
        if not self.interactive:
            return
        square = self.square_at(e.position())
        if square is None:
            return
        if self.edit_mode:
            if e.button() == Qt.MouseButton.RightButton or self.edit_piece is None:
                self.board.remove_piece_at(square)
            else:
                current = self.board.piece_at(square)
                self.board.set_piece_at(square, None if current == self.edit_piece else self.edit_piece)
            self.warn_squares.discard(square)
            self.positionEdited.emit()
            self.update()
            return
        if e.button() != Qt.MouseButton.LeftButton:
            self._selected = None
            self.update()
            return
        if self._selected is not None and self._try_move(self._selected, square):
            return
        piece = self.board.piece_at(square)
        if piece and piece.color == self.board.turn:
            self._selected = square
            self._drag_from = square
            self._drag_pos = e.position()
        else:
            self._selected = None
        self.update()

    def mouseMoveEvent(self, e) -> None:
        if self._drag_from is not None and e.buttons() & Qt.MouseButton.LeftButton:
            self._drag_pos = e.position()
            self.update()

    def mouseReleaseEvent(self, e) -> None:
        if self._drag_from is None:
            return
        start = self._drag_from
        self._drag_from = None
        self._drag_pos = None
        target = self.square_at(e.position())
        if target is not None and target != start:
            self._try_move(start, target)
        self.update()

    def _try_move(self, start: chess.Square, target: chess.Square) -> bool:
        move = chess.Move(start, target)
        piece = self.board.piece_at(start)
        if piece and piece.piece_type == chess.PAWN and chess.square_rank(target) in (0, 7):
            choices = ["Queen", "Rook", "Bishop", "Knight"]
            if chess.Move(start, target, chess.QUEEN) not in self.board.legal_moves:
                return False
            choice, ok = QInputDialog.getItem(self, "Promotion", "Promote to:", choices, 0, False)
            if not ok:
                return False
            move = chess.Move(start, target, {"Queen": chess.QUEEN, "Rook": chess.ROOK,
                                              "Bishop": chess.BISHOP, "Knight": chess.KNIGHT}[choice])
        if move in self.board.legal_moves:
            self._selected = None
            self.moveMade.emit(move)
            return True
        return False
