"""Main application window."""

from __future__ import annotations

import html

import chess
from PySide6.QtCore import QRect, Qt, QThreadPool, QTimer
from PySide6.QtGui import QAction, QColor, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSlider, QSpinBox, QTabWidget, QTextBrowser, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import __version__
from ..config import APP_NAME, Settings
from ..engine import AnalysisResult, Engine, find_stockfish, format_score
from ..explain import describe_move, explain_line, explain_sequence, summarize
from ..vision import BoardNotFoundError, load_image, recognize, validate
from ..vision.capture import CaptureError, grab_screen
from ..vision.pieces import calibrate, clear_calibration, has_calibration
from ..vision.recognizer import _infer_castling
from .board_widget import FROM_HL, TO_HL, Arrow, BoardWidget
from .eval_bar import EvalBar
from .fairplay import ALLOWED, FairPlayDialog
from .overlay import OverlayWindow

ARROW_COLORS = [QColor(46, 204, 113, 210), QColor(66, 165, 245, 150), QColor(255, 167, 38, 130)]
_KINDS = (("Pawn", chess.PAWN), ("Knight", chess.KNIGHT), ("Bishop", chess.BISHOP),
          ("Rook", chess.ROOK), ("Queen", chess.QUEEN), ("King", chess.KING))
PALETTE = [(f"{side} {name}", chess.Piece(t, color))
           for side, color in (("White", chess.WHITE), ("Black", chess.BLACK)) for name, t in _KINDS]
PALETTE.append(("Eraser (empty square)", None))


