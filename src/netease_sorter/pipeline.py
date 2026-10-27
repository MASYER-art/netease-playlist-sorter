"""抓取 + 分类的流水线，命令行和网页共用。"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .api import Client, Song, track_ids_of
from .classify import classify
from .export import write_preview
from .genres import detect as detect_genres
from .genres import join as join_genres
from .store import save_json, save_library

Progress = Callable[[int, int, str], None]


def _noop(done: int, total: int, message: str) -> None:
    pass


def parse_playlist_ref(value: str) -> int:
    """从链接或裸 id 里取歌单 id。"""
    match = re.search(r"[?&#]id=(\d+)", value or "") or re.fullmatch(r"\s*(\d+)\s*", value or "")
    if not match:
        raise ValueError(f"解析不出歌单 id：{value}")
    return int(match.group(1))


def _fill_lyrics(songs: Sequence[Song], workers: int, progress: Progress) -> None:
    todo = [s for s in songs if not s.lyric]
    if not todo:
        return
    done = 0

    def work(song: Song) -> tuple[Song, str, bool]:
        client = Client()
        text, pure = client.lyric(song.id)
        return song, text, pure

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(work, song) for song in todo]
        for future in as_completed(futures):
            song, text, pure = future.result()
            song.lyric, song.pure = text, pure
            done += 1
            if done % 50 == 0 or done == len(todo):
                progress(done, len(todo), f"拉取歌词 {done}/{len(todo)}")


def load_playlist(
    ref: str | int,
    workers: int = 8,
    progress: Progress = _noop,
    cookies: dict[str, str] | None = None,
) -> tuple[dict, list[Song]]:
    """抓一个公开歌单：返回 (歌单信息, 带歌词的歌曲列表)。"""
    pid = parse_playlist_ref(str(ref))
    client = Client(cookies)
    info = client.playlist(pid)
    ids = track_ids_of(info)
    name = info.get("name") or str(pid)
    progress(0, len(ids), f"《{name}》共 {len(ids)} 首，获取详情")
    songs = client.songs(ids)
    progress(len(ids), len(ids), f"详情就绪，开始拉歌词（{len(songs)} 首）")
    _fill_lyrics(songs, workers, progress)
    return info, songs


def build_records(
    songs: Iterable[Song],
    overrides: dict[int, str] | None = None,
) -> list[dict]:
    """语种 + 曲风一起算，产出网页用的记录。"""
    overrides = overrides or {}
    records: list[dict] = []
    for song in songs:
        if song.id in overrides:
            lang, confidence, reason = overrides[song.id], "manual", "overrides.csv"
        else:
            result = classify(song)
            lang, confidence, reason = result.category, result.confidence, result.reason
        genres = detect_genres(song, lang=lang)
        records.append(
            {
                "id": song.id,
                "name": song.name,
                "artists": song.artists,
                "album": song.album,
                "lang": lang,
                "genres": genres,
                "confidence": confidence,
                "reason": reason,
            }
        )
    return records


def preview_rows(records: Iterable[dict]) -> list[list]:
    return [
        [
            r["id"], r["name"], r["artists"], r["album"], r["lang"],
            join_genres(r["genres"]), r["confidence"], r["reason"],
        ]
        for r in records
    ]


def summarize(records: Sequence[dict]) -> tuple[dict[str, int], dict[str, int], int]:
    lang_counter: dict[str, int] = {}
    genre_counter: dict[str, int] = {}
    review = 0
    for record in records:
        lang_counter[record["lang"]] = lang_counter.get(record["lang"], 0) + 1
        for genre in record["genres"]:
            genre_counter[genre] = genre_counter.get(genre, 0) + 1
        review += record["confidence"] in ("low", "mid")
    return lang_counter, genre_counter, review


def save_outputs(
    data_dir: Path,
    songs: Sequence[Song],
    records: Sequence[dict],
    meta: dict,
) -> None:
    save_library(data_dir / "library.json", list(songs))
    save_json(data_dir / "classified.json", list(records))
    save_json(data_dir / "meta.json", meta)
    write_preview(data_dir / "preview.csv", preview_rows(records))
