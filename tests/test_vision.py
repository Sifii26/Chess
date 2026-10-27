import chess
import numpy as np
import pytest

pytest.importorskip("PySide6.QtSvg")

from synthetic import render  # noqa: E402

from chess_coach.vision import BoardNotFoundError, recognize  # noqa: E402
from chess_coach.vision import pieces  # noqa: E402

POSITIONS = [
    "r1bqkb1r/1ppp1ppp/p1n2n2/4p3/B3P3/5N2/PPPP1PPP/RNBQ1RK1 b kq - 3 5",
    "r1b2k1r/ppp1bppp/8/1B1Q4/5q2/2P5/PPP2PPP/R3R1K1 w - - 1 1",
    "8/5pk1/6p1/8/3Q4/6P1/5PKP/2q5 w - - 0 40",
]


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(pieces, "CALIBRATION_FILE", tmp_path / "calibrated.npz")
    monkeypatch.setattr(pieces, "TEMPLATE_DIR", tmp_path)


@pytest.mark.parametrize("fen", POSITIONS)
@pytest.mark.parametrize("flipped", [False, True])
def test_recognize_positions(fen, flipped):
    board = chess.Board(fen)
    img = render(board, flipped=flipped)
    det = recognize(img)
    assert det.board.board_fen() == board.board_fen()
    assert det.white_bottom == (not flipped)


def test_turn_from_last_move_highlight():
    board = chess.Board()
    board.push_san("e4")
    det = recognize(render(board, lastmove=board.peek()))
    assert det.board.turn == chess.BLACK
    assert not det.turn_guessed


def test_scaled_board_and_calibration():
    start = chess.Board()
    calib_img = render(start, size=360, canvas=(900, 600), at=(120, 90))
    from chess_coach.vision import detect_board
    region = detect_board(calib_img)
    assert pieces.calibrate(region.crop(calib_img)) == 32
    board = chess.Board(POSITIONS[0])
    det = recognize(render(board, size=360, canvas=(900, 600), at=(400, 200)))
    assert det.calibrated
    assert det.board.board_fen() == board.board_fen()


def test_no_board_raises():
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (400, 600, 3), dtype=np.uint8)
    with pytest.raises(BoardNotFoundError):
        recognize(noise)
