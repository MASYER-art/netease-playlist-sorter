"""本地 Web 界面：加载歌单、按语种/曲风筛选、生成写入脚本。"""

from __future__ import annotations

import json
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .api import ApiError, Client
from .classify import load_overrides
from .export import console_script
from .pipeline import build_records, load_playlist, save_outputs
from .store import load_json, load_session, save_json
from .target import TargetError, resolve

WEB_DIR = Path(__file__).parent / "web"
STATIC = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/index.html": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}

JOBS: dict[str, dict[str, Any]] = {}
JOB_LOCK = threading.Lock()

WRITE_BATCH = 100
WRITE_DELAY = 1.2


def build_payload(data_dir: Path) -> dict[str, Any]:
    records = load_json(data_dir / "classified.json")
    meta = load_json(data_dir / "meta.json", {}) or {}
    session = load_session(data_dir / "session.json")
    account = {"uid": session.get("uid"), "nickname": session.get("nickname", "")} if session else None
    if records is None:
        return {
            "error": "还没有数据，在上方粘贴歌单链接加载，或用命令行 fetch + classify",
            "songs": [],
            "account": account,
        }
    return {
        "playlist": meta,
        "songs": records,
        "languages": ["中文", "英文", "日语", "纯音乐", "其他"],
        "account": account,
    }


def _run_create(job_id: str, data_dir: Path, ids: list[int], name: str, append: bool) -> None:
    """直接写入账号：建歌单 / 复用 / 分批写 / 核对。"""
    job = JOBS[job_id]
    try:
        session = load_session(data_dir / "session.json")
        if not session:
            raise RuntimeError("还没有登录态：先在命令行运行 netease-sorter login --from-edge")

        client = Client(session["cookies"])
        uid = int(session.get("uid") or client.uid())
        playlists = client.user_playlists(uid)

        state = load_json(data_dir / "state.json", {"playlists": {}, "done": {}}) or {}
        state.setdefault("playlists", {})
        state.setdefault("done", {})

        try:
            target = resolve(name, playlists, uid, known_id=state["playlists"].get(name), append=append)
        except TargetError as exc:
            raise RuntimeError(str(exc)) from exc

        pid = target.playlist_id
        if pid is None:
            job.update(message=f"创建《{name}》…")
            pid = client.create_playlist(name)
            time.sleep(1)
        state["playlists"][name] = pid
        save_json(data_dir / "state.json", state)

        done_ids = set(state["done"].get(str(pid), []))
        todo = [i for i in ids if i not in done_ids]
        total = len(todo)
        job.update(progress=0, total=max(total, 1), message=f"写入《{name}》 0/{total}")

        for index in range(0, total, WRITE_BATCH):
            part = todo[index : index + WRITE_BATCH]
            client.add_tracks(pid, part)
            state["done"].setdefault(str(pid), []).extend(part)
            save_json(data_dir / "state.json", state)
            job.update(progress=index + len(part), message=f"写入《{name}》 {index + len(part)}/{total}")
            time.sleep(WRITE_DELAY)

        info = client.playlist(pid)
        count = int(info.get("trackCount") or 0)
        job.update(
            status="done",
            progress=1,
            total=1,
            message=f"完成：{name} 现有 {count} 首",
            result={
                "id": pid,
                "name": name,
                "count": count,
                "written": total,
                "url": f"https://music.163.com/playlist?id={pid}",
            },
        )
    except (ApiError, RuntimeError) as exc:
        job.update(status="error", message=str(exc))


def _run_job(job_id: str, data_dir: Path, ref: str, workers: int) -> None:
    job = JOBS[job_id]

    def progress(done: int, total: int, message: str) -> None:
        job.update(progress=done, total=max(total, 1), message=message)

    try:
        info, songs = load_playlist(ref, workers=workers, progress=progress)
        job.update(progress=0, total=1, message="分类中…")
        override_file = data_dir / "overrides.csv"
        overrides = load_overrides(str(override_file)) if override_file.exists() else {}
        records = build_records(songs, overrides)
        meta = {
            "id": info.get("id"),
            "name": info.get("name") or str(ref),
            "count": len(records),
            "updated": time.strftime("%Y-%m-%d %H:%M"),
        }
        save_outputs(data_dir, songs, records, meta)
        job.update(status="done", progress=1, total=1, message=f"完成，共 {len(records)} 首")
    except Exception as exc:  # noqa: BLE001 - 任务里的错误要回传给前端
        job.update(status="error", message=str(exc))


