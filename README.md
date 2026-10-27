# Chess Coach

A desktop chess analysis assistant powered by **Stockfish**. Load a position from a screenshot, a FEN or by hand, and Chess Coach tells you the best move in plain language. For example: *"Move your knight from G1 to F3."* It draws an arrow on the board, lists the top three candidates, finds forced checkmates and explains each move of the mating sequence.

> **Fair play.** Chess Coach is for **Chess.com bot games, puzzles (practice/unrated) and the analysis board**, plus offline study. Using an engine during a game against a person, rated or unrated, breaks Chess.com's Fair Play policy. When you start the app you choose what you are analysing. If you choose a live game against a human, engine analysis is switched off. The app never moves pieces, clicks or types on Chess.com. It doesn't watch your screen either: screen capture runs only when you press the button.

## Features

| Area | What you get |
|---|---|
| Board detection | Finds the board in a screenshot or screen capture (OpenCV). Reads every piece, works out whether you are White or Black, infers the side to move from Chess.com's last-move highlight, and builds a FEN including castling rights. |
| Corrections | Squares the detector is unsure about are tinted red. **Edit / correct pieces** lets you place pieces or clear squares. The position is validated (kings, pawns on the back rank, impossible checks) before analysis. |
| Stockfish | Adjustable depth from 6 to 40 and a top-3 MultiPV. Forced mates are shown as *Mate in X* and sorted first. |
| Recommendations | The best move in large text, a sentence naming the piece, its start square and its destination square, the SAN notation, and an evaluation. A green arrow is drawn, with blue and orange arrows for the alternatives, and the start and target squares are highlighted. |
| Explanations | Detects checks, forks, pins, discovered attacks, sacrifices, promotions, captures and castling, and explains them in simple language. |
| Checkmate finder | A deeper mate search mode. The **Checkmate plan** tab shows the whole forced sequence and the purpose of each move ("Forced — this is their only legal move"). When no mate exists, it shows the strongest strategic continuation instead. |
| GUI | Dark-mode PySide6 interface with a drag-and-drop or click-to-move board, eval bar, Analyze / Next Move / Undo / Reset / Flip, move entry (SAN or UCI), FEN import and copy, and a move history. |
| Overlay | An optional transparent, always-on-top window that draws the recommended arrow. It lines up with the board automatically after a screen capture, or you can drag it into place. When locked, mouse clicks pass through it. |
| Automatic analysis | Re-analyses whenever you load a position or enter a move. You can turn this off. |

## Installation

You need **Python 3.10 or newer** and a **Stockfish** binary.

### Windows

1. Install Python from <https://www.python.org/downloads/>. Tick **"Add python.exe to PATH"**.
2. Download or clone this folder.
3. Double-click **`run_windows.bat`**. The first time, it creates a virtual environment, installs `requirements.txt`, and downloads the latest Stockfish into `engines/`.

Manual alternative (PowerShell):

```powershell
cd Chess
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts\download_stockfish.py     # or download from https://stockfishchess.org/download/
python run.py
```

If your CPU is old and Stockfish crashes, run `python scripts\download_stockfish.py --generic`.

### macOS

```bash
brew install python stockfish      # Homebrew: https://brew.sh  (or: python3 scripts/download_stockfish.py)
cd Chess
./run_mac.command                  # creates .venv, installs requirements, launches
```

Manual alternative:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

To use **Capture screen** on macOS, grant *Screen Recording* permission to Terminal (or your Python app) under **System Settings → Privacy & Security → Screen Recording**, then restart it.

### Linux

```bash
sudo apt install stockfish python3-venv   # or: python3 scripts/download_stockfish.py
./run_mac.command                          # the script works on Linux too
```

### Where Stockfish is looked for

In order:

1. The path set in **Engine → Set Stockfish path…**
2. The `STOCKFISH_PATH` environment variable
3. `./engines/` (where `download_stockfish.py` puts it)
4. Your `PATH`
5. Common install locations (Homebrew, `/usr/games`, `Program Files`)

