"""用 Edge 的调试端口取登录态。

为什么不用你平时的 Edge 配置：Chrome 136 起，``--remote-debugging-port`` 在**默认**
user-data-dir 上会被直接忽略（Edge 156 同样如此），实测端口根本不会开。
所以这里用一个**工具专用的配置目录**（默认 ``data/edge-profile``）：
- 不碰你日常浏览器的配置，也不需要关掉它；
- 第一次在里面扫码登录一次，Cookie 就存在这个目录里，以后直接可用；
- 浏览器自己知道明文，外部读文件才受 App-Bound Encryption 限制。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

import requests

EDGE_PATHS = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
)

LOGIN_URL = "https://music.163.com/#/login"
COOKIE_DOMAIN = "https://music.163.com/"


class BrowserError(RuntimeError):
    pass


def find_edge() -> str:
    for path in EDGE_PATHS:
        if Path(path).exists():
            return path
    raise BrowserError("没找到 msedge.exe，确认装的是 Microsoft Edge")


def launch(port: int, user_data_dir: str, url: str = LOGIN_URL,
           headless: bool = False) -> subprocess.Popen:
    args = [
        find_edge(),
        f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={user_data_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-mode",
        url,
    ]
    if headless:
        args.append("--headless=new")
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _targets(port: int) -> list[dict[str, Any]]:
    try:
        resp = requests.get(f"http://127.0.0.1:{port}/json/list", timeout=2)
        data = resp.json()
        return data if isinstance(data, list) else []
    except (requests.RequestException, ValueError):
        return []


def wait_target(port: int, timeout: float = 40) -> dict[str, Any]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        pages = [t for t in _targets(port) if t.get("webSocketDebuggerUrl")]
        pages.sort(key=lambda t: 0 if "music.163.com" in (t.get("url") or "") else 1)
        if pages:
            return pages[0]
        time.sleep(0.5)
    raise BrowserError(f"调试端口 {port} 没起来；换个端口试试（--port 9334）")


def _cookies_via_cdp(ws_url: str) -> dict[str, str]:
    try:
        from websockets.sync.client import connect
    except ImportError as exc:  # pragma: no cover
        raise BrowserError("需要 websockets：pip install \"netease-playlist-sorter[edge]\"") from exc

    with connect(ws_url, max_size=None, open_timeout=10) as ws:
        counter = 0

        def call(method: str, params: dict | None = None) -> dict:
            nonlocal counter
            counter += 1
            ws.send(json.dumps({"id": counter, "method": method, "params": params or {}}))
            while True:
                message = json.loads(ws.recv(timeout=20))
                if message.get("id") != counter:
                    continue  # 事件帧
                if "error" in message:
                    raise BrowserError(f"CDP 错误: {message['error']}")
                return message.get("result") or {}

        call("Network.enable")
        result = call("Network.getCookies", {"urls": [COOKIE_DOMAIN]})
        return {c["name"]: c["value"] for c in result.get("cookies") or []}


def _kill_tree(pid: int) -> None:
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)],
                   capture_output=True, text=True, errors="ignore")


def capture(
    port: int = 9333,
    wait: int = 180,
    profile_dir: str | Path | None = None,
    keep_open: bool = False,
    log: Callable[[str], None] = print,
) -> dict[str, str]:
    """打开专用配置的 Edge，等你在里面登录，然后读走 Cookie。"""
    profile = Path(profile_dir) if profile_dir else Path("data") / "edge-profile"
    profile = profile.resolve()  # Edge 不认相对路径，会直接起不来
    profile.mkdir(parents=True, exist_ok=True)

    log(f"启动 Edge（专用配置：{profile}）")
    log("如果窗口里显示的是登录框，用网易云 App 扫码即可；登录一次以后就不用再登。")
    proc = launch(port, str(profile))
    try:
        target = wait_target(port)
        ws_url = target["webSocketDebuggerUrl"]
        log(f"已连上浏览器，最多等 {wait} 秒…")
        deadline = time.time() + wait
        while time.time() < deadline:
            try:
                cookies = _cookies_via_cdp(ws_url)
            except BrowserError:
                raise
            except Exception:
                time.sleep(2)
                continue
            if cookies.get("MUSIC_U"):
                return cookies
            time.sleep(3)
        raise BrowserError("没等到 MUSIC_U：确认在那个 Edge 窗口里登录了 music.163.com")
    finally:
        if not keep_open:
            _kill_tree(proc.pid)
