"""Stockfish integration: locating the binary and running analyses."""

from __future__ import annotations

import os
import platform
import shutil
import threading
from dataclasses import dataclass, field
from pathlib import Path

import chess
import chess.engine

from .config import ENGINE_DIR


class EngineError(RuntimeError):
    """Raised when Stockfish cannot be found, started or queried."""


def find_stockfish(preferred: str = "") -> str | None:
    """Return the path of a usable Stockfish executable, or None."""
    candidates: list[str] = []
    if preferred:
        candidates.append(preferred)
    if os.environ.get("STOCKFISH_PATH"):
        candidates.append(os.environ["STOCKFISH_PATH"])

    # Binaries fetched by scripts/download_stockfish.py
    if ENGINE_DIR.is_dir():
        for p in sorted(ENGINE_DIR.rglob("stockfish*")):
            if p.is_file() and (p.suffix in ("", ".exe")):
                candidates.append(str(p))

    for name in ("stockfish", "stockfish.exe"):
        found = shutil.which(name)
        if found:
            candidates.append(found)

    if platform.system() == "Darwin":
        candidates += ["/opt/homebrew/bin/stockfish", "/usr/local/bin/stockfish"]
    elif platform.system() == "Windows":
        for base in (os.environ.get("ProgramFiles", ""), os.environ.get("LOCALAPPDATA", "")):
            if base:
                candidates += [str(p) for p in Path(base).glob("Stockfish*/stockfish*.exe")]
    else:
        candidates += ["/usr/games/stockfish", "/usr/bin/stockfish", "/usr/local/bin/stockfish"]

    for c in candidates:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return None


@dataclass
class Line:
    """One principal variation returned by the engine."""

    moves: list[chess.Move]
    score: chess.engine.PovScore  # from the side to move's point of view
    depth: int

    @property
    def move(self) -> chess.Move:
        return self.moves[0]

    @property
    def mate(self) -> int | None:
        """Mate-in-N for the side to move (+N we mate, -N we get mated)."""
        return self.score.relative.mate()

    @property
    def cp(self) -> int | None:
        return self.score.relative.score()


@dataclass
class AnalysisResult:
    fen: str
    lines: list[Line] = field(default_factory=list)
    mate_search: bool = False

    @property
    def best(self) -> Line | None:
        return self.lines[0] if self.lines else None


def format_score(score: chess.engine.PovScore, pov: chess.Color = chess.WHITE) -> str:
    s = score.pov(pov)
    mate = s.mate()
    if mate is not None:
        if mate == 0:
            return "#"
        return f"M{mate}" if mate > 0 else f"-M{-mate}"
    cp = s.score() or 0
    return f"{cp / 100:+.2f}"


class Engine:
    """Thread-safe wrapper around a single Stockfish process."""

    def __init__(self, path: str = "", threads: int = 2, hash_mb: int = 128):
        self.path = find_stockfish(path)
        self.threads = threads
        self.hash_mb = hash_mb
        self._engine: chess.engine.SimpleEngine | None = None
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        if self._engine is None:
            return "not started"
        return self._engine.id.get("name", "Stockfish")

    def start(self) -> None:
        if self._engine is not None:
            return
        if not self.path:
            raise EngineError(
                "Stockfish was not found. Run `python scripts/download_stockfish.py`, "
                "install it with your package manager, or set the path in Settings."
            )
        try:
            self._engine = chess.engine.SimpleEngine.popen_uci(self.path)
            opts = {}
            if "Threads" in self._engine.options:
                opts["Threads"] = self.threads
            if "Hash" in self._engine.options:
                opts["Hash"] = self.hash_mb
            if opts:
                self._engine.configure(opts)
        except (OSError, chess.engine.EngineError) as exc:
            self._engine = None
            raise EngineError(f"Could not start Stockfish at {self.path}: {exc}") from exc

    def stop(self) -> None:
        with self._lock:
            if self._engine is not None:
                try:
                    self._engine.quit()
                except Exception:
                    pass
                self._engine = None

    def analyse(
        self,
        board: chess.Board,
        depth: int = 18,
        multipv: int = 3,
        mate_search: bool = False,
        mate_depth: int = 30,
        time_limit: float | None = None,
    ) -> AnalysisResult:
        """Analyse ``board`` and return up to ``multipv`` candidate lines.

        In mate-search mode the engine searches deeper and is told to look for
        a forced mate; lines delivering mate are sorted to the top.
        """
        if board.is_game_over():
            return AnalysisResult(fen=board.fen(), mate_search=mate_search)
        self.start()
        assert self._engine is not None
        legal = board.legal_moves.count()
        multipv = max(1, min(multipv, legal))
        if mate_search:
            limit = chess.engine.Limit(depth=max(depth, mate_depth), mate=mate_depth // 2,
                                       time=time_limit or 20.0)
        else:
            limit = chess.engine.Limit(depth=depth, time=time_limit)

        with self._lock:
            try:
                infos = self._engine.analyse(board, limit, multipv=multipv)
            except chess.engine.EngineTerminatedError as exc:
                self._engine = None
                raise EngineError("Stockfish stopped unexpectedly. It will restart on the next analysis.") from exc
            except chess.engine.EngineError as exc:
                raise EngineError(f"Engine error: {exc}") from exc

        lines = [
            Line(moves=list(info["pv"]), score=info["score"], depth=info.get("depth", 0))
            for info in infos
            if info.get("pv") and "score" in info
        ]
        # Always prefer the fastest forced mate, then the best evaluation.
        lines.sort(key=lambda ln: _sort_key(ln))
        return AnalysisResult(fen=board.fen(), lines=lines, mate_search=mate_search)


def _sort_key(line: Line) -> tuple:
    mate = line.mate
    if mate is not None and mate > 0:
        return (0, mate)
    if mate is not None and mate < 0:
        return (2, mate)  # being mated: longest resistance first (-10 < -2)
    return (1, -(line.cp or 0))
