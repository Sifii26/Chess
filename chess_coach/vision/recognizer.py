"""Screenshot -> chess.Board, including orientation and side to move."""

from __future__ import annotations

from dataclasses import dataclass, field

import chess
import cv2
import numpy as np

from .board_detector import BoardNotFoundError, BoardRegion, detect_board
from .pieces import CellReading, has_calibration, read_cells


@dataclass
class Detection:
    board: chess.Board
    white_bottom: bool               # True if White is at the bottom (you play White)
    region: BoardRegion
    readings: list[list[CellReading]]
    warnings: list[str] = field(default_factory=list)
    low_confidence: list[chess.Square] = field(default_factory=list)
    turn_guessed: bool = True        # side to move was assumed, not inferred
    calibrated: bool = False

    @property
    def player_color(self) -> chess.Color:
        return chess.WHITE if self.white_bottom else chess.BLACK


def load_image(path: str) -> np.ndarray:
    data = np.fromfile(path, dtype=np.uint8)  # handles non-ASCII paths on Windows
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise BoardNotFoundError(f"Could not open image: {path}")
    return img


def screen_to_square(r: int, c: int, white_bottom: bool) -> chess.Square:
    return chess.square(c, 7 - r) if white_bottom else chess.square(7 - c, r)


def _orientation(readings: list[list[CellReading]]) -> bool:
    """Return True when White pieces sit at the bottom of the screen."""
    wk = bk = None
    w_rows, b_rows = [], []
    for r in range(8):
        for c in range(8):
            p = readings[r][c].piece
            if p is None:
                continue
            (w_rows if p.color == chess.WHITE else b_rows).append(r)
            if p.piece_type == chess.KING:
                if p.color == chess.WHITE:
                    wk = r
                else:
                    bk = r
    # Pawns are the most reliable: they march toward the opponent.
    if w_rows and b_rows:
        return float(np.mean(w_rows)) >= float(np.mean(b_rows))
    if wk is not None and bk is not None:
        return wk >= bk
    return True


def recognize(img: np.ndarray, white_bottom: bool | None = None,
              turn: chess.Color | None = None) -> Detection:
    """Detect the board and pieces in a BGR screenshot.

    ``white_bottom`` / ``turn`` override auto-detection when given.
    """
    region = detect_board(img)
    crop = region.crop(img)
    readings = read_cells(crop)
    if white_bottom is None:
        white_bottom = _orientation(readings)

    board = chess.Board(None)
    low_conf = []
    for r in range(8):
        for c in range(8):
            cell = readings[r][c]
            if cell.piece is None:
                continue
            sq = screen_to_square(r, c, white_bottom)
            board.set_piece_at(sq, cell.piece)
            if cell.confidence < 0.35:
                low_conf.append(sq)

    warnings: list[str] = []
    turn_guessed = True
    if turn is None:
        turn, turn_guessed = _infer_turn(board, readings, white_bottom)
    board.turn = turn
    _fix_rank_pawns(board, warnings)
    board.castling_rights = _infer_castling(board)
    warnings += validate(board)
    if low_conf:
        warnings.append("Unsure about: " + ", ".join(chess.square_name(s).upper() for s in low_conf[:8])
                        + ". Please double-check these squares.")
    if turn_guessed:
        warnings.append(f"Side to move couldn't be detected; assuming {'White' if turn else 'Black'} "
                        "to move. Use the 'Side to move' switch if that's wrong.")
    return Detection(board, white_bottom, region, readings, warnings, low_conf, turn_guessed,
                     calibrated=has_calibration())


def _infer_turn(board: chess.Board, readings, white_bottom: bool) -> tuple[chess.Color, bool]:
    """Use Chess.com's last-move highlight: the piece on a highlighted square just moved."""
    highlighted = [(r, c) for r in range(8) for c in range(8) if readings[r][c].highlighted]
    if 1 <= len(highlighted) <= 3:
        movers = [readings[r][c].piece for r, c in highlighted if readings[r][c].piece is not None]
        if len(movers) == 1:
            return (not movers[0].color), False
    # Fallbacks: whoever is in check must be the side to move.
    for color in (chess.WHITE, chess.BLACK):
        king = board.king(color)
        if king is not None and board.is_attacked_by(not color, king):
            return color, False
    return (chess.WHITE if white_bottom else chess.BLACK), True


def _fix_rank_pawns(board: chess.Board, warnings: list[str]) -> None:
    for sq in list(board.pieces(chess.PAWN, chess.WHITE) | board.pieces(chess.PAWN, chess.BLACK)):
        if chess.square_rank(sq) in (0, 7):
            color = board.piece_at(sq).color
            board.set_piece_at(sq, chess.Piece(chess.BISHOP, color))
            warnings.append(f"A pawn was read on {chess.square_name(sq).upper()} (impossible) — "
                            "changed to a bishop; please verify.")


def _infer_castling(board: chess.Board) -> int:
    rights = 0
    for color, rank in ((chess.WHITE, 0), (chess.BLACK, 7)):
        if board.piece_at(chess.square(4, rank)) == chess.Piece(chess.KING, color):
            if board.piece_at(chess.square(7, rank)) == chess.Piece(chess.ROOK, color):
                rights |= chess.BB_SQUARES[chess.square(7, rank)]
            if board.piece_at(chess.square(0, rank)) == chess.Piece(chess.ROOK, color):
                rights |= chess.BB_SQUARES[chess.square(0, rank)]
    return rights


def validate(board: chess.Board) -> list[str]:
    """Human-readable problems that would make the position illegal."""
    problems = []
    for color in (chess.WHITE, chess.BLACK):
        name = "White" if color else "Black"
        kings = len(board.pieces(chess.KING, color))
        if kings != 1:
            problems.append(f"{name} has {kings} kings (needs exactly 1).")
        if len(board.pieces(chess.PAWN, color)) > 8:
            problems.append(f"{name} has more than 8 pawns.")
        if bin(board.occupied_co[color]).count("1") > 16:
            problems.append(f"{name} has more than 16 pieces.")
    if not problems:
        status = board.status()
        if status & chess.STATUS_OPPOSITE_CHECK:
            problems.append("The side NOT to move is in check — flip the side to move.")
        elif status & ~chess.STATUS_VALID and status & (chess.STATUS_TOO_MANY_CHECKERS |
                                                          chess.STATUS_IMPOSSIBLE_CHECK):
            problems.append("The check situation is impossible — some pieces are probably misread.")
    return problems
