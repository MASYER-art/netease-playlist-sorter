"""命令行入口。"""

from __future__ import annotations

import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .api import ApiError, Client, Song, parse_cookie, qr_login
from .browser import BrowserError, capture
from .classify import CATEGORIES, OTHER, classify, load_overrides
from .export import group_ids, read_preview, write_console_scripts, write_preview
from .genres import detect as detect_genres
from .genres import join as join_genres
from .server import serve
from .target import TargetError, resolve
from .store import (
    load_json,
    load_library,
    load_session,
    save_json,
    save_library,
    save_session,
)

WRITE_BATCH = 100  # 网易云单次「添加到歌单」的舒适区间


# ---------------------------------------------------------------- 辅助
def _data(args: argparse.Namespace, name: str) -> Path:
    return Path(args.data_dir) / name


def _client(args: argparse.Namespace) -> Client:
    session = load_session(_data(args, "session.json"))
    if not session:
        raise SystemExit("还没有登录态：先运行 `netease-sorter login --cookie ...`")
    return Client(session["cookies"])


def parse_playlist_id(value: str) -> int:
    match = re.search(r"[?&#]id=(\d+)", value) or re.fullmatch(r"(\d+)", value.strip())
    if not match:
        raise SystemExit(f"解析不出歌单 id: {value}")
    return int(match.group(1))


def _show_qr(url: str) -> None:
    print("登录链接:", url)
    try:
        import qrcode  # 可选依赖
    except ImportError:
        print("（没装 qrcode，无法生成二维码图片，可把链接转成二维码再扫）")
        return
    path = Path("data") / "login_qr.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    qrcode.make(url).resize((420, 420)).save(path)
    print("二维码已保存:", path)


# ---------------------------------------------------------------- login
def cmd_login(args: argparse.Namespace) -> int:
    if args.from_edge:
        try:
            jar = capture(
                port=args.port,
                wait=args.wait,
                profile_dir=args.profile or (Path(args.data_dir) / "edge-profile"),
                keep_open=args.keep_open,
            )
        except BrowserError as exc:
            raise SystemExit(f"从 Edge 取登录态失败: {exc}") from exc
    else:
        cookie_text = args.cookie
        if not cookie_text and args.cookie_file:
            cookie_text = Path(args.cookie_file).read_text(encoding="utf-8").strip()
        if not cookie_text:
            for candidate in (Path("music_u.txt"), Path(args.data_dir) / "music_u.txt"):
                if candidate.exists():
                    cookie_text = candidate.read_text(encoding="utf-8").strip()
                    print("已读取", candidate)
                    break

        if cookie_text:
            jar = parse_cookie(cookie_text)
        elif args.qr:
            jar = qr_login(_show_qr)
        else:
            raise SystemExit(
                "需要登录态：用 --from-edge 从浏览器取，或用 --cookie / --cookie-file 提供 MUSIC_U，"
                "或加 --qr 扫码（部分账号会被风控拦住）"
            )

    client = Client(jar)
    account = client.account()
    uid = int(account["account"]["id"])
    nickname = (account.get("profile") or {}).get("nickname", "")
    save_session(_data(args, "session.json"), jar, uid, nickname)
    print(f"登录成功: {nickname} (uid={uid})")
    return 0


# ---------------------------------------------------------------- fetch
def cmd_fetch(args: argparse.Namespace) -> int:
    if args.playlist:
        client = Client()
        pid = parse_playlist_id(args.playlist)
        info = client.playlist(pid)
        name = info.get("name", "")
    else:
        client = _client(args)
        session = load_session(_data(args, "session.json")) or {}
        uid = session.get("uid") or client.uid()
        liked = client.liked_playlist(int(uid))
        pid, name = int(liked["id"]), liked.get("name", "")

    ids = client.track_ids(pid)
    if args.limit:
        ids = ids[: args.limit]
    print(f"《{name}》 id={pid}，曲目 {len(ids)} 首")

    songs = client.songs(ids)
    print(f"拿到详情 {len(songs)} 首")

    cached: dict[int, Song] = {}
    if not args.refresh:
        for song in load_library(_data(args, "library.json")):
            if song.lyric:
                cached[song.id] = song

    todo = [s for s in songs if s.id not in cached]
    print(f"需要拉歌词 {len(todo)} 首（缓存命中 {len(songs) - len(todo)}）")

    def work(song: Song) -> tuple[int, str, bool]:
        worker = Client()
        text, pure = worker.lyric(song.id)
        return song.id, text, pure

    done = 0
    lyrics: dict[int, tuple[str, bool]] = {}
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(work, song) for song in todo]
        for future in as_completed(futures):
            sid, text, pure = future.result()
            lyrics[sid] = (text, pure)
            done += 1
            if done % 200 == 0:
                print(f"  歌词 {done}/{len(todo)}", flush=True)

    for song in songs:
        if song.id in cached:
            song.lyric, song.pure = cached[song.id].lyric, cached[song.id].pure
        elif song.id in lyrics:
            song.lyric, song.pure = lyrics[song.id]

    save_library(_data(args, "library.json"), songs)
    save_json(
        _data(args, "meta.json"),
        {"id": pid, "name": name, "count": len(songs), "updated": time.strftime("%Y-%m-%d %H:%M")},
    )
    print(f"已保存 {len(songs)} 首到 {_data(args, 'library.json')}")
    return 0