class Handler(BaseHTTPRequestHandler):
    data_dir: Path = Path("data")
    server_version = "netease-sorter"

    # ---------------------------------------------------------- 工具
    def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8", status)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw or b"{}")

    def log_message(self, fmt: str, *args: Any) -> None:
        print(f"[web] {fmt % args}")

    # ---------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/api/data":
            self._json(build_payload(self.data_dir))
            return
        if parsed.path == "/api/job":
            job_id = (parse_qs(parsed.query).get("id") or [""])[0]
            job = JOBS.get(job_id)
            if not job:
                self._json({"error": "没有这个任务"}, 404)
                return
            self._json({k: v for k, v in job.items() if k != "started"})
            return

        entry = STATIC.get(parsed.path)
        if not entry:
            self._send(b"not found", "text/plain; charset=utf-8", 404)
            return
        name, ctype = entry
        file = WEB_DIR / name
        if not file.exists():
            self._send(b"web assets missing", "text/plain; charset=utf-8", 500)
            return
        self._send(file.read_bytes(), ctype)

    # ---------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/load":
            self._handle_load()
            return
        if path == "/api/script":
            self._handle_script()
            return
        if path == "/api/create":
            self._handle_create()
            return
        self._send(b"not found", "text/plain; charset=utf-8", 404)

    def _handle_load(self) -> None:
        try:
            ref = str(self._body().get("playlist") or "").strip()
        except ValueError as exc:
            self._json({"error": f"参数错误: {exc}"}, 400)
            return
        if not ref:
            self._json({"error": "请填写歌单链接或 id"}, 400)
            return
        with JOB_LOCK:
            if any(job["status"] == "running" for job in JOBS.values()):
                self._json({"error": "上一个任务还没跑完，稍等一下"}, 409)
                return
            job_id = uuid.uuid4().hex[:8]
            JOBS[job_id] = {
                "status": "running", "progress": 0, "total": 1,
                "message": "准备中…", "started": time.time(),
            }
        threading.Thread(
            target=_run_job, args=(job_id, self.data_dir, ref, 8), daemon=True
        ).start()
        self._json({"job": job_id})

    def _handle_create(self) -> None:
        try:
            payload = self._body()
            ids = [int(i) for i in payload.get("ids") or []]
            name = (payload.get("name") or "").strip()[:40]
            append = bool(payload.get("append"))
        except (ValueError, TypeError) as exc:
            self._json({"error": f"参数错误: {exc}"}, 400)
            return
        if not ids:
            self._json({"error": "没有选中歌曲"}, 400)
            return
        if not name:
            self._json({"error": "请填歌单名"}, 400)
            return
        if not load_session(self.data_dir / "session.json"):
            self._json({"error": "还没有登录态：先在命令行运行 netease-sorter login --from-edge"}, 401)
            return
        with JOB_LOCK:
            if any(job["status"] == "running" for job in JOBS.values()):
                self._json({"error": "上一个任务还没跑完，稍等一下"}, 409)
                return
            job_id = uuid.uuid4().hex[:8]
            JOBS[job_id] = {
                "status": "running", "progress": 0, "total": len(ids),
                "message": f"准备写入《{name}》…", "started": time.time(),
            }
        threading.Thread(
            target=_run_create, args=(job_id, self.data_dir, ids, name, append), daemon=True
        ).start()
        self._json({"job": job_id})

    def _handle_script(self) -> None:
        try:
            payload = self._body()
            ids = [int(i) for i in payload.get("ids") or []]
            name = (payload.get("name") or "我的歌单").strip()[:40] or "我的歌单"
        except (ValueError, TypeError) as exc:
            self._json({"error": f"参数错误: {exc}"}, 400)
            return
        if not ids:
            self._json({"error": "没有选中歌曲"}, 400)
            return
        self._json({"script": console_script("自定义", ids, name), "count": len(ids)})


def serve(data_dir: Path, port: int = 8765, open_browser: bool = True) -> None:
    handler = type("BoundHandler", (Handler,), {"data_dir": data_dir})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"已启动: {url}  (Ctrl+C 退出)")
    if open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        httpd.server_close()
