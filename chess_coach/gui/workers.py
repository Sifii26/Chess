"""Background workers so the GUI never freezes while Stockfish thinks."""

from __future__ import annotations

import traceback

import chess
from PySide6.QtCore import QObject, QRunnable, Signal

from ..engine import AnalysisResult, Engine


class _Signals(QObject):
    finished = Signal(int, object)   # generation, AnalysisResult
    failed = Signal(int, str)


class AnalysisJob(QRunnable):
    def __init__(self, engine: Engine, board: chess.Board, generation: int, current_gen,
                 depth: int, multipv: int, mate_search: bool, mate_depth: int):
        super().__init__()
        self.engine = engine
        self.board = board.copy()
        self.generation = generation
        self.current_gen = current_gen  # callable -> latest generation
        self.depth = depth
        self.multipv = multipv
        self.mate_search = mate_search
        self.mate_depth = mate_depth
        self.signals = _Signals()

    def run(self) -> None:
        if self.current_gen() != self.generation:
            return  # a newer position was requested while we were queued
        try:
            result: AnalysisResult = self.engine.analyse(
                self.board, depth=self.depth, multipv=self.multipv,
                mate_search=self.mate_search, mate_depth=self.mate_depth)
            self.signals.finished.emit(self.generation, result)
        except Exception as exc:  # surface every failure in the UI
            msg = str(exc) or exc.__class__.__name__
            if not msg:
                msg = traceback.format_exc()
            self.signals.failed.emit(self.generation, msg)
