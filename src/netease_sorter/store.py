"""本地文件读写：登录态、歌曲缓存、写入进度。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .api import Song


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def song_to_dict(song: Song) -> dict[str, Any]:
    return {
        "id": song.id,
        "name": song.name,
        "artists": song.artists,
        "album": song.album,
        "lyric": song.lyric,
        "pure": song.pure,
    }


def dict_to_song(data: dict[str, Any]) -> Song:
    return Song(
        id=int(data["id"]),
        name=data.get("name", ""),
        artists=data.get("artists", ""),
        album=data.get("album", ""),
        lyric=data.get("lyric", ""),
        pure=bool(data.get("pure", False)),
    )


def save_library(path: Path, songs: list[Song]) -> None:
    save_json(path, [song_to_dict(s) for s in songs])


def load_library(path: Path) -> list[Song]:
    return [dict_to_song(item) for item in load_json(path, []) or []]


def save_session(path: Path, cookies: dict[str, str], uid: int, nickname: str = "") -> None:
    save_json(path, {"cookies": cookies, "uid": uid, "nickname": nickname})


def load_session(path: Path) -> dict[str, Any] | None:
    data = load_json(path)
    if not data or "cookies" not in data:
        return None
    return data
