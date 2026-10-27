"""PyInstaller 打包入口：不带参数时默认启动网页。

单独运行也可以：``python tools/launcher.py create --dry-run``。
"""

import sys

from netease_sorter.cli import main

if __name__ == "__main__":
    sys.exit(main(["serve"] if len(sys.argv) == 1 else None))
