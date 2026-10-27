#!/usr/bin/env python3
"""Launch Chess Coach:  python run.py"""

import runpy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
runpy.run_module("chess_coach", run_name="__main__")
