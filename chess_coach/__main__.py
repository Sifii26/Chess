"""Run with ``python -m chess_coach``."""

import sys

REQUIRED = {"chess": "chess", "PySide6": "PySide6", "cv2": "opencv-python", "numpy": "numpy"}


def _check_dependencies() -> bool:
    missing = []
    for module, package in REQUIRED.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if missing:
        print("Missing packages: " + ", ".join(missing))
        print("Install them with:  pip install -r requirements.txt")
        return False
    return True


if __name__ == "__main__":
    if not _check_dependencies():
        sys.exit(1)
    from chess_coach.app import main

    sys.exit(main())
