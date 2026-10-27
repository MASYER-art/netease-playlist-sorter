"""输出：CSV 预览 + 可直接粘进浏览器 Console 的建歌单脚本。"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Mapping, Sequence

CSV_HEADER = ["id", "歌名", "歌手", "专辑", "语种", "曲风", "置信度", "依据"]

CONSOLE_TEMPLATE = """// 【__LABEL__】__COUNT__ 首
// 用法：在 music.163.com 已登录的页面按 F12 -> Console，整段粘贴，回车。
// 首次粘贴浏览器会要求输入 allow pasting，按提示输入即可。
(async () => {
  const NAME = "__NAME__";
  const IDS = __IDS__;
  const csrf = (document.cookie.match(/__csrf=([^;]+)/) || [])[1] || "";
  const post = (url, body) => fetch(url, {
    method: "POST", credentials: "include",
    headers: {"Content-Type": "application/x-www-form-urlencoded"},
    body: new URLSearchParams(body)
  }).then(r => r.json());
  const get = url => fetch(url, {credentials: "include"}).then(r => r.json());

  let pid = null, have = 0;
  try {
    const acc = await get("/api/nuser/account/get");
    const uid = (acc.account || {}).id;
    const pl = await get("/api/user/playlist?uid=" + uid + "&limit=1000&offset=0");
    const hit = ((pl.playlist) || []).find(p => p.name === NAME);
    if (hit) { pid = hit.id; have = hit.trackCount || 0; }
  } catch (e) { console.log("查询已有歌单失败:", e); }

  if (pid) {
    console.log("已存在《" + NAME + "》，现有 " + have + " 首");
    if (have > 0 && !confirm("《" + NAME + "》已存在且不为空，继续会重复添加。继续吗？")) return;
  } else {
    const r = await post("/api/playlist/create", {
      name: NAME, privacy: "10", type: "NORMAL", csrf_token: csrf
    });
    pid = (r.playlist || r.result || {}).id;
    if (!pid) {
      console.log("创建失败，返回：", r);
      console.log("你可以手动建一个叫「" + NAME + "」的空歌单，再粘一次这段代码。");
      return;
    }
    console.log("已创建《" + NAME + "》 id=" + pid);
  }
  console.log("开始写入 " + IDS.length + " 首…");

  for (let i = 0; i < IDS.length; i += 100) {
    const part = IDS.slice(i, i + 100);
    const a = await post("/api/playlist/manipulate/tracks", {
      pid: pid, trackIds: JSON.stringify(part), op: "add", csrf_token: csrf
    });
    const ok = (a.status === 200 || a.code === 200);
    console.log("[__LABEL__] 第 " + ((i / 100) + 1) + " 批 " + part.length + " 首 -> " +
                (ok ? "OK" : JSON.stringify(a).slice(0, 140)));
    await new Promise(s => setTimeout(s, 1200));
  }
  console.log("《" + NAME + "》 完成，共 " + IDS.length + " 首");
})();
"""


def write_preview(path: Path, rows: Iterable[Sequence]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_HEADER)
        writer.writerows(rows)


def read_preview(path: Path) -> list[dict[str, str]]:
    """读 preview.csv；兼容旧版本只有「分类」列的文件。"""
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        if "语种" not in row and "分类" in row:
            row["语种"] = row["分类"]
        row.setdefault("曲风", "")
    return rows


def group_ids(rows: Iterable[dict[str, str]], categories: Sequence[str]) -> dict[str, list[int]]:
    plan: dict[str, list[int]] = {c: [] for c in categories}
    for row in rows:
        category = row.get("语种") or row.get("分类") or ""
        if category in plan:
            plan[category].append(int(row["id"]))
    return plan


def console_script(category: str, ids: Sequence[int], playlist_name: str) -> str:
    return (
        CONSOLE_TEMPLATE.replace("__LABEL__", category)
        .replace("__NAME__", playlist_name)
        .replace("__COUNT__", str(len(ids)))
        .replace("__IDS__", json.dumps(list(ids)))
    )


def write_console_scripts(
    plan: Mapping[str, Sequence[int]],
    outdir: Path,
    playlist_prefix: str = "我的喜欢 · ",
    file_prefix: str = "加歌单",
) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for category, ids in plan.items():
        if not ids:
            continue
        path = outdir / f"{file_prefix}_{category}.js"
        path.write_text(
            console_script(category, ids, playlist_prefix + category), encoding="utf-8"
        )
        written.append(path)
    return written
