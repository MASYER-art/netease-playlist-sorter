"""网易云网页版接口的最小封装。

这里用的是网页端自带的私有接口（``/api/*``），**不是**官方开放平台。
接口随时可能变动，字段对不上时先抓包核对，再去改 ``api.py``。
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from typing import Any, Iterable, Iterator, Sequence

import requests

BASE = "https://music.163.com"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)

# /api/song/detail 一次能带的 id 数量
BATCH_SIZE = 200


class ApiError(RuntimeError):
    """接口返回了非预期内容。"""


@dataclass
class Song:
    """一首歌，只保留分类需要的字段。"""

    id: int
    name: str = ""
    artists: str = ""
    album: str = ""
    lyric: str = ""
    pure: bool = False

    @property
    def meta(self) -> str:
        return f"{self.name} {self.artists} {self.album}"


def chunks(seq: Sequence[int], size: int) -> Iterator[Sequence[int]]:
    for i in range(0, len(seq), size):
        yield seq[i : i + size]


def parse_cookie(text: str) -> dict[str, str]:
    """把 ``a=1; b=2`` 或单个 ``MUSIC_U`` 的值解析成字典。"""
    text = (text or "").strip()
    if "=" not in text:
        return {"MUSIC_U": text}
    jar: dict[str, str] = {}
    for part in text.split(";"):
        if "=" in part:
            key, value = part.strip().split("=", 1)
            jar[key] = value
    return jar


def track_ids_of(playlist: dict[str, Any]) -> list[int]:
    """从歌单详情里取去重后的曲目 id 列表。"""
    ids: list[int] = []
    seen: set[int] = set()
    for item in playlist.get("trackIds") or []:
        tid = item.get("id") if isinstance(item, dict) else item
        if tid and tid not in seen:
            seen.add(tid)
            ids.append(int(tid))
    return ids


class Client:
    """带重试的接口客户端。"""

    def __init__(
        self,
        cookies: dict[str, str] | None = None,
        timeout: int = 20,
        retries: int = 3,
        polite_delay: float = 0.0,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.polite_delay = polite_delay
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": UA,
                "Referer": BASE + "/",
                "Origin": BASE,
                "Accept": "*/*",
            }
        )
        if cookies:
            self.session.cookies.update(cookies)

    # ---------------------------------------------------------------- 基础
    @property
    def csrf(self) -> str:
        return self.session.cookies.get("__csrf", "")

    def request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        url = path if path.startswith("http") else BASE + path
        last: Exception | None = None
        for attempt in range(self.retries):
            try:
                resp = self.session.request(method, url, timeout=self.timeout, **kwargs)
                data = resp.json()
                if isinstance(data, dict) and data.get("code") in (400, 403, 405, 429):
                    raise ApiError(f"{path} 返回 code={data.get('code')}: {data}")
                return data
            except Exception as exc:  # noqa: BLE001 - 统一重试
                last = exc
                time.sleep(0.8 * (attempt + 1) + random.random() * 0.4)
        raise ApiError(f"请求失败: {path} -> {last}")

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(self, path: str, **data: Any) -> dict[str, Any]:
        return self.request("POST", path, data=data)

    # ---------------------------------------------------------------- 账号
    def account(self) -> dict[str, Any]:
        data = self.get("/api/nuser/account/get")
        if not (data.get("account") or {}).get("id"):
            raise ApiError(f"登录态无效: {str(data)[:200]}")
        return data

    def uid(self) -> int:
        return int(self.account()["account"]["id"])

    def user_playlists(self, uid: int) -> list[dict[str, Any]]:
        data = self.get("/api/user/playlist", uid=uid, limit=1000, offset=0)
        return data.get("playlist") or []

    def liked_playlist(self, uid: int) -> dict[str, Any]:
        """返回「我喜欢的音乐」歌单（specialType == 5）。"""
        for item in self.user_playlists(uid):
            if item.get("specialType") == 5:
                return item
        raise ApiError("没找到「我喜欢的音乐」，请确认 Cookie 属于当前账号")

    # ---------------------------------------------------------------- 歌单
    def playlist(self, pid: int) -> dict[str, Any]:
        data = self.get("/api/v6/playlist/detail", id=pid, n=1000, s=0)
        pl = data.get("playlist") or data.get("result")
        if not pl:
            raise ApiError(f"歌单 {pid} 读取失败: {str(data)[:200]}")
        return pl

    def track_ids(self, pid: int) -> list[int]:
        return track_ids_of(self.playlist(pid))

    def songs(self, ids: Sequence[int]) -> list[Song]:
        out: list[Song] = []
        for part in chunks(ids, BATCH_SIZE):
            data = self.get("/api/song/detail", ids=json.dumps(list(part)))
            for item in data.get("songs") or []:
                artists = item.get("artists") or item.get("ar") or []
                album = item.get("album") or item.get("al") or {}
                out.append(
                    Song(
                        id=int(item["id"]),
                        name=item.get("name") or "",
                        artists=" / ".join(a.get("name", "") for a in artists),
                        album=album.get("name", "") or "",
                    )
                )
            time.sleep(self.polite_delay)
        return out

    def lyric(self, sid: int) -> tuple[str, bool]:
        """返回 (歌词文本, 是否纯音乐)。``pureMusic`` 是网易云自己打的标记。"""
        try:
            data = self.get("/api/song/lyric", id=sid, lv=-1, kv=-1, tv=-1)
        except ApiError:
            return "", False
        text = ((data.get("lrc") or {}).get("lyric") or "")
        return text, bool(data.get("pureMusic"))

    # ---------------------------------------------------------------- 写入
    def create_playlist(self, name: str, private: bool = True) -> int:
        data = self.post(
            "/api/playlist/create",
            name=name,
            privacy="10" if private else "0",
            type="NORMAL",
            csrf_token=self.csrf,
        )
        pid = (data.get("playlist") or data.get("result") or {}).get("id")
        if not pid:
            raise ApiError(f"创建歌单失败: {str(data)[:300]}")
        return int(pid)

    def add_tracks(self, pid: int, ids: Sequence[int], attempts: int = 3) -> None:
        """把一批歌加进歌单；失败会退避重试，仍然失败就抛 ``ApiError``。

        遇到明确的限流信号（400/403）不再重试，直接抛出，避免越刷越糟。
        """
        last: Exception | None = None
        for attempt in range(attempts):
            try:
                data = self.post(
                    "/api/playlist/manipulate/tracks",
                    pid=pid,
                    trackIds=json.dumps(list(ids)),
                    op="add",
                    csrf_token=self.csrf,
                )
            except ApiError as exc:
                last = exc
            else:
                if data.get("status") == 200 or data.get("code") == 200:
                    return
                last = ApiError(f"写入失败: {str(data)[:200]}")
                if data.get("code") in (400, 403) or data.get("status") in (400, 403):
                    break
            time.sleep(2 ** attempt)
        raise ApiError(f"写入 {len(ids)} 首失败（已重试 {attempts} 次）: {last}")


def qr_login(on_qr) -> dict[str, str]:
    """扫码登录，返回 cookie。``on_qr`` 收到登录链接，负责把二维码展示给用户。

    注意：部分账号会被风控拦下（``code 8821``），此时只能改用浏览器 Cookie。
    """
    client = Client()
    data = client.post("/api/login/qrcode/unikey", type=1)
    if data.get("code") != 200:
        raise ApiError(f"获取二维码失败: {data}")
    key = data["unikey"]
    url = f"https://music.163.com/login?codekey={key}"
    on_qr(url)

    deadline = time.time() + 180
    while time.time() < deadline:
        info = client.post("/api/login/qrcode/client/login", key=key, type=1)
        code = info.get("code")
        if code == 800:
            raise ApiError("二维码已过期")
        if code in (801, 802):
            time.sleep(2)
            continue
        if code == 803:
            jar = {c.name: c.value for c in client.session.cookies}
            for part in (info.get("cookie") or "").split(";"):
                if "=" in part:
                    k, v = part.strip().split("=", 1)
                    jar[k] = v
            return jar
        raise ApiError(f"登录状态异常: {info}")
    raise ApiError("等待扫码超时")
