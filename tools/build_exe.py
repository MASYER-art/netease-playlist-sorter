# -*- coding: utf-8 -*-
"""用 PyInstaller 打单文件 exe，输出到 release/。

需要先装 PyInstaller：``pip install pyinstaller``
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
BUILD = ROOT / "build"


def main() -> int:
    RELEASE.mkdir(exist_ok=True)
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onefile", "--console",
        "--name", "NeteaseSorter",
        "--paths", str(ROOT / "src"),
        "--add-data", f"{ROOT / 'src' / 'netease_sorter' / 'web'};netease_sorter/web",
        "--distpath", str(RELEASE),
        "--workpath", str(BUILD),
        "--specpath", str(BUILD),
        str(ROOT / "tools" / "launcher.py"),
    ]
    start = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        return result.returncode
    exe = RELEASE / "NeteaseSorter.exe"
    print(f"完成：{exe}（{exe.stat().st_size / 1048576:.1f} MB，{time.time() - start:.0f}s）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
