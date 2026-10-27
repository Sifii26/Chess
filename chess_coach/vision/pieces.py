"""Recognise the piece (if any) on each of the 64 cells of a board crop.

Each occupied cell is reduced to a silhouette (pixels that differ from the
square's background colour). The piece *colour* comes from the brightness of
the silhouette's interior; the piece *type* from comparing the silhouette
shape with templates. Two template sets exist:

* built-in: rendered from python-chess's SVG pieces (works with most sets);
* calibrated: learned from a screenshot of the starting position in the
  user's own Chess.com piece set (much more accurate — see ``calibrate``).
"""

from __future__ import annotations

from dataclasses import dataclass

import chess
import cv2
import numpy as np

from ..config import TEMPLATE_DIR
from .board_detector import square_class_colors

CELL = 64
SHAPE = 48
TYPES = [chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN, chess.KING]
CALIBRATION_FILE = TEMPLATE_DIR / "calibrated.npz"


@dataclass
class CellReading:
    piece: chess.Piece | None
    confidence: float          # 0..1
    occupancy: float           # fraction of foreground pixels in the cell centre
    highlighted: bool = False  # square tinted as part of the last move


@dataclass
class Template:
    piece_type: int
    shape: np.ndarray   # SHAPE x SHAPE float mask, bbox-normalised
    height: float       # bbox height / cell size
    width: float


def _silhouette(cell_bgr: np.ndarray, bg_lab: np.ndarray, square_lab: tuple[np.ndarray, np.ndarray]) -> np.ndarray:
    """Binary mask of the piece on a CELL x CELL cell image."""
    lab = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2LAB).astype(np.float32)
    diff = np.linalg.norm(lab - bg_lab, axis=2)
    # Also discard pixels that match either board colour (e.g. highlights, coordinates).
    d_light = np.linalg.norm(lab - square_lab[0], axis=2)
    d_dark = np.linalg.norm(lab - square_lab[1], axis=2)
    mask = ((diff > 22) & (d_light > 14) & (d_dark > 14)).astype(np.uint8)
    # Remove coordinate labels drawn in the cell corners on edge squares.
    m = CELL // 7
    mask[:m, :m] = mask[:m, -m:] = mask[-m:, :m] = mask[-m:, -m:] = 0
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask)
    if n <= 1:
        return np.zeros_like(mask)
    keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    mask = (labels == keep).astype(np.uint8)
    # Fill interior holes so outline-only and filled sets look alike.
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    filled = np.zeros_like(mask)
    cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
    return filled


