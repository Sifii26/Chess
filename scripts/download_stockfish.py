#!/usr/bin/env python3
"""Download the latest official Stockfish build into ./engines/.

    python scripts/download_stockfish.py            # auto-detect the best build
    python scripts/download_stockfish.py --generic  # most compatible (older CPUs)

Builds come from https://github.com/official-stockfish/Stockfish/releases.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import stat
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://github.com/official-stockfish/Stockfish/releases/latest/download/"
ENGINE_DIR = Path(__file__).resolve().parent.parent / "engines"


def pick_asset(generic: bool) -> str:
    system, machine = platform.system(), platform.machine().lower()
    arm = machine in ("arm64", "aarch64")
    if system == "Windows":
        return "stockfish-windows-x86-64.zip" if generic else "stockfish-windows-x86-64-avx2.zip"
    if system == "Darwin":
        if arm:
            return "stockfish-macos-m1-apple-silicon.tar"
        return "stockfish-macos-x86-64.tar" if generic else "stockfish-macos-x86-64-avx2.tar"
    if system == "Linux":
        if arm:
            sys.exit("No official Linux ARM build; install with your package manager (e.g. apt install stockfish).")
        return "stockfish-ubuntu-x86-64.tar" if generic else "stockfish-ubuntu-x86-64-avx2.tar"
    sys.exit(f"Unsupported platform: {system} {machine}")


def safe_extract(archive: Path, dest: Path) -> None:
    dest = dest.resolve()
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            for name in z.namelist():
                if not (dest / name).resolve().is_relative_to(dest):
                    sys.exit(f"Refusing unsafe path in archive: {name}")
            z.extractall(dest)
    else:
        with tarfile.open(archive) as t:
            for m in t.getmembers():
                if not (dest / m.name).resolve().is_relative_to(dest) or m.issym() or m.islnk():
                    continue
                if sys.version_info >= (3, 12):
                    t.extract(m, dest, filter="data")
                else:
                    t.extract(m, dest)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--generic", action="store_true", help="download the most compatible (non-AVX2) build")
    args = ap.parse_args()

    asset = pick_asset(args.generic)
    url = BASE + asset
    ENGINE_DIR.mkdir(exist_ok=True)
    print(f"Downloading {url}")
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / asset
        try:
            with urllib.request.urlopen(url, timeout=60) as resp, open(archive, "wb") as out:
                shutil.copyfileobj(resp, out)
        except OSError as exc:
            sys.exit(f"Download failed: {exc}\nDownload it manually from "
                     "https://stockfishchess.org/download/ and set the path in the app (Engine menu).")
        target = ENGINE_DIR / asset.split(".")[0]
        if target.exists():
            shutil.rmtree(target)
        target.mkdir()
        safe_extract(archive, target)

    exe = None
    for p in target.rglob("stockfish*"):
        if p.is_file() and (p.suffix in ("", ".exe")) and "src" not in p.parts:
            exe = p
            break
    if exe is None:
        sys.exit("Downloaded archive did not contain a Stockfish binary.")
    if os.name != "nt":
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"Stockfish installed: {exe}")
    print("Chess Coach will find it automatically.")


if __name__ == "__main__":
    main()
