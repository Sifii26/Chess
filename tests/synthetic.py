"""Render synthetic 'screenshots' of a board for testing the vision pipeline."""

import chess
import chess.svg
import numpy as np
from PySide6.QtCore import QByteArray
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def render(board: chess.Board, size=480, flipped=False, lastmove=None, canvas=(1280, 800), at=(300, 150)):
    svg = chess.svg.board(board, size=size, flipped=flipped, coordinates=False, lastmove=lastmove,
                          colors={"square light": "#ebecd0", "square dark": "#739552",
                                  "square light lastmove": "#f5f682", "square dark lastmove": "#b9ca43"})
    img = QImage(canvas[0], canvas[1], QImage.Format.Format_RGB888)
    img.fill(QColor(48, 46, 43))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    from PySide6.QtCore import QRectF
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(at[0], at[1], size, size))
    p.end()
    arr = np.frombuffer(img.constBits(), np.uint8).reshape(canvas[1], img.bytesPerLine())[:, :canvas[0] * 3]
    return np.ascontiguousarray(arr.reshape(canvas[1], canvas[0], 3)[:, :, ::-1])
