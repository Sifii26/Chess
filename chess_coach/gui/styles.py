DARK_QSS = """
* { font-family: "Segoe UI", "SF Pro Text", "Inter", "Helvetica Neue", Arial; font-size: 13px; }
QMainWindow, QWidget { background: #16181d; color: #e6e6e6; }
QFrame#card { background: #1f2229; border: 1px solid #2c3039; border-radius: 10px; }
QFrame#card QLabel, QFrame#card QCheckBox, QFrame#card QWidget#chips { background: transparent; }
QLabel#bestMove { font-size: 40px; font-weight: 700; color: #7ee787; }
QLabel#instruction { font-size: 18px; font-weight: 600; color: #ffffff; }
QLabel#evalLabel { font-size: 22px; font-weight: 700; }
QFrame#card QLabel#mateBadge { background: #b62324; color: white; border-radius: 6px; padding: 3px 10px; font-weight: 700; }
QLabel#muted { color: #8b949e; }
QLabel#warning { color: #ffb86b; }
QFrame#card QLabel#chip { background: #30363d; border-radius: 9px; padding: 2px 9px; color: #c9d1d9; }
QPushButton { background: #2b303b; border: 1px solid #3a404d; border-radius: 7px; padding: 7px 12px; color: #e6e6e6; }
QPushButton:hover { background: #343a47; }
QPushButton:pressed { background: #222731; }
QPushButton:disabled { color: #5c6370; }
QPushButton#primary { background: #2ea043; border-color: #2ea043; color: white; font-weight: 700; }
QPushButton#primary:hover { background: #3fb950; }
QPushButton:checked { background: #1f6feb; border-color: #1f6feb; }
QLineEdit, QSpinBox, QComboBox, QTextBrowser, QListWidget, QTreeWidget {
    background: #0f1115; border: 1px solid #2c3039; border-radius: 6px; padding: 4px; selection-background-color: #1f6feb; }
QHeaderView::section { background: #1f2229; color: #8b949e; border: none; padding: 4px; }
QTabWidget::pane { border: 1px solid #2c3039; border-radius: 8px; }
QTabBar::tab { background: #1f2229; padding: 6px 12px; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QTabBar::tab:selected { background: #2b303b; }
QSlider::groove:horizontal { height: 6px; background: #2c3039; border-radius: 3px; }
QSlider::handle:horizontal { background: #2ea043; width: 14px; margin: -5px 0; border-radius: 7px; }
QStatusBar { background: #111318; color: #8b949e; }
QCheckBox::indicator { width: 16px; height: 16px; }
QScrollArea { border: none; }
"""
