"""Fair-play gate shown at startup.

Chess.com's Fair Play policy forbids outside assistance in games against
people. This tool is meant for bot games, puzzles (unrated/practice) and the
analysis board. It can't technically verify where a position came from, so the
user must choose the context; choosing a game against a human disables analysis.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QLabel,
                               QRadioButton, QVBoxLayout)

CONTEXT_ANALYSIS = "Analysis board / studying a finished game"
CONTEXT_BOT = "Game against a Chess.com bot"
CONTEXT_PUZZLE = "Puzzles (practice / unrated)"
CONTEXT_OFFLINE = "Offline study (books, my own positions)"
CONTEXT_HUMAN = "A live game against a human (rated or unrated)"

ALLOWED = [CONTEXT_ANALYSIS, CONTEXT_BOT, CONTEXT_PUZZLE, CONTEXT_OFFLINE]


class FairPlayDialog(QDialog):
    def __init__(self, parent=None, preselect: str = CONTEXT_ANALYSIS, acknowledged: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Fair play")
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        intro = QLabel(
            "<h3>What are you analysing?</h3>"
            "Chess Coach is for <b>bot games, puzzles and analysis</b>. Using an engine during a game "
            "against another person breaks Chess.com's Fair Play rules and is unfair to your opponent, "
            "so analysis is disabled in that case. Chess Coach never moves pieces or clicks on Chess.com for you."
        )
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(intro)
        self.group = QButtonGroup(self)
        for text in ALLOWED + [CONTEXT_HUMAN]:
            rb = QRadioButton(text)
            self.group.addButton(rb)
            lay.addWidget(rb)
            if text == preselect:
                rb.setChecked(True)
        self.ack = QCheckBox("I will not use Chess Coach during live games against human opponents.")
        self.ack.setChecked(acknowledged)
        lay.addWidget(self.ack)
        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.group.buttonToggled.connect(self._update)
        self.ack.toggled.connect(self._update)
        self._update()

    @property
    def context(self) -> str:
        btn = self.group.checkedButton()
        return btn.text() if btn else ""

    @property
    def analysis_allowed(self) -> bool:
        return self.context in ALLOWED and self.ack.isChecked()

    def _update(self, *_args) -> None:
        ok = self.buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setEnabled(bool(self.context) and self.ack.isChecked())
        if self.context == CONTEXT_HUMAN:
            ok.setText("Continue without engine")
        else:
            ok.setText("Start")