def card(title: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(8)
    if title:
        t = QLabel(f"<b>{title}</b>")
        lay.addWidget(t)
    return frame, lay


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings, context: str):
        super().__init__()
        self.settings = settings
        self.context = context
        self.board = chess.Board()
        self.hero: chess.Color = chess.WHITE
        self.engine = Engine(settings.stockfish_path, settings.threads, settings.hash_mb)
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)
        self.generation = 0
        self.last_result: AnalysisResult | None = None
        self.last_detection = None
        self.overlay = OverlayWindow()

        self.setWindowTitle(f"{APP_NAME} {__version__}")
        self.resize(1360, 860)
        self._build_ui()
        self._build_menu()
        self._apply_context()
        self.set_position(chess.Board(), "Starting position")

    # ================================================================ UI
    def _build_ui(self) -> None:
        root = QWidget()
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(12, 12, 12, 12)
        h.setSpacing(12)

        # ---- left: eval bar + board
        left = QVBoxLayout()
        self.banner = QLabel()
        self.banner.setObjectName("warning")
        self.banner.setWordWrap(True)
        self.banner.hide()
        left.addWidget(self.banner)
        bh = QHBoxLayout()
        self.eval_bar = EvalBar()
        self.board_widget = BoardWidget()
        self.board_widget.moveMade.connect(self.on_user_move)
        self.board_widget.positionEdited.connect(self.on_position_edited)
        bh.addWidget(self.eval_bar)
        bh.addWidget(self.board_widget, 1)
        left.addLayout(bh, 1)
        buttons = QHBoxLayout()
        self.btn_analyze = QPushButton("Analyze")
        self.btn_analyze.setObjectName("primary")
        self.btn_analyze.setShortcut(QKeySequence("Space"))
        self.btn_next = QPushButton("Next Move ▶")
        self.btn_next.setToolTip("Play the recommended move on this board (does not touch Chess.com).")
        self.btn_undo = QPushButton("◀ Undo")
        self.btn_undo.setShortcut(QKeySequence.StandardKey.Undo)
        self.btn_reset = QPushButton("Reset")
        self.btn_flip = QPushButton("Flip board")
        for b in (self.btn_analyze, self.btn_next, self.btn_undo, self.btn_reset, self.btn_flip):
            buttons.addWidget(b)
        self.btn_analyze.clicked.connect(self.analyze)
        self.btn_next.clicked.connect(self.next_move)
        self.btn_undo.clicked.connect(self.undo)
        self.btn_reset.clicked.connect(lambda: self.set_position(chess.Board(), "Board reset"))
        self.btn_flip.clicked.connect(lambda: self.set_hero(not self.hero))
        left.addLayout(buttons)
        h.addLayout(left, 5)

        # ---- right: scrollable panel
        panel = QWidget()
        v = QVBoxLayout(panel)
        v.setContentsMargins(0, 0, 6, 0)
        v.setSpacing(10)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(panel)
        scroll.setMinimumWidth(470)
        h.addWidget(scroll, 4)

        # Recommendation card
        rec, rl = card()
        self.turn_label = QLabel("White to move")
        self.turn_label.setObjectName("muted")
        rl.addWidget(self.turn_label)
        self.best_label = QLabel("—")
        self.best_label.setObjectName("bestMove")
        rl.addWidget(self.best_label)
        self.instruction = QLabel("Load a position and press Analyze.")
        self.instruction.setObjectName("instruction")
        self.instruction.setWordWrap(True)
        rl.addWidget(self.instruction)
        er = QHBoxLayout()
        self.eval_label = QLabel("")
        self.eval_label.setObjectName("evalLabel")
        self.eval_label.setMinimumWidth(96)
        self.mate_badge = QLabel("")
        self.mate_badge.setObjectName("mateBadge")
        self.mate_badge.hide()
        self.depth_label = QLabel("")
        self.depth_label.setObjectName("muted")
        er.addWidget(self.eval_label)
        er.addWidget(self.mate_badge)
        er.addStretch(1)
        er.addWidget(self.depth_label)
        rl.addLayout(er)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        chips_w = QWidget()
        chips_w.setObjectName("chips")
        chips_w.setLayout(self.chips)
        rl.addWidget(chips_w)
        self.reasons = QLabel("")
        self.reasons.setWordWrap(True)
        self.reasons.setTextFormat(Qt.TextFormat.RichText)
        rl.addWidget(self.reasons)
        self.summary = QLabel("")
        self.summary.setObjectName("warning")
        self.summary.setWordWrap(True)
        rl.addWidget(self.summary)
        v.addWidget(rec)

        # Tabs: candidate lines / mate plan / move list
        self.tabs = QTabWidget()
        self.lines_tree = QTreeWidget()
        self.lines_tree.setHeaderLabels(["#", "Move", "Eval", "Line"])
        self.lines_tree.setRootIsDecorated(False)
        self.lines_tree.setColumnWidth(0, 28)
        self.lines_tree.setColumnWidth(1, 70)
        self.lines_tree.setColumnWidth(2, 64)
        self.lines_tree.setMinimumHeight(120)
        self.mate_view = QTextBrowser()
        self.mate_view.setMinimumHeight(160)
        self.moves_list = QListWidget()
        self.tabs.addTab(self.lines_tree, "Top 3 moves")
        self.tabs.addTab(self.mate_view, "Checkmate plan")
        self.tabs.addTab(self.moves_list, "Move history")
        v.addWidget(self.tabs)

        # Analysis settings
        st, sl = card("Analysis")
        g = QGridLayout()
        g.addWidget(QLabel("Depth"), 0, 0)
        self.depth_slider = QSlider(Qt.Orientation.Horizontal)
        self.depth_slider.setRange(6, 40)
        self.depth_slider.setValue(self.settings.depth)
        self.depth_value = QLabel(str(self.settings.depth))
        self.depth_slider.valueChanged.connect(self._depth_changed)
        g.addWidget(self.depth_slider, 0, 1)
        g.addWidget(self.depth_value, 0, 2)
        self.chk_mate = QCheckBox("Checkmate finder mode (search deeper for forced mates)")
        self.chk_mate.setChecked(self.settings.mate_mode)
        self.chk_mate.toggled.connect(self._mate_mode_changed)
        g.addWidget(self.chk_mate, 1, 0, 1, 3)
        self.chk_auto = QCheckBox("Analyze automatically when the position changes")
        self.chk_auto.setChecked(self.settings.auto_analyze)
        self.chk_auto.toggled.connect(self._auto_changed)
        g.addWidget(self.chk_auto, 2, 0, 1, 3)
        g.addWidget(QLabel("I play"), 3, 0)
        self.hero_combo = QComboBox()
        self.hero_combo.addItems(["White (board from White's side)", "Black (board from Black's side)"])
        self.hero_combo.currentIndexChanged.connect(lambda i: self.set_hero(chess.WHITE if i == 0 else chess.BLACK))
        g.addWidget(self.hero_combo, 3, 1, 1, 2)
        g.addWidget(QLabel("Side to move"), 4, 0)
        self.turn_combo = QComboBox()
        self.turn_combo.addItems(["White", "Black"])
        self.turn_combo.activated.connect(self._turn_changed)
        g.addWidget(self.turn_combo, 4, 1, 1, 2)
        sl.addLayout(g)
        v.addWidget(st)

        # Manual input
        inp, il = card("Enter moves / FEN")
        row = QHBoxLayout()
        self.move_edit = QLineEdit()
        self.move_edit.setPlaceholderText("Move, e.g. Nf3, e2e4, O-O")
        self.move_edit.returnPressed.connect(self.play_typed_move)
        b = QPushButton("Play")
        b.clicked.connect(self.play_typed_move)
        row.addWidget(self.move_edit, 1)
        row.addWidget(b)
        il.addLayout(row)
        row = QHBoxLayout()
        self.fen_edit = QLineEdit()
        self.fen_edit.setPlaceholderText("Paste a FEN")
        self.fen_edit.returnPressed.connect(self.load_fen)
        b = QPushButton("Load")
        b.clicked.connect(self.load_fen)
        c = QPushButton("Copy FEN")
        c.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.board.fen()))
        row.addWidget(self.fen_edit, 1)
        row.addWidget(b)
        row.addWidget(c)
        il.addLayout(row)
        v.addWidget(inp)

        # Screenshot tools
        sc, scl = card("Board from screenshot")
        g = QGridLayout()
        self.btn_upload = QPushButton("Upload screenshot…")
        self.btn_upload.clicked.connect(self.open_screenshot)
        self.btn_capture = QPushButton("Capture screen")
        self.btn_capture.setToolTip("Hides this window, waits a few seconds, then takes ONE screenshot.")
        self.btn_capture.clicked.connect(self.capture_screen)
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(0, 10)
        self.delay_spin.setSuffix(" s delay")
        self.delay_spin.setValue(self.settings.capture_delay_s)
        g.addWidget(self.btn_upload, 0, 0)
        g.addWidget(self.btn_capture, 0, 1)
        g.addWidget(self.delay_spin, 0, 2)
        self.btn_edit = QPushButton("Edit / correct pieces")
        self.btn_edit.setCheckable(True)
        self.btn_edit.toggled.connect(self.toggle_edit_mode)
        self.palette_combo = QComboBox()
        for name, _ in PALETTE:
            self.palette_combo.addItem(name)
        self.palette_combo.currentIndexChanged.connect(
            lambda i: setattr(self.board_widget, "edit_piece", PALETTE[i][1]))
        self.palette_combo.setEnabled(False)
        btn_clear = QPushButton("Clear board")
        btn_clear.clicked.connect(self.clear_board)
        g.addWidget(self.btn_edit, 1, 0)
        g.addWidget(self.palette_combo, 1, 1)
        g.addWidget(btn_clear, 1, 2)
        self.btn_calibrate = QPushButton("Calibrate piece set…")
        self.btn_calibrate.setToolTip("Teach the app your Chess.com piece style from a screenshot of the starting position.")
        self.btn_calibrate.clicked.connect(self.calibrate_pieces)
        self.btn_overlay = QPushButton("Overlay")
        self.btn_overlay.setCheckable(True)
        self.btn_overlay.toggled.connect(self.toggle_overlay)
        self.btn_lock = QPushButton("Lock overlay")
        self.btn_lock.setCheckable(True)
        self.btn_lock.setEnabled(False)
        self.btn_lock.toggled.connect(self.overlay.set_locked)
        g.addWidget(self.btn_calibrate, 2, 0)
        g.addWidget(self.btn_overlay, 2, 1)
        g.addWidget(self.btn_lock, 2, 2)
        scl.addLayout(g)
        hint = QLabel("Tip: in edit mode, left-click places the selected piece, right-click empties a square. "
                      "Squares the detector was unsure about are tinted red.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        scl.addWidget(hint)
        self.detect_warnings = QLabel("")
        self.detect_warnings.setObjectName("warning")
        self.detect_warnings.setWordWrap(True)
        scl.addWidget(self.detect_warnings)
        v.addWidget(sc)
        v.addStretch(1)

        self.status = self.statusBar()
        self.engine_label = QLabel()
        self.status.addPermanentWidget(self.engine_label)
        self._update_engine_label()

    def _build_menu(self) -> None:
        m = self.menuBar()
        f = m.addMenu("&File")
        for text, slot, key in (("Open screenshot…", self.open_screenshot, "Ctrl+O"),
                                ("Capture screen", self.capture_screen, "Ctrl+Shift+C"),
                                ("Copy FEN", lambda: QGuiApplication.clipboard().setText(self.board.fen()), "Ctrl+Shift+F")):
            a = QAction(text, self)
            a.setShortcut(QKeySequence(key))
            a.triggered.connect(slot)
            f.addAction(a)
        f.addSeparator()
        q = QAction("Quit", self)
        q.setShortcut(QKeySequence.StandardKey.Quit)
        q.triggered.connect(self.close)
        f.addAction(q)
        e = m.addMenu("&Engine")
        a = QAction("Set Stockfish path…", self)
        a.triggered.connect(self.choose_engine)
        e.addAction(a)
        a = QAction("Reset piece calibration", self)
        a.triggered.connect(self._reset_calibration)
        e.addAction(a)
        a = QAction("Change what I'm analysing (fair play)…", self)
        a.triggered.connect(self.change_context)
        e.addAction(a)
        hmenu = m.addMenu("&Help")
        a = QAction("How to use", self)
        a.triggered.connect(self.show_help)
        hmenu.addAction(a)

    # ================================================================ fair play
    @property
    def analysis_allowed(self) -> bool:
        return self.context in ALLOWED

    def _apply_context(self) -> None:
        allowed = self.analysis_allowed
        for w in (self.btn_analyze, self.btn_next, self.chk_mate, self.btn_overlay):
            w.setEnabled(allowed)
        if allowed:
            self.banner.setText(f"Mode: {self.context}. Engine help is for bots, puzzles and analysis only.")
            self.banner.setStyleSheet("color: #8b949e;")
        else:
            self.banner.setText("Engine analysis is disabled because you're in a live game against a person. "
                                "You can still use the board. Change this under Engine ▸ Change what I'm analysing.")
            self.banner.setStyleSheet("color: #ffb86b; font-weight: 600;")
            self.btn_overlay.setChecked(False)
            self._clear_recommendation("Engine disabled for games against humans.")
        self.banner.show()

    def change_context(self) -> None:
        dlg = FairPlayDialog(self, preselect=self.context, acknowledged=True)
        if dlg.exec():
            self.context = dlg.context
            self._apply_context()
            if self.analysis_allowed:
                self._maybe_auto_analyze()

    # ================================================================ position handling
    def set_position(self, board: chess.Board, message: str = "") -> None:
        self.board = board
        self.board_widget.warn_squares = set()
        self._refresh_board()
        if message:
            self.status.showMessage(message, 5000)
        self._maybe_auto_analyze()

    def _refresh_board(self) -> None:
        self.board_widget.set_board(self.board)
        self.board_widget.clear_annotations()
        self.overlay.set_move(None, self.board_widget.flipped)
        self.fen_edit.setText(self.board.fen())
        self.turn_combo.blockSignals(True)
        self.turn_combo.setCurrentIndex(0 if self.board.turn == chess.WHITE else 1)
        self.turn_combo.blockSignals(False)
        who = "White" if self.board.turn else "Black"
        mine = "your move" if self.board.turn == self.hero else "opponent's move"
        self.turn_label.setText(f"{who} to move · {mine}")
        self._refresh_history()
        self.btn_undo.setEnabled(bool(self.board.move_stack))
        self.last_result = None

    def _refresh_history(self) -> None:
        self.moves_list.clear()
        replay = chess.Board(self.board.root().fen()) if self.board.move_stack else None
        if replay is None:
            return
        for mv in self.board.move_stack:
            num = replay.fullmove_number
            prefix = f"{num}." if replay.turn == chess.WHITE else f"{num}…"
            self.moves_list.addItem(f"{prefix} {replay.san(mv)}")
            replay.push(mv)
        self.moves_list.scrollToBottom()

    def set_hero(self, color: chess.Color) -> None:
        self.hero = color
        self.board_widget.flipped = color == chess.BLACK
        self.eval_bar.flipped = self.board_widget.flipped
        self.hero_combo.blockSignals(True)
        self.hero_combo.setCurrentIndex(0 if color == chess.WHITE else 1)
        self.hero_combo.blockSignals(False)
        self.board_widget.update()
        self.eval_bar.update()
        who = "White" if self.board.turn else "Black"
        mine = "your move" if self.board.turn == self.hero else "opponent's move"
        self.turn_label.setText(f"{who} to move · {mine}")
        if self.last_result is not None:
            self._show_result(self.last_result)

    def on_user_move(self, move: chess.Move) -> None:
        self.board.push(move)
        self._refresh_board()
        self._maybe_auto_analyze()

    def play_typed_move(self) -> None:
        text = self.move_edit.text().strip()
        if not text:
            return
        try:
            move = self.board.parse_san(text)
        except ValueError:
            try:
                move = chess.Move.from_uci(text.lower())
                if move not in self.board.legal_moves:
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "Illegal move",
                                    f"“{text}” is not a legal move here.\nUse SAN (Nf3, exd5, O-O, e8=Q) or UCI (g1f3).")
                return
        self.move_edit.clear()
        self.on_user_move(move)

    def load_fen(self) -> None:
        fen = self.fen_edit.text().strip()
        try:
            board = chess.Board(fen)
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid FEN", f"That FEN could not be read:\n{exc}")
            return
        problems = validate(board)
        if problems:
            QMessageBox.warning(self, "Questionable position", "\n".join(problems))
        self.set_position(board, "FEN loaded")

    def undo(self) -> None:
        if self.board.move_stack:
            self.board.pop()
            self._refresh_board()
            self._maybe_auto_analyze()

    def next_move(self) -> None:
        """Play the engine's recommendation on the in-app board."""
        if not self.analysis_allowed:
            return
        if self.last_result and self.last_result.best and self.last_result.fen == self.board.fen():
            self.on_user_move(self.last_result.best.move)
        else:
            self.analyze(then_play=True)

    def _turn_changed(self, idx: int) -> None:
        board = chess.Board(self.board.fen())
        board.turn = chess.WHITE if idx == 0 else chess.BLACK
        board.ep_square = None
        self.set_position(board, "Side to move changed")

    def clear_board(self) -> None:
        board = chess.Board(None)
        self.board = board
        if not self.btn_edit.isChecked():
            self.btn_edit.setChecked(True)
        self._refresh_board()
        self.on_position_edited()

    # ================================================================ edit mode
    def toggle_edit_mode(self, on: bool) -> None:
        self.board_widget.edit_mode = on
        self.palette_combo.setEnabled(on)
        self.btn_edit.setText("Done editing" if on else "Edit / correct pieces")
        if on:
            # Editing works on a flat position (no move history).
            flat = chess.Board(self.board.fen())
            self.board = flat
            self.board_widget.set_board(flat)
            self.board_widget.clear_annotations()
            self.status.showMessage("Edit mode: left-click to place, right-click to clear.", 6000)
            return
        board = chess.Board(self.board.fen())
        inferred = _infer_castling(board)
        # Keep rights the user already had, but drop any the new piece placement makes impossible.
        board.castling_rights = (inferred & self.board.castling_rights) if self.board.castling_rights else inferred
        self.set_position(board, "Position updated")
        self.on_position_edited()

    def on_position_edited(self) -> None:
        self.fen_edit.setText(self.board.fen())
        problems = validate(self.board)
        self.detect_warnings.setText("\n".join(problems))

    # ================================================================ analysis
    def _maybe_auto_analyze(self) -> None:
        if self.chk_auto.isChecked() and self.analysis_allowed and not self.board_widget.edit_mode:
            self.analyze()

    def analyze(self, then_play: bool = False) -> None:
        if not self.analysis_allowed:
            return
        if self.board_widget.edit_mode:
            self.btn_edit.setChecked(False)  # finishing the edit triggers analysis itself
            if not self.chk_auto.isChecked():
                self.analyze(then_play)
            return
        problems = validate(self.board)
        if problems:
            self._clear_recommendation("Fix the position first: " + " ".join(problems))
            self.detect_warnings.setText("\n".join(problems))
            return
        if self.board.is_game_over():
            self._clear_recommendation(summarize(self.board, AnalysisResult(self.board.fen())))
            return
        if self.engine.path is None:
            self._clear_recommendation("Stockfish not found. Use Engine ▸ Set Stockfish path…, or run "
                                       "`python scripts/download_stockfish.py`.")
            return
        self.generation += 1
        self._then_play = then_play
        self.btn_analyze.setText("Analyzing…")
        self.depth_label.setText("thinking…")
        from .workers import AnalysisJob
        job = AnalysisJob(self.engine, self.board, self.generation, lambda: self.generation,
                          depth=self.depth_slider.value(), multipv=self.settings.multipv,
                          mate_search=self.chk_mate.isChecked(), mate_depth=self.settings.mate_search_depth)
        job.signals.finished.connect(self._on_result)
        job.signals.failed.connect(self._on_failed)
        self.pool.start(job)

    def _on_failed(self, gen: int, message: str) -> None:
        if gen != self.generation:
            return
        self.btn_analyze.setText("Analyze")
        self.depth_label.setText("")
        self._clear_recommendation("Engine problem: " + message)
        self._update_engine_label()

    def _on_result(self, gen: int, result: AnalysisResult) -> None:
        if gen != self.generation or result.fen != self.board.fen():
            return
        self.btn_analyze.setText("Analyze")
        self._update_engine_label()
        self.last_result = result
        self._show_result(result)
        if getattr(self, "_then_play", False) and result.best:
            self._then_play = False
            self.on_user_move(result.best.move)

    def _clear_recommendation(self, message: str) -> None:
        self.best_label.setText("—")
        self.instruction.setText(message)
        self.eval_label.setText("")
        self.mate_badge.hide()
        self.reasons.setText("")
        self.summary.setText("")
        self.depth_label.setText("")
        self.lines_tree.clear()
        self.mate_view.clear()
        self._set_chips([])
        self.board_widget.clear_annotations()
        self.overlay.set_move(None, self.board_widget.flipped)
        self.eval_bar.set_eval(None, None)

    def _set_chips(self, motifs: list[str]) -> None:
        while self.chips.count():
            item = self.chips.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for m in motifs:
            lab = QLabel(m)
            lab.setObjectName("chip")
            self.chips.addWidget(lab)
        self.chips.addStretch(1)

    def _show_result(self, result: AnalysisResult) -> None:
        board = self.board
        best = result.best
        if best is None:
            self._clear_recommendation(summarize(board, result) or "No moves to analyse.")
            return
        insight = explain_line(board, best)
        yours = board.turn == self.hero
        self.best_label.setText(insight.san)
        sentence = describe_move(board, best.move, you=yours)
        self.instruction.setText(sentence if yours else "Opponent's best: " + sentence[0].lower() + sentence[1:])
        self.eval_label.setText(format_score(best.score, self.hero))
        self.eval_label.setToolTip("Evaluation from your side: + is good for you, M = forced mate.")
        mate = best.mate
        if mate is not None and mate > 0:
            self.mate_badge.setText(f"Mate in {mate}" if yours else f"They mate in {mate}")
            self.mate_badge.show()
        elif mate is not None and mate < 0:
            self.mate_badge.setText(f"Mated in {-mate}")
            self.mate_badge.show()
        else:
            self.mate_badge.hide()
        self.depth_label.setText(f"your perspective · depth {best.depth}")
        self._set_chips(insight.motifs)
        self.reasons.setText("<ul style='margin-left:-20px'>" +
                             "".join(f"<li>{html.escape(r)}</li>" for r in insight.reasons) + "</ul>")
        self.summary.setText(summarize(board, result))

        white = best.score.white()
        self.eval_bar.set_eval(white.score(), white.mate())

        # Candidate lines
        self.lines_tree.clear()
        for i, line in enumerate(result.lines[:3]):
            san_line = board.variation_san(line.moves[:10]) if line.moves else ""
            item = QTreeWidgetItem([str(i + 1), board.san(line.move), format_score(line.score, self.hero), san_line])
            item.setToolTip(3, san_line)
            item.setForeground(1, ARROW_COLORS[i])
            self.lines_tree.addTopLevelItem(item)

        self._show_plan(result)

        # Arrows: best move biggest; alternatives thinner.
        arrows = [Arrow(line.move.from_square, line.move.to_square, ARROW_COLORS[i], 0.22 if i == 0 else 0.13)
                  for i, line in reversed(list(enumerate(result.lines[:3])))]
        highlights = {best.move.from_square: FROM_HL, best.move.to_square: TO_HL}
        self.board_widget.set_annotations(arrows, highlights)
        self.overlay.set_move(best.move, self.board_widget.flipped, f"{insight.san} · {format_score(best.score, self.hero)}")

    def _show_plan(self, result: AnalysisResult) -> None:
        board = self.board
        best = result.best
        mate = best.mate
        mover = board.turn
        hero_name = "You" if mover == self.hero else "Side to move"
        if mate is not None and mate > 0:
            title = f"<h3>Forced checkmate in {mate}</h3>"
            intro = "<p>Every reply is covered. Follow this sequence:</p>"
            moves = best.moves[: mate * 2 - 1]
        elif mate is not None and mate < 0:
            title = f"<h3>Danger: forced mate against the side to move in {-mate}</h3>"
            intro = "<p>The position can't be saved against perfect play. This is the longest resistance:</p>"
            moves = best.moves[: -mate * 2]
        else:
            title = "<h3>No forced checkmate found</h3>"
            intro = ("<p>No forced mate exists at this depth, so here is the strongest strategic "
                     "continuation instead:</p>")
            moves = best.moves[:8]
        steps = explain_sequence(board, moves, hero=mover)
        rows = []
        for st in steps:
            who = hero_name if st.mover == mover else "Opponent"
            num = (st.ply // 2) + 1
            rows.append(f"<p><b>{num}. {who}: {html.escape(st.san)}</b><br>"
                        f"{html.escape(st.sentence)}<br><span style='color:#8b949e'>{html.escape(st.purpose)}</span></p>")
        self.mate_view.setHtml(title + intro + "".join(rows))
        if mate is not None and mate > 0:
            self.tabs.setCurrentWidget(self.mate_view)

    # ================================================================ screenshots
    def open_screenshot(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open screenshot", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        try:
            img = load_image(path)
        except BoardNotFoundError as exc:
            QMessageBox.warning(self, "Could not open image", str(exc))
            return
        self._load_detection(img, from_screen=False)

    def capture_screen(self) -> None:
        delay = self.delay_spin.value()
        self.settings.capture_delay_s = delay
        self.hide()
        self.overlay.hide()
        QTimer.singleShot(max(250, delay * 1000), self._do_capture)

    def _do_capture(self) -> None:
        try:
            img = grab_screen()
        except CaptureError as exc:
            self.show()
            QMessageBox.warning(self, "Screen capture failed", str(exc))
            return
        finally:
            if self.btn_overlay.isChecked():
                self.overlay.show()
        self.show()
        self.raise_()
        self.activateWindow()
        self._load_detection(img, from_screen=True)

    def _load_detection(self, img, from_screen: bool) -> None:
        try:
            det = recognize(img)
        except BoardNotFoundError as exc:
            QMessageBox.warning(
                self, "Board not found",
                f"{exc}\n\nTips:\n• Make sure the whole board is visible and not covered by popups.\n"
                "• Crop the screenshot closer to the board.\n• Or set up the position by hand with "
                "'Edit / correct pieces'.")
            return
        except Exception as exc:  # unexpected vision failure — never crash the app
            QMessageBox.critical(self, "Detection error", f"Something went wrong while reading the board:\n{exc}")
            return
        self.last_detection = det
        self.set_hero(det.player_color)
        self.board_widget.warn_squares = set(det.low_confidence)
        board = det.board
        warn = list(det.warnings)
        if not det.calibrated:
            warn.append("Tip: run 'Calibrate piece set…' once for much more accurate piece recognition.")
        self.detect_warnings.setText("\n".join(warn))
        self.board = board
        self._refresh_board()
        self.board_widget.warn_squares = set(det.low_confidence)
        self.status.showMessage(f"Board detected — you play {'White' if det.white_bottom else 'Black'}. "
                                "Check the pieces, then analyse.", 8000)
        if from_screen:
            self._align_overlay(det.region)
        if validate(board):
            self._clear_recommendation("The detected position looks wrong — please correct it with "
                                       "'Edit / correct pieces'.")
            return
        self._maybe_auto_analyze()

    def _align_overlay(self, region) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        dpr = screen.devicePixelRatio() or 1.0
        geo = screen.geometry()
        self.overlay.align_to(QRect(int(geo.x() + region.x / dpr), int(geo.y() + region.y / dpr),
                                    int(region.size / dpr), int(region.size / dpr)))

    def calibrate_pieces(self) -> None:
        QMessageBox.information(
            self, "Calibrate piece set",
            "Open a screenshot of the STARTING POSITION from Chess.com (e.g. a new analysis board) "
            "using your usual board and piece theme. The app will learn what your pieces look like.")
        path, _ = QFileDialog.getOpenFileName(self, "Starting-position screenshot", "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.webp)")
        if not path:
            return
        try:
            from ..vision import detect_board
            img = load_image(path)
            region = detect_board(img)
            crop = region.crop(img)
            try:
                n = calibrate(crop, white_bottom=True)
            except ValueError:
                n = calibrate(crop, white_bottom=False)
        except (BoardNotFoundError, ValueError) as exc:
            QMessageBox.warning(self, "Calibration failed", str(exc))
            return
        QMessageBox.information(self, "Calibration saved", f"Learned {n} piece samples. Future screenshots "
                                                           "will use your piece set.")

    def _reset_calibration(self) -> None:
        if has_calibration():
            clear_calibration()
            self.status.showMessage("Piece calibration removed; using built-in templates.", 5000)

    # ================================================================ overlay
    def toggle_overlay(self, on: bool) -> None:
        self.btn_lock.setEnabled(on)
        if on:
            self.overlay.show()
            if self.last_result and self.last_result.best:
                self._show_result(self.last_result)
        else:
            self.btn_lock.setChecked(False)
            self.overlay.hide()

    # ================================================================ settings / misc
    def _depth_changed(self, v: int) -> None:
        self.depth_value.setText(str(v))
        self.settings.depth = v

    def _mate_mode_changed(self, on: bool) -> None:
        self.settings.mate_mode = on
        self._maybe_auto_analyze()

    def _auto_changed(self, on: bool) -> None:
        self.settings.auto_analyze = on

    def choose_engine(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Stockfish executable")
        if not path:
            return
        if find_stockfish(path) != path:
            QMessageBox.warning(self, "Not executable", "That file is not an executable program.")
            return
        self.engine.stop()
        self.settings.stockfish_path = path
        self.engine = Engine(path, self.settings.threads, self.settings.hash_mb)
        self._update_engine_label()
        self._maybe_auto_analyze()

    def _update_engine_label(self) -> None:
        if self.engine.path is None:
            self.engine_label.setText("⚠ Stockfish not found")
        else:
            self.engine_label.setText(f"Engine: {self.engine.name if self.engine.name != 'not started' else self.engine.path}")

    def show_help(self) -> None:
        QMessageBox.information(self, "How to use", (
            "1. Load a position: upload a screenshot, capture the screen, paste a FEN, or set it up in edit mode.\n"
            "2. Check the detected pieces (red squares = unsure) and fix them with 'Edit / correct pieces'.\n"
            "3. Make sure 'Side to move' and 'I play' are right.\n"
            "4. Press Analyze (Space). The green arrow shows the best move; blue/orange are alternatives.\n"
            "5. Turn on 'Checkmate finder mode' to search deeper for forced mates.\n"
            "6. 'Next Move' plays the recommendation on this board; enter the reply to continue.\n\n"
            "Chess Coach never moves pieces on Chess.com. Use it only for bots, puzzles and analysis."))

    def closeEvent(self, e) -> None:
        self.generation += 1
        self.settings.save()
        self.overlay.close()
        self.pool.waitForDone(3000)
        self.engine.stop()
        super().closeEvent(e)
