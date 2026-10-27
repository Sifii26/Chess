#!/bin/bash
# Double-click (or run ./run_mac.command) to launch Chess Coach on macOS / Linux.
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv || { echo "Python 3.10+ is required: https://www.python.org/downloads/"; exit 1; }
    .venv/bin/python -m pip install --upgrade pip
    .venv/bin/python -m pip install -r requirements.txt
    if ! command -v stockfish >/dev/null 2>&1; then
        .venv/bin/python scripts/download_stockfish.py || echo "Install Stockfish with: brew install stockfish"
    fi
fi
exec .venv/bin/python run.py
