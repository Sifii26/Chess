"""One-shot, user-initiated screen capture.

There is deliberately no continuous screen watching: a capture happens only
when the user clicks the button, so the tool cannot silently follow a live game.
"""

from __future__ import annotations

import numpy as np


class CaptureError(RuntimeError):
    pass


def grab_screen(monitor_index: int = 1) -> np.ndarray:
    """Return a BGR screenshot of one monitor (1 = primary)."""
    try:
        import mss
    except ImportError as exc:
        raise CaptureError("Screen capture requires the 'mss' package (pip install mss).") from exc
    try:
        with mss.mss() as sct:
            monitors = sct.monitors
            mon = monitors[monitor_index] if monitor_index < len(monitors) else monitors[0]
            shot = np.array(sct.grab(mon))  # BGRA
    except Exception as exc:  # mss raises platform-specific errors
        raise CaptureError(
            f"Screen capture failed: {exc}. On macOS, grant Screen Recording permission "
            "to your terminal/Python in System Settings > Privacy & Security."
        ) from exc
    return np.ascontiguousarray(shot[:, :, :3])