def _shape_features(mask: np.ndarray) -> tuple[np.ndarray, float, float] | None:
    ys, xs = np.nonzero(mask)
    if len(xs) < 20:
        return None
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    crop = mask[y0:y1, x0:x1].astype(np.float32)
    h, w = crop.shape
    s = max(h, w)
    pad = np.zeros((s, s), np.float32)
    pad[(s - h) // 2:(s - h) // 2 + h, (s - w) // 2:(s - w) // 2 + w] = crop
    shape = cv2.resize(pad, (SHAPE, SHAPE), interpolation=cv2.INTER_AREA)
    return shape, h / mask.shape[0], w / mask.shape[1]


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    inter = np.minimum(a, b).sum()
    union = np.maximum(a, b).sum()
    return float(inter / union) if union else 0.0


# ---------------------------------------------------------------- templates

def _render_builtin_templates() -> list[Template]:
    """Render python-chess's SVG pieces with Qt and extract silhouettes."""
    import chess.svg
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QColor, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    out = []
    for color in (chess.WHITE, chess.BLACK):
        for pt in TYPES:
            svg = chess.svg.piece(chess.Piece(pt, color), size=CELL)
            img = QImage(CELL, CELL, QImage.Format.Format_RGB888)
            img.fill(QColor(0, 200, 0))
            painter = QPainter(img)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            QSvgRenderer(QByteArray(svg.encode())).render(painter)
            painter.end()
            ptr = img.constBits()
            arr = np.frombuffer(ptr, np.uint8).reshape(CELL, img.bytesPerLine())[:, :CELL * 3]
            rgb = arr.reshape(CELL, CELL, 3)
            mask = ~((rgb[..., 0] < 30) & (rgb[..., 1] > 170) & (rgb[..., 2] < 30))
            mask = mask.astype(np.uint8)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            filled = np.zeros_like(mask)
            cv2.drawContours(filled, contours, -1, 1, thickness=cv2.FILLED)
            feats = _shape_features(filled)
            if feats:
                out.append(Template(pt, *feats))
    _ = Qt  # keep import for clarity of Qt dependency
    return out


_builtin_cache: list[Template] | None = None


def builtin_templates() -> list[Template]:
    global _builtin_cache
    if _builtin_cache is None:
        _builtin_cache = _render_builtin_templates()
    return _builtin_cache


def load_calibrated_templates() -> list[Template] | None:
    try:
        data = np.load(CALIBRATION_FILE)
    except (OSError, ValueError):
        return None
    return [Template(int(t), s, float(h), float(w))
            for t, s, h, w in zip(data["types"], data["shapes"], data["heights"], data["widths"])]


def has_calibration() -> bool:
    return CALIBRATION_FILE.is_file()


def clear_calibration() -> None:
    try:
        CALIBRATION_FILE.unlink()
    except OSError:
        pass


# ---------------------------------------------------------------- reading

def _cells(board_img: np.ndarray) -> np.ndarray:
    norm = cv2.resize(board_img, (CELL * 8, CELL * 8), interpolation=cv2.INTER_AREA)
    return norm.reshape(8, CELL, 8, CELL, 3).transpose(0, 2, 1, 3, 4)


def read_cells(board_img: np.ndarray, templates: list[Template] | None = None) -> list[list[CellReading]]:
    """Classify all 64 cells. Index as [row][col] in *screen* orientation."""
    light, dark, corner_colors = square_class_colors(board_img)
    cal = load_calibrated_templates()
    if templates is None:
        templates = cal or builtin_templates()
    calibrated = templates is cal and cal is not None
    cells = _cells(board_img)
    out: list[list[CellReading]] = []
    for r in range(8):
        row = []
        for c in range(8):
            base = light if (r + c) % 2 == 0 else dark
            bg = corner_colors[r, c]
            highlighted = bool(np.linalg.norm(bg - base) > 12)
            cell = cells[r, c]
            mask = _silhouette(cell, bg, (light, dark))
            inner = mask[CELL // 6: -CELL // 6, CELL // 6: -CELL // 6]
            occ = float(inner.mean())
            if occ < 0.06:
                row.append(CellReading(None, 1.0 - occ * 5, occ, highlighted))
                continue
            row.append(_classify(cell, mask, templates, calibrated, occ, highlighted))
        out.append(row)
    return out


def _piece_color(cell: np.ndarray, mask: np.ndarray) -> tuple[chess.Color, float]:
    eroded = cv2.erode(mask, np.ones((5, 5), np.uint8))
    if eroded.sum() < 15:
        eroded = mask
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    vals = gray[eroded.astype(bool)]
    # White pieces are mostly light inside; black pieces mostly dark.
    bright = float((vals > 150).mean())
    dark = float((vals < 90).mean())
    color = chess.WHITE if bright >= dark else chess.BLACK
    return color, abs(bright - dark)


def _classify(cell, mask, templates, calibrated, occ, highlighted) -> CellReading:
    feats = _shape_features(mask)
    if feats is None:
        return CellReading(None, 0.5, occ, highlighted)
    shape, h, w = feats
    color, color_conf = _piece_color(cell, mask)
    scores: dict[int, float] = {}
    for t in templates:
        s = _iou(shape, t.shape)
        # Relative size matters (pawns are small, kings/queens tall).
        size_weight = 4.0 if calibrated else 1.5
        s -= size_weight * (abs(h - t.height) + 0.5 * abs(w - t.width)) * (0.6 if not calibrated else 1.0)
        scores[t.piece_type] = max(scores.get(t.piece_type, -9.0), s)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_type, best_score = ranked[0]
    margin = best_score - ranked[1][1] if len(ranked) > 1 else 1.0
    conf = float(np.clip(0.5 * best_score + 2.5 * margin, 0, 1)) * (0.6 + 0.4 * min(1.0, color_conf * 2))
    return CellReading(chess.Piece(best_type, color), conf, occ, highlighted)


# ---------------------------------------------------------------- calibration

START_LAYOUT = chess.Board().piece_map()


def calibrate(board_img: np.ndarray, white_bottom: bool = True) -> int:
    """Learn the user's piece set from a screenshot of the starting position.

    Returns the number of samples learned. Raises ValueError if the image does
    not look like the initial position.
    """
    light, dark, corner_colors = square_class_colors(board_img)
    cells = _cells(board_img)
    samples: dict[int, list[tuple[np.ndarray, float, float]]] = {t: [] for t in TYPES}
    for r in range(8):
        for c in range(8):
            square = chess.square(c, 7 - r) if white_bottom else chess.square(7 - c, r)
            expected = START_LAYOUT.get(square)
            mask = _silhouette(cells[r, c], corner_colors[r, c], (light, dark))
            occ = float(mask[CELL // 6:-CELL // 6, CELL // 6:-CELL // 6].mean())
            if expected is None:
                if occ > 0.12:
                    raise ValueError(f"Expected {chess.square_name(square)} to be empty — "
                                     "load a screenshot of the starting position.")
                continue
            feats = _shape_features(mask)
            if feats is None or occ < 0.06:
                raise ValueError(f"No piece found on {chess.square_name(square)} — "
                                 "load a screenshot of the starting position.")
            samples[expected.piece_type].append(feats)
    shapes, types, heights, widths = [], [], [], []
    for t, lst in samples.items():
        for shape, h, w in lst:
            shapes.append(shape)
            types.append(t)
            heights.append(h)
            widths.append(w)
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(CALIBRATION_FILE, shapes=np.array(shapes), types=np.array(types),
                        heights=np.array(heights), widths=np.array(widths))
    return len(types)