## Using it

1. **Pick the context** in the startup dialog (analysis board, bot game, puzzle or offline study).
2. **Load a position**, using any of these:
   - **Upload screenshot…**: a PNG or JPG of a Chess.com board. Cropping close to the board helps, but it isn't required.
   - **Capture screen**: hides the window, waits for the delay you set (so you can switch to your browser), then takes one screenshot.
   - Paste a **FEN** and press Load, or type moves such as `e4`, `Nf3`, `O-O` or `g1f3`.
   - **Edit / correct pieces**: left-click places the selected piece, right-click clears a square.
3. **Check the position.** Fix any red-tinted squares, and check that **Side to move** and **I play** are right.
4. **Analyze** (shortcut: Space). Read the big move, the instruction and the reasons. The *Top 3 moves* tab shows the alternatives.
5. Turn on **Checkmate finder mode** to search deeper for forced mates. Then open the *Checkmate plan* tab.
6. **Next Move** plays the recommendation on the in-app board, so you can step through a line. Enter the opponent's reply to continue. **Undo** and **Reset** work as you'd expect.
7. **Overlay** (optional): after a screen capture it lines up with the board. Otherwise drag it over the board and resize it from the bottom-right corner. Press **Lock overlay** to make clicks pass through.

### Getting accurate piece recognition: calibrate once

Chess.com offers many piece styles. Out of the box, Chess Coach compares piece silhouettes with built-in templates. That works for standard-looking sets, but it can confuse similar shapes, such as a bishop and a pawn. For near-perfect recognition:

1. On Chess.com, open a new **analysis board** with your usual board and piece theme, showing the starting position.
2. Take a screenshot.
3. In Chess Coach, choose **Calibrate piece set…** and pick that screenshot.

The learned templates are saved in `~/.chess_coach/piece_templates/`. You can remove them with **Engine → Reset piece calibration**. Calibrate again if you change piece themes.

### When detection goes wrong

- **"Board not found"**: make sure the whole board is visible and no popup covers it, or crop the screenshot closer to the board.
- **Wrong pieces**: fix them in edit mode, or calibrate (see above).
- **Wrong side to move**: use the *Side to move* selector. The app infers it from the yellow last-move highlight; when there isn't one, it assumes it's your move.
- **Board upside down**: change **I play** or press **Flip board**.
- The app refuses to analyse illegal positions (missing kings, pawns on the first or last rank, and so on) and tells you what's wrong.

## Project layout

```
chess-coach/  (this repository)
├── run.py                     # python run.py
├── run_windows.bat            # double-click launcher (Windows)
├── run_mac.command            # double-click launcher (macOS / Linux)
├── requirements.txt
├── scripts/download_stockfish.py
├── chess_coach/
│   ├── app.py                 # QApplication + fair-play gate
│   ├── config.py              # settings persisted in ~/.chess_coach/settings.json
│   ├── engine.py              # Stockfish discovery & MultiPV / mate search
│   ├── explain.py             # tactics detection & plain-language explanations
│   ├── vision/
│   │   ├── board_detector.py  # find the 8x8 grid in a screenshot
│   │   ├── pieces.py          # silhouette-based piece classifier + calibration
│   │   ├── recognizer.py      # screenshot -> chess.Board (+ orientation, turn, validation)
│   │   └── capture.py         # one-shot screen capture (mss)
│   └── gui/
│       ├── main_window.py     # main window & workflow
│       ├── board_widget.py    # interactive board, arrows, highlights, edit mode
│       ├── overlay.py         # transparent overlay window
│       ├── eval_bar.py, fairplay.py, styles.py, workers.py
└── tests/                     # pytest suite (vision runs on synthetic screenshots)
```

## Running the tests

```bash
pip install pytest
python -m pytest tests
```

The engine tests are skipped when Stockfish isn't installed.