# ---------------------------------------------------------------- classify
def cmd_classify(args: argparse.Namespace) -> int:
    songs = load_library(_data(args, "library.json"))
    if not songs:
        raise SystemExit("没有歌曲数据，先运行 fetch")

    overrides: dict[int, str] = {}
    path = Path(args.overrides) if args.overrides else _data(args, "overrides.csv")
    if path.exists():
        overrides = load_overrides(str(path))
        print(f"已应用人工修正 {len(overrides)} 条: {path}")

    rows = []
    records = []
    counter: dict[str, int] = {}
    genre_counter: dict[str, int] = {}
    review = 0
    for song in songs:
        if song.id in overrides:
            category, confidence, reason = overrides[song.id], "manual", "overrides.csv"
        else:
            result = classify(song)
            category, confidence, reason = result.category, result.confidence, result.reason
        genres = detect_genres(song, lang=category)
        for genre in genres:
            genre_counter[genre] = genre_counter.get(genre, 0) + 1
        counter[category] = counter.get(category, 0) + 1
        review += confidence in ("low", "mid")
        rows.append(
            [song.id, song.name, song.artists, song.album, category,
             join_genres(genres), confidence, reason]
        )
        records.append(
            {
                "id": song.id,
                "name": song.name,
                "artists": song.artists,
                "album": song.album,
                "lang": category,
                "genres": genres,
                "confidence": confidence,
                "reason": reason,
            }
        )

    out = _data(args, "preview.csv")
    write_preview(out, rows)
    save_json(_data(args, "classified.json"), records)
    print(f"共 {len(rows)} 首 -> {out}")
    for category in (*CATEGORIES, OTHER):
        if counter.get(category):
            print(f"  {category}: {counter[category]}")
    top = sorted(genre_counter.items(), key=lambda kv: kv[1], reverse=True)[:8]
    print("  曲风 Top:", "、".join(f"{g} {n}" for g, n in top))
    print(f"置信度 low/mid（建议人工复核）: {review}")
    return 0


# ---------------------------------------------------------------- export
def cmd_export(args: argparse.Namespace) -> int:
    rows = read_preview(_data(args, "preview.csv"))
    plan = group_ids(rows, CATEGORIES)
    written = write_console_scripts(
        plan,
        Path(args.out_dir) if args.out_dir else Path(args.data_dir),
        playlist_prefix=args.playlist_prefix,
        file_prefix=args.file_prefix,
    )
    for path in written:
        print("已生成", path)
    if not written:
        raise SystemExit("preview.csv 里没有可分组的歌曲")
    return 0


# ---------------------------------------------------------------- serve
def cmd_serve(args: argparse.Namespace) -> int:
    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    if not (data_dir / "classified.json").exists():
        print("还没有数据：打开页面后在上方粘贴歌单链接即可加载")
    serve(data_dir, port=args.port, open_browser=not args.no_open)
    return 0


# ---------------------------------------------------------------- create（API 模式）
def cmd_create(args: argparse.Namespace) -> int:
    client = _client(args)
    uid = int((load_session(_data(args, "session.json")) or {}).get("uid") or client.uid())
    rows = read_preview(_data(args, "preview.csv"))
    plan = group_ids(rows, CATEGORIES)

    categories = list(CATEGORIES)
    if args.only:
        wanted = [c.strip() for c in args.only.replace("，", ",").split(",") if c.strip()]
        unknown = [c for c in wanted if c not in CATEGORIES]
        if unknown:
            raise SystemExit(f"未知分类: {'、'.join(unknown)}（可选：{'、'.join(CATEGORIES)}）")
        categories = [c for c in CATEGORIES if c in wanted]
    categories = [c for c in categories if plan.get(c)]
    if not categories:
        raise SystemExit("没有要写入的歌曲")
    if args.name and len(categories) > 1:
        raise SystemExit("--name 只能配合单个分类使用：先用 --only 选一个分类")

    playlists = client.user_playlists(uid)
    state = load_json(_data(args, "state.json"), {"playlists": {}, "done": {}}) or {}
    state.setdefault("playlists", {})
    state.setdefault("done", {})

    for category in categories:
        ids = plan[category]
        if args.name and len(categories) == 1:
            name = args.name.strip()
        else:
            name = args.playlist_prefix + category

        try:
            target = resolve(name, playlists, uid,
                             known_id=state["playlists"].get(name), append=args.append)
        except TargetError as exc:
            raise SystemExit(f"[{category}] {exc}") from exc

        where = f"复用 id={target.playlist_id}" if target.action == "reuse" else "新建"
        print(f"{category}: {len(ids)} 首 -> 《{name}》 [{where}]")
        if args.dry_run:
            continue

        pid = target.playlist_id
        if pid is None:
            pid = client.create_playlist(name, private=not args.public)
            playlists.append({"id": pid, "name": name, "userId": uid, "trackCount": 0})
            print(f"  已创建 id={pid}")
            time.sleep(1)

        state["playlists"][name] = pid
        save_json(_data(args, "state.json"), state)

        done_ids = set(state["done"].get(str(pid), []))
        todo = [sid for sid in ids if sid not in done_ids]
        if not todo:
            print("  没有新增曲目")
        for i in range(0, len(todo), WRITE_BATCH):
            part = todo[i : i + WRITE_BATCH]
            client.add_tracks(pid, part)  # 失败会抛 ApiError，已成功的批次已落盘
            state["done"].setdefault(str(pid), []).extend(part)
            save_json(_data(args, "state.json"), state)
            print(f"  第 {i // WRITE_BATCH + 1} 批 +{len(part)}")
            time.sleep(args.delay)

        info = client.playlist(pid)
        have = int(info.get("trackCount") or 0)
        print(f"  核对：歌单现有 {have} 首，本次目标 {len(ids)} 首")
        print(f"  链接：https://music.163.com/playlist?id={pid}")
    print("完成")
    return 0


