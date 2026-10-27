import chess
import pytest

from chess_coach.engine import Engine, find_stockfish
from chess_coach.explain import describe_move, detect_motifs, explain_sequence

needs_engine = pytest.mark.skipif(find_stockfish() is None, reason="Stockfish not installed")


def test_describe_move():
    b = chess.Board()
    assert describe_move(b, chess.Move.from_uci("g1f3")) == "Move your knight from G1 to F3."


def test_describe_castling():
    b = chess.Board("4k3/8/8/8/8/8/8/R3K2R w KQ - 0 1")
    assert describe_move(b, b.parse_san("O-O")).startswith("Castle kingside: move your king from E1 to G1")


@pytest.mark.parametrize("fen,san,motif", [
    ("r3k3/8/8/3N4/8/8/8/4K3 w - - 0 1", "Nc7+", "Fork"),
    ("4k3/8/2n5/8/8/8/8/4KB2 w - - 0 1", "Bb5", "Pin"),
    ("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 4", "Qxf7#", "Checkmate"),
])
def test_motifs(fen, san, motif):
    b = chess.Board(fen)
    motifs, reasons = detect_motifs(b, b.parse_san(san))
    assert motif in motifs and reasons


@needs_engine
def test_finds_mate_in_two():
    e = Engine()
    try:
        b = chess.Board("r1b2k1r/ppp1bppp/8/1B1Q4/5q2/2P5/PPP2PPP/R3R1K1 w - - 1 1")
        r = e.analyse(b, depth=14, mate_search=True, mate_depth=10)
        assert r.best.mate == 2
        assert b.san(r.best.move) == "Qd8+"
        steps = explain_sequence(b, r.best.moves[:3], chess.WHITE)
        assert steps[-1].purpose.startswith("Checkmate")
        assert len(r.lines) == 3
    finally:
        e.stop()
