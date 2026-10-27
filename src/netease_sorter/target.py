"""歌单落点解析：把「用户想要的名字」变成确定的 playlist id。

名字不是身份——可能重名、可能改名、可能是别人分享给你的歌单。
所以这里只做一件事：给定候选歌单列表 + 名字 + 已知 id，判断该复用、新建还是拒绝。
纯函数，方便测试。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping


class TargetError(RuntimeError):
    """落点不合法（重名、不是自己的、已存在且非空……）。"""


@dataclass(frozen=True)
class Target:
    name: str
    playlist_id: int | None
    action: str  # "create" 或 "reuse"


def resolve(
    name: str,
    playlists: Iterable[Mapping],
    uid: int,
    known_id: int | None = None,
    append: bool = False,
) -> Target:
    """决定这次写入落在哪个歌单。

    - ``known_id`` 来自本地 state，优先级最高（改名也不会走丢）；
    - 否则按名字找：找不到就新建，找到唯一一个就复用（需要空歌单或 ``append``），
      找到多个则报错，让人先把重名处理掉。
    """
    name = (name or "").strip()
    if not name:
        raise TargetError("歌单名不能为空")

    by_id = {int(p["id"]): p for p in playlists if p.get("id") is not None}
    if known_id is not None and int(known_id) in by_id:
        item = by_id[int(known_id)]
        _ensure_owned(item, uid, name)
        return Target(name, int(known_id), "reuse")

    matches = [p for p in by_id.values() if (p.get("name") or "") == name]
    if not matches:
        return Target(name, None, "create")
    if len(matches) > 1:
        ids = "、".join(str(int(p["id"])) for p in matches)
        raise TargetError(f"有 {len(matches)} 个叫《{name}》的歌单（id: {ids}），请先改名或合并")

    item = matches[0]
    _ensure_owned(item, uid, name)
    pid = int(item["id"])
    count = int(item.get("trackCount") or 0)
    if append or count == 0:
        return Target(name, pid, "reuse")
    raise TargetError(f"《{name}》已存在且有 {count} 首；加 --append 追加，或换个名字")


def _ensure_owned(item: Mapping, uid: int, name: str) -> None:
    owner = item.get("userId")
    if owner is None:
        return
    if int(owner) != int(uid):
        raise TargetError(f"《{name}》不是你创建的（id={int(item['id'])}），不能写入")