# ---------------------------------------------------------------- all
def cmd_all(args: argparse.Namespace) -> int:
    cmd_fetch(args)
    cmd_classify(args)
    return cmd_export(args)


# ---------------------------------------------------------------- 参数
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="netease-sorter",
        description="把网易云歌单 / 我喜欢的音乐按语种拆成 中文 / 英文 / 日语 / 纯音乐",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data-dir", default="data", help="数据目录，默认 data/")

    p = sub.add_parser("login", help="保存登录态")
    common(p)
    p.add_argument("--cookie", help="MUSIC_U 的值，或整段 cookie")
    p.add_argument("--cookie-file", help="从文件读取 cookie")
    p.add_argument("--qr", action="store_true", help="扫码登录（可能被风控拦截）")
    p.add_argument("--from-edge", action="store_true", help="打开专用 Edge 窗口登录后自动取 Cookie")
    p.add_argument("--keep-open", action="store_true", help="取完 Cookie 不关闭那个 Edge 窗口")
    p.add_argument("--profile", help="专用配置目录，默认 data/edge-profile")
    p.add_argument("--port", type=int, default=9333, help="调试端口，默认 9333")
    p.add_argument("--wait", type=int, default=180, help="等待登录的秒数，默认 180")
    p.set_defaults(func=cmd_login)

    p = sub.add_parser("fetch", help="抓取歌单曲目与歌词")
    common(p)
    p.add_argument("--liked", action="store_true", help="抓「我喜欢的音乐」（需要登录）")
    p.add_argument("--playlist", help="公开歌单链接或 id（不需要登录）")
    p.add_argument("--workers", type=int, default=8, help="歌词并发数，默认 8")
    p.add_argument("--refresh", action="store_true", help="忽略缓存，重新拉歌词")
    p.add_argument("--limit", type=int, help="只取前 N 首，便于试跑")
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("classify", help="分类并输出 preview.csv")
    common(p)
    p.add_argument("--overrides", help="人工修正表，默认 data/overrides.csv")
    p.set_defaults(func=cmd_classify)

    p = sub.add_parser("export", help="生成可粘贴到浏览器 Console 的脚本")
    common(p)
    p.add_argument("--out-dir", help="输出目录，默认与 data-dir 相同")
    p.add_argument("--playlist-prefix", default="我的喜欢 · ")
    p.add_argument("--file-prefix", default="加歌单")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("serve", help="启动本地网页，按语种/曲风筛选")
    common(p)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("create", help="用登录态直接建歌单并写入")
    common(p)
    p.add_argument("--playlist-prefix", default="我的喜欢 · ", help="歌单名前缀")
    p.add_argument("--only", help="只写这些分类，逗号分隔，如 中文,日语")
    p.add_argument("--name", help="精确指定歌单名（只能配合 --only 单个分类）")
    p.add_argument("--append", action="store_true", help="允许追加到已存在的非空同名歌单")
    p.add_argument("--public", action="store_true", help="建成公开歌单（默认私密）")
    p.add_argument("--delay", type=float, default=1.2, help="每批之间的间隔秒数")
    p.add_argument("--dry-run", action="store_true", help="只打印计划，不改动账号")
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("all", help="fetch + classify + export")
    common(p)
    p.add_argument("--liked", action="store_true")
    p.add_argument("--playlist")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--limit", type=int)
    p.add_argument("--overrides")
    p.add_argument("--out-dir")
    p.add_argument("--playlist-prefix", default="我的喜欢 · ")
    p.add_argument("--file-prefix", default="加歌单")
    p.set_defaults(func=cmd_all)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args) or 0
    except ApiError as exc:
        print(f"接口错误: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已中断", file=sys.stderr)
        return 130
