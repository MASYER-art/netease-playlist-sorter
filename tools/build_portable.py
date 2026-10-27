# -*- coding: utf-8 -*-
"""构建免安装运行时：把嵌入式 Python 和依赖装进项目的 runtime/ 目录。

产物（都不进 git）：

    runtime/python/         嵌入式 Python
    runtime/site-packages/  requests / websockets 等依赖
    启动网页.bat            项目根目录
    登录网易云.bat          项目根目录

用法::

    python tools/build_portable.py            # 本地构建（用清华镜像）
    python tools/build_portable.py --zip      # 构建并打出 release/ 里的便携包
    python tools/build_portable.py --force    # 删掉旧 runtime 重建
"""

from __future__ import annotations

import argparse
import io
import shutil
import sys
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime"
PY_DIR = RUNTIME / "python"
SITE = RUNTIME / "site-packages"
RELEASE = ROOT / "release"

PY_VERSION = "3.12.10"
PY_URLS = {
    "org": f"https://www.python.org/ftp/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip",
    "huawei": f"https://mirrors.huaweicloud.com/python/{PY_VERSION}/python-{PY_VERSION}-embed-amd64.zip",
}
PKGS = ["requests", "urllib3", "idna", "certifi", "charset-normalizer", "websockets"]
MIRRORS = {
    "pypi": "https://pypi.org/pypi/{}/json",
    "tuna": "https://pypi.tuna.tsinghua.edu.cn/pypi/{}/json",
}

LAUNCH_BAT = r"""@echo off
chcp 65001 >nul
title 网易云歌单整理器
cd /d "%~dp0"
if not exist "%~dp0runtime\python\python.exe" (
  echo [缺少 runtime] 这个仓库没有内置运行环境。
  echo 请从 Releases 下载便携包，或在项目目录运行：python tools\build_portable.py
  pause
  exit /b 1
)
echo 正在启动，浏览器会自动打开 http://127.0.0.1:8765/
echo 关闭本窗口即可停止服务。
echo.
"%~dp0runtime\python\python.exe" -m netease_sorter serve %*
pause
"""

LOGIN_BAT = r"""@echo off
chcp 65001 >nul
title 登录网易云
cd /d "%~dp0"
if not exist "%~dp0runtime\python\python.exe" (
  echo [缺少 runtime] 这个仓库没有内置运行环境。
  echo 请从 Releases 下载便携包，或在项目目录运行：python tools\build_portable.py
  pause
  exit /b 1
)
echo 会打开一个专用 Edge 窗口，请用网易云 App 扫码登录。
echo 登录成功后窗口会自动关闭。
echo.
"%~dp0runtime\python\python.exe" -m netease_sorter login --from-edge %*
pause
"""


def http_get(url: str, timeout: int = 120) -> bytes:
    last: Exception | None = None
    for _ in range(3):
        try:
            resp = requests.get(url, timeout=timeout, verify=False)
            resp.raise_for_status()
            return resp.content
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise SystemExit(f"下载失败 {url}: {last}")


def pick_wheel(base: str, name: str) -> str:
    data = requests.get(base.format(name), timeout=30, verify=False).json()

    def rank(filename: str) -> int:
        fn = filename.lower()
        if "cp312" in fn and "win_amd64" in fn:
            return 0
        if fn.endswith("py3-none-any.whl"):
            return 1
        if fn.endswith("py2.py3-none-any.whl"):
            return 2
        return 9

    wheels = [f for f in data["urls"] if f["filename"].endswith(".whl")]
    wheels.sort(key=lambda f: rank(f["filename"]))
    if not wheels or rank(wheels[0]["filename"]) == 9:
        raise SystemExit(f"{name}: 找不到适用于 Windows/CPython 3.12 的 wheel")
    return wheels[0]["url"]


def build_runtime(mirror: str, py_mirror: str = "org") -> None:
    if (PY_DIR / "python.exe").exists():
        print(f"已存在 {PY_DIR}，跳过下载（--force 可重建）")
    else:
        print(f"下载 Python {PY_VERSION} 嵌入式包…")
        PY_DIR.mkdir(parents=True, exist_ok=True)
        zipfile.ZipFile(io.BytesIO(http_get(PY_URLS[py_mirror], 300))).extractall(PY_DIR)

    SITE.mkdir(parents=True, exist_ok=True)
    pth = next(PY_DIR.glob("python*._pth"))
    text = pth.read_text(encoding="utf-8").replace("#import site", "import site")
    for entry in ("../site-packages", "../../src"):
        if entry not in text:
            text += f"\n{entry}\n"
    pth.write_text(text, encoding="utf-8")

    print("解析依赖…")
    base = MIRRORS[mirror]
    with ThreadPoolExecutor(6) as pool:
        urls = dict(zip(PKGS, pool.map(lambda p: pick_wheel(base, p), PKGS)))
    print("下载依赖…")
    with ThreadPoolExecutor(6) as pool:
        blobs = dict(zip(PKGS, pool.map(lambda p: http_get(urls[p]), PKGS)))
    for name, blob in blobs.items():
        print("  解包", name)
        zipfile.ZipFile(io.BytesIO(blob)).extractall(SITE)

    (ROOT / "启动网页.bat").write_text(LAUNCH_BAT, encoding="utf-8")
    (ROOT / "登录网易云.bat").write_text(LOGIN_BAT, encoding="utf-8")
    print("运行时就绪：", PY_DIR)


def build_zip() -> Path:
    RELEASE.mkdir(exist_ok=True)
    target = RELEASE / "netease-sorter-portable-win64.zip"
    skip = {".git", ".github", "data", "release", "build", "__pycache__"}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if set(rel.parts) & skip or path.suffix in {".pyc", ".spec"}:
                continue
            zf.write(path, rel.as_posix())
    print(f"便携包：{target}（{target.stat().st_size / 1048576:.1f} MB）")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="构建免安装运行时")
    parser.add_argument("--mirror", choices=sorted(MIRRORS), default="tuna")
    parser.add_argument("--py-mirror", choices=sorted(PY_URLS), default="org")
    parser.add_argument("--zip", action="store_true", help="同时打出 release/ 里的便携包")
    parser.add_argument("--force", action="store_true", help="删除旧 runtime 重新构建")
    args = parser.parse_args()

    if args.force and RUNTIME.exists():
        shutil.rmtree(RUNTIME)
    build_runtime(args.mirror, args.py_mirror)
    if args.zip:
        build_zip()
    return 0


if __name__ == "__main__":
    sys.exit(main())
