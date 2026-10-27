"""Locate an 8x8 chessboard inside a screenshot.

Strategy: gather candidate square regions from several cheap detectors
(edge contours, known Chess.com theme colours, the whole image), then keep
the candidate whose 64 cells best fit an alternating light/dark pattern.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Light/dark square colours (RGB) of common Chess.com board themes.
THEME_COLORS_RGB = [
    ((235, 236, 208), (115, 149, 82)),   # green (current)
    ((238, 238, 210), (118, 150, 86)),   # green (classic)
    ((240, 217, 181), (181, 136, 99)),   # brown
    ((234, 233, 210), (75, 115, 153)),   # blue / icy
    ((222, 227, 230), (140, 162, 173)),  # light blue
    ((237, 214, 176), (184, 135, 98)),   # wood-ish
    ((232, 235, 239), (125, 135, 150)),  # grey
]


class BoardNotFoundError(RuntimeError):
    pass


@dataclass
class BoardRegion:
    x: int
    y: int
    size: int
    score: float

    def crop(self, img: np.ndarray) -> np.ndarray:
        return img[self.y:self.y + self.size, self.x:self.x + self.size]


def _cell_corner_colors(board_img: np.ndarray) -> np.ndarray:
    """Median colour of the four corner patches of each cell -> (8, 8, 3) Lab."""
    norm = cv2.resize(board_img, (480, 480), interpolation=cv2.INTER_AREA)
    lab = cv2.cvtColor(norm, cv2.COLOR_BGR2LAB).astype(np.float32)
    c = 60
    out = np.zeros((8, 8, 3), np.float32)
    for r in range(8):
        for f in range(8):
            y0, x0 = r * c, f * c
            patches = [lab[y0 + 3:y0 + 10, x0 + 3:x0 + 10], lab[y0 + 3:y0 + 10, x0 + c - 10:x0 + c - 3],
                       lab[y0 + c - 10:y0 + c - 3, x0 + 3:x0 + 10], lab[y0 + c - 10:y0 + c - 3, x0 + c - 10:x0 + c - 3]]
            meds = np.array([np.median(p.reshape(-1, 3), axis=0) for p in patches])
            out[r, f] = np.median(meds, axis=0)
    return out


def checker_score(board_img: np.ndarray) -> float:
    """How strongly a square crop looks like a chessboard (higher is better)."""
    if board_img.size == 0 or min(board_img.shape[:2]) < 64:
        return 0.0
    colors = _cell_corner_colors(board_img)
    parity = (np.add.outer(np.arange(8), np.arange(8)) % 2).astype(bool)
    a, b = colors[~parity], colors[parity]
    ma, mb = np.median(a, axis=0), np.median(b, axis=0)
    sep = float(np.linalg.norm(ma - mb))
    if sep < 12:
        return 0.0
    # Fraction of cells that sit closer to their own class colour (robust to highlights).
    da = np.linalg.norm(a - ma, axis=1) < np.linalg.norm(a - mb, axis=1)
    db = np.linalg.norm(b - mb, axis=1) < np.linalg.norm(b - ma, axis=1)
    consistency = (da.sum() + db.sum()) / 64.0
    spread = (np.median(np.linalg.norm(a - ma, axis=1)) + np.median(np.linalg.norm(b - mb, axis=1))) / 2
    return consistency ** 4 * sep / (spread + 4.0)


def _square_candidates_from_contours(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 30, 90)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    min_side = 0.15 * min(h, w)
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw < min_side or ch < min_side:
            continue
        if abs(cw - ch) > 0.06 * max(cw, ch):
            continue
        out.append((x, y, cw, ch))
    return out


def _square_candidates_from_theme_colors(img: np.ndarray) -> list[tuple[int, int, int, int]]:
    out = []
    for light, dark in THEME_COLORS_RGB:
        mask = np.zeros(img.shape[:2], np.uint8)
        for rgb in (light, dark):
            bgr = np.array(rgb[::-1], np.int16)
            diff = np.abs(img.astype(np.int16) - bgr).sum(axis=2)
            mask |= (diff < 30).astype(np.uint8)
        if mask.mean() < 0.02:
            continue
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(mask)
        for i in range(1, n):
            x, y, cw, ch, area = stats[i]
            if min(cw, ch) > 64 and abs(cw - ch) < 0.12 * max(cw, ch):
                out.append((x, y, cw, ch))
    return out


def _refine(img: np.ndarray, x: int, y: int, size: int) -> BoardRegion:
    """Nudge position/size by a few pixels to maximise the checker score."""
    best = BoardRegion(x, y, size, checker_score(img[y:y + size, x:x + size]))
    step = max(1, size // 160)
    improved, rounds = True, 0
    while improved and rounds < 60:
        improved, rounds = False, rounds + 1
        for dx, dy, ds in ((step, 0, 0), (-step, 0, 0), (0, step, 0), (0, -step, 0),
                           (0, 0, step), (0, 0, -step), (step, step, -2 * step), (-step, -step, 2 * step)):
            nx, ny, ns = best.x + dx, best.y + dy, best.size + ds
            if nx < 0 or ny < 0 or ns < 64 or ny + ns > img.shape[0] or nx + ns > img.shape[1]:
                continue
            s = checker_score(img[ny:ny + ns, nx:nx + ns])
            if s > best.score * 1.001:
                best = BoardRegion(nx, ny, ns, s)
                improved = True
    return best


def detect_board(img: np.ndarray, min_score: float = 1.5) -> BoardRegion:
    """Find the chessboard in a BGR image. Raises BoardNotFoundError."""
    if img is None or img.size == 0:
        raise BoardNotFoundError("The image is empty or could not be read.")
    h, w = img.shape[:2]
    cands = _square_candidates_from_contours(img) + _square_candidates_from_theme_colors(img)
    side = min(h, w)
    cands.append(((w - side) // 2, (h - side) // 2, side, side))  # already-cropped board

    scored: list[BoardRegion] = []
    seen = set()
    for x, y, cw, ch in cands:
        size = int(min(cw, ch))
        key = (x // 4, y // 4, size // 4)
        if key in seen:
            continue
        seen.add(key)
        crop = img[y:y + size, x:x + size]
        scored.append(BoardRegion(int(x), int(y), size, checker_score(crop)))
    if not scored:
        raise BoardNotFoundError("No chessboard-shaped region found in the image.")
    # Prefer high score; among near-ties prefer the larger region (whole board vs. sub-grid).
    scored.sort(key=lambda r: r.score, reverse=True)
    top = scored[0].score
    shortlist = [r for r in scored[:12] if r.score >= 0.8 * top]
    best = max(shortlist, key=lambda r: r.size)
    best = _refine(img, best.x, best.y, best.size)
    if best.score < min_score:
        raise BoardNotFoundError(
            "Could not find a chessboard in the image (best match score "
            f"{best.score:.2f}). Try a tighter screenshot of just the board."
        )
    return best


def square_class_colors(board_img: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (light Lab, dark Lab, per-cell corner Lab colours)."""
    colors = _cell_corner_colors(board_img)
    parity = (np.add.outer(np.arange(8), np.arange(8)) % 2).astype(bool)
    return np.median(colors[~parity], axis=0), np.median(colors[parity], axis=0), colors
