"""Turn engine output into plain-language coaching.

Tactical motifs (forks, pins, sacrifices, ...) are detected directly with
python-chess so explanations don't depend on any extra engine features.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import chess
import chess.engine

from .engine import AnalysisResult, Line

PIECE_NAMES = {
    chess.PAWN: "pawn", chess.KNIGHT: "knight", chess.BISHOP: "bishop",
    chess.ROOK: "rook", chess.QUEEN: "queen", chess.KING: "king",
}
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 100}


def sq(square: chess.Square) -> str:
    return chess.square_name(square).upper()


def color_name(color: chess.Color) -> str:
    return "White" if color == chess.WHITE else "Black"


@dataclass
class MoveInsight:
    move: chess.Move
    san: str
    piece: str
    from_sq: str
    to_sq: str
    instruction: str           # "Move your knight from G1 to F3."
    motifs: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


def describe_move(board: chess.Board, move: chess.Move, you: bool = True) -> str:
    """'Move your knight from G1 to F3.' style sentence."""
    piece = board.piece_at(move.from_square)
    name = PIECE_NAMES[piece.piece_type] if piece else "piece"
    owner = "your" if you else "their"
    if board.is_castling(move):
        side = "kingside" if chess.square_file(move.to_square) > chess.square_file(move.from_square) else "queenside"
        rook_to = "F" if side == "kingside" else "D"
        return (f"Castle {side}: move {owner} king from {sq(move.from_square)} to "
                f"{sq(_castle_king_target(move))} (the rook goes to {rook_to}{chess.square_rank(move.from_square) + 1}).")
    text = f"Move {owner} {name} from {sq(move.from_square)} to {sq(move.to_square)}"
    if board.is_capture(move):
        victim = board.piece_at(move.to_square)
        vname = PIECE_NAMES[victim.piece_type] if victim else "pawn"  # en passant
        text += f", capturing the {vname}"
    if move.promotion:
        text += f" and promote to a {PIECE_NAMES[move.promotion]}"
    return text + "."


def _castle_king_target(move: chess.Move) -> chess.Square:
    rank = chess.square_rank(move.from_square)
    file = 6 if chess.square_file(move.to_square) > chess.square_file(move.from_square) else 2
    return chess.square(file, rank)


def detect_motifs(board: chess.Board, move: chess.Move) -> tuple[list[str], list[str]]:
    """Return (short motif tags, explanatory sentences) for ``move``."""
    motifs: list[str] = []
    reasons: list[str] = []
    us = board.turn
    them = not us
    piece = board.piece_at(move.from_square)
    if piece is None:
        return motifs, reasons
    captured = board.piece_at(move.to_square)
    if board.is_en_passant(move):
        captured = chess.Piece(chess.PAWN, them)

    # Was the moving piece under attack and insufficiently defended?
    if board.is_attacked_by(them, move.from_square) and piece.piece_type != chess.KING:
        attackers = board.attackers(them, move.from_square)
        cheapest = min(VALUES[board.piece_type_at(a)] for a in attackers)
        if not board.is_attacked_by(us, move.from_square) or cheapest < VALUES[piece.piece_type]:
            reasons.append(f"It rescues your {PIECE_NAMES[piece.piece_type]}, which was under attack on {sq(move.from_square)}.")

    after = board.copy(stack=False)
    after.push(move)
    moved = after.piece_at(move.to_square)

    if after.is_checkmate():
        motifs.append("Checkmate")
        reasons.append("It is checkmate — the enemy king has no escape.")
        return motifs, reasons

    if after.is_check():
        motifs.append("Check")
        replies = after.legal_moves.count()
        reasons.append("It gives check" + (", leaving the opponent only one legal reply." if replies == 1
                                            else ", forcing the opponent to respond to the threat on their king."))

    if captured is not None:
        gain = VALUES[captured.piece_type]
        defended = after.is_attacked_by(them, move.to_square)
        if not defended:
            motifs.append("Wins material")
            reasons.append(f"It wins a free {PIECE_NAMES[captured.piece_type]} (worth {gain}).")
        elif gain > VALUES[piece.piece_type]:
            motifs.append("Favourable trade")
            reasons.append(f"It trades your {PIECE_NAMES[piece.piece_type]} for their more valuable {PIECE_NAMES[captured.piece_type]}.")
        else:
            reasons.append(f"It captures the {PIECE_NAMES[captured.piece_type]} on {sq(move.to_square)}.")

    if move.promotion:
        motifs.append("Promotion")
        reasons.append(f"The pawn promotes to a {PIECE_NAMES[move.promotion]}.")

    # Fork: the moved piece attacks two or more valuable / undefended targets.
    if moved is not None:
        targets = []
        for t in after.attacks(move.to_square):
            victim = after.piece_at(t)
            if victim is None or victim.color != them:
                continue
            if victim.piece_type == chess.KING or VALUES[victim.piece_type] > VALUES[moved.piece_type] \
                    or not after.is_attacked_by(them, t):
                targets.append((t, victim))
        if len(targets) >= 2:
            motifs.append("Fork")
            names = ", ".join(f"{PIECE_NAMES[v.piece_type]} on {sq(t)}" for t, v in targets[:3])
            reasons.append(f"Fork! Your {PIECE_NAMES[moved.piece_type]} attacks several targets at once: {names}.")

    # Pins created by this move (enemy piece stuck in front of its king).
    new_pins = []
    for s in after.pieces(chess.KNIGHT, them) | after.pieces(chess.BISHOP, them) | \
            after.pieces(chess.ROOK, them) | after.pieces(chess.QUEEN, them):
        if after.is_pinned(them, s) and not board.is_pinned(them, s):
            new_pins.append(s)
    if new_pins:
        motifs.append("Pin")
        p = new_pins[0]
        reasons.append(f"It pins the {PIECE_NAMES[after.piece_type_at(p)]} on {sq(p)} to the king — it cannot move without exposing the king.")

    # Discovered attack: a different piece of ours now attacks something valuable.
    if moved is not None and not board.is_castling(move):
        for s in chess.SquareSet(after.occupied_co[us]):
            if s == move.to_square:
                continue
            before_att = board.attacks(s) if board.piece_at(s) else chess.SquareSet()
            for t in after.attacks(s) & after.occupied_co[them]:
                if t not in before_att and after.piece_type_at(t) in (chess.QUEEN, chess.ROOK, chess.KING):
                    if "Discovered attack" not in motifs:
                        motifs.append("Discovered attack")
                        reasons.append(f"Moving away uncovers an attack by your {PIECE_NAMES[after.piece_type_at(s)]} "
                                       f"on the {PIECE_NAMES[after.piece_type_at(t)]} on {sq(t)}.")

    # Sacrifice: we leave material en prise to a cheaper attacker.
    if moved is not None and moved.piece_type != chess.KING and after.is_attacked_by(them, move.to_square):
        attackers = after.attackers(them, move.to_square)
        cheapest = min(VALUES[after.piece_type_at(a)] for a in attackers)
        gained = VALUES[captured.piece_type] if captured else 0
        if VALUES[moved.piece_type] - gained >= 2 and (cheapest < VALUES[moved.piece_type]
                                                       or not after.is_attacked_by(us, move.to_square)):
            motifs.append("Sacrifice")
            reasons.append(f"It's a sacrifice: your {PIECE_NAMES[moved.piece_type]} can be taken, "
                           "but the follow-up is worth more than the material.")

    if board.is_castling(move):
        motifs.append("Castling")
        reasons.append("Castling tucks your king into safety and activates a rook.")

    # Simple positional hints when nothing tactical happened.
    if not reasons and moved is not None:
        center = {chess.D4, chess.E4, chess.D5, chess.E5}
        if move.to_square in center or (after.attacks(move.to_square) & chess.SquareSet(center)):
            reasons.append("It strengthens your control of the centre.")
        if moved.piece_type in (chess.KNIGHT, chess.BISHOP) and \
                chess.square_rank(move.from_square) in (0, 7):
            reasons.append("It develops a minor piece toward active play.")
        if moved.piece_type == chess.PAWN and chess.square_rank(move.to_square) in (5, 6) and us == chess.WHITE \
                or moved.piece_type == chess.PAWN and chess.square_rank(move.to_square) in (1, 2) and us == chess.BLACK:
            reasons.append("It pushes a pawn closer to promotion.")
    return motifs, reasons


def explain_line(board: chess.Board, line: Line) -> MoveInsight:
    move = line.move
    piece = board.piece_at(move.from_square)
    motifs, reasons = detect_motifs(board, move)
    if board.legal_moves.count() == 1:
        reasons.insert(0, "It is your only legal move.")
    mate = line.mate
    if mate is not None and mate > 0:
        if mate > 1:
            reasons.insert(0, f"It starts a forced checkmate in {mate} moves — every defence loses.")
    elif mate is not None and mate < 0:
        reasons.append(f"Your position is lost (mate in {-mate} against you), but this resists the longest.")
    elif line.cp is not None:
        cp = line.cp
        if cp >= 300:
            reasons.append(f"Stockfish rates your position as winning ({cp / 100:+.1f}).")
        elif cp >= 100:
            reasons.append(f"It keeps a clear advantage ({cp / 100:+.1f}).")
        elif cp > -100:
            reasons.append(f"It keeps the balance ({cp / 100:+.1f}).")
        else:
            reasons.append(f"It is the most stubborn defence available ({cp / 100:+.1f}).")
    if len(line.moves) > 1:
        reply = board.copy(stack=False)
        reply.push(move)
        if line.moves[1] in reply.legal_moves:
            reasons.append(f"Expected reply: {reply.san(line.moves[1])}.")
    return MoveInsight(
        move=move,
        san=board.san(move),
        piece=PIECE_NAMES[piece.piece_type] if piece else "piece",
        from_sq=sq(move.from_square),
        to_sq=sq(move.to_square),
        instruction=describe_move(board, move, you=True),
        motifs=motifs,
        reasons=reasons or ["It is the engine's strongest continuation."],
    )


@dataclass
class SequenceStep:
    ply: int
    mover: chess.Color
    san: str
    sentence: str
    purpose: str


def explain_sequence(board: chess.Board, moves: list[chess.Move], hero: chess.Color) -> list[SequenceStep]:
    """Explain each move of a predicted line (e.g. a forced mate)."""
    b = board.copy(stack=False)
    steps: list[SequenceStep] = []
    for i, move in enumerate(moves):
        if move not in b.legal_moves:
            break
        mover = b.turn
        san = b.san(move)
        sentence = describe_move(b, move, you=(mover == hero))
        motifs, reasons = detect_motifs(b, move)
        legal_before = b.legal_moves.count()
        b.push(move)
        if b.is_checkmate():
            purpose = "Checkmate! The king is attacked and has no escape squares."
        elif mover != hero:
            purpose = ("Forced — this is their only legal move." if legal_before == 1
                       else "The opponent's best defence; alternatives lose even faster.")
        elif b.is_check():
            n = b.legal_moves.count()
            purpose = "Check, " + ("leaving exactly one legal reply." if n == 1 else f"restricting the king to {n} replies.")
            if "Sacrifice" in motifs:
                purpose = "Sacrifice with check — rip open the king's shelter. " + purpose
        elif "Sacrifice" in motifs:
            purpose = "A sacrifice that removes a key defender."
        elif reasons:
            purpose = reasons[0]
        else:
            purpose = "A quiet move that takes away the king's escape squares."
        steps.append(SequenceStep(ply=i, mover=mover, san=san, sentence=sentence, purpose=purpose))
    return steps


def summarize(board: chess.Board, result: AnalysisResult) -> str:
    """One-paragraph summary suitable for a status line."""
    best = result.best
    if best is None:
        if board.is_checkmate():
            return f"Checkmate — {color_name(not board.turn)} wins."
        if board.is_stalemate():
            return "Stalemate — the game is a draw."
        return "No legal moves."
    if best.mate is not None and best.mate > 0:
        return f"Forced checkmate in {best.mate} for {color_name(board.turn)}!"
    if result.mate_search:
        return "No forced mate found at this depth — playing the strongest strategic move instead."
    return ""
