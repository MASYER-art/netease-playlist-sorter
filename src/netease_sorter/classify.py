"""语种 / 纯音乐判定。

判定顺序（前面的命中就不再往下走）：

1. ``pureMusic`` 标记 —— 网易云自己标的纯音乐，最可靠
2. 歌词是「纯音乐，请欣赏」占位
3. 标题 / 专辑里的强关键词（纯音乐、instrumental、bgm……）
4. 没有歌词：先看标题里的弱关键词，再按标题文字判断语种
5. 假名占比 -> 日语
6. 谚文 -> 其他（韩语）
7. 汉字 vs 拉丁字母加权计分 -> 中文 / 英文

第 7 步给标题更高权重，否则「带中文翻译歌词的英文歌」会整片被判成中文。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

CATEGORIES = ("中文", "英文", "日语", "纯音乐")
OTHER = "其他"

KANA_RE = re.compile(r"[\u3040-\u30ff\u31f0-\u31ff]")  # 平假名 + 片假名
HAN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
HANGUL_RE = re.compile(r"[\u1100-\u11ff\uac00-\ud7af]")
LATIN_RE = re.compile(r"[A-Za-z]")
TS_RE = re.compile(r"\[[^\]]*\]")  # LRC 时间轴

PLACEHOLDER = ("纯音乐，请欣赏", "纯音乐,请欣赏", "纯音乐 请欣赏", "纯音乐，静享")

# 单独出现就足以判定纯音乐
STRONG_INSTR = ("纯音乐", "轻音乐", "instrumental", "inst.", "bgm", "演奏", "独奏")
# 只作为弱线索：soundtrack / ost 经常混人声
WEAK_INSTR = (
    "配乐", "背景音乐", "钢琴", "吉他", "小提琴", "大提琴", "二胡", "古筝", "琵琶",
    "八音盒", "音乐盒", "合奏", "交响", "soundtrack", "ost", "piano", "guitar",
    "violin", "cello", "lofi", "lo-fi", "ambient", "伴奏",
)
ASCII_KW_RE = re.compile(r"^[a-z. ]+$")


class SongLike(Protocol):
    name: str
    artists: str
    album: str
    lyric: str
    pure: bool


@dataclass(frozen=True)
class Result:
    category: str
    confidence: str  # high / mid / low / manual
    reason: str


def hit_kw(text: str, keyword: str) -> bool:
    """英文关键词按词边界匹配，避免 ``Post Malone`` 命中 ``ost``。"""
    if ASCII_KW_RE.match(keyword):
        return re.search(r"(?<![a-z])" + re.escape(keyword) + r"(?![a-z])", text) is not None
    return keyword in text


def script_counts(text: str) -> tuple[int, int, int, int]:
    """返回 (假名, 汉字, 谚文, 拉丁字母) 的数量。"""
    text = text or ""
    return (
        len(KANA_RE.findall(text)),
        len(HAN_RE.findall(text)),
        len(HANGUL_RE.findall(text)),
        len(LATIN_RE.findall(text)),
    )


def clean_lyric(text: str) -> str:
    return TS_RE.sub("", text or "").strip()


def classify(song: SongLike) -> Result:
    meta = f"{song.name} {song.artists} {song.album}"
    lyric = clean_lyric(song.lyric)
    low = meta.lower()

    # 1) 网易云自己的纯音乐标记
    if song.pure:
        return Result("纯音乐", "high", "接口标记 pureMusic")
    if any(p in lyric for p in PLACEHOLDER):
        return Result("纯音乐", "high", "歌词为「纯音乐请欣赏」占位")

    # 2) 强关键词
    for kw in STRONG_INSTR:
        if hit_kw(low, kw):
            return Result("纯音乐", "high", f"标题/专辑含关键词:{kw}")

    km, hm, gm, lm = script_counts(meta)
    kl, hl, gl, ll = script_counts(lyric)

    # 3) 没有歌词：先看纯音乐线索，再看标题语言
    if not lyric:
        for kw in WEAK_INSTR:
            if hit_kw(low, kw):
                return Result("纯音乐", "mid", f"无歌词+标题含关键词:{kw}")
        if kl >= 1 or km >= 1:
            return Result("日语", "low", "无歌词，标题含假名")
        if gm >= 1 or gl >= 1:
            return Result(OTHER, "low", "无歌词，标题含谚文")
        if hm >= 1:
            return Result("中文", "low", "无歌词，标题含汉字")
        if lm >= 2:
            return Result("英文", "low", "无歌词，标题为拉丁字母")
        return Result(OTHER, "low", "无歌词且无语言线索")

    # 4) 日语：假名占比
    if kl >= 2 and kl >= 0.03 * (kl + hl):
        return Result("日语", "high", f"歌词假名 {kl} / 汉字 {hl}")
    if km >= 1 and kl + km >= 2 and hm <= km * 3:
        return Result("日语", "mid", "标题含假名")

    # 5) 韩语
    if gl >= 3 and gl >= 0.1 * (gl + hl):
        return Result(OTHER, "mid", f"谚文 {gl}")

    # 6) 中文 / 英文：标题权重更高
    zh = hm * 2 + hl
    en = lm * 2 + ll
    if zh >= 20 and zh >= en * 0.6:
        return Result("中文", "high" if zh > en else "mid", f"汉字计分 {zh} vs 拉丁 {en}")
    if en >= 20:
        return Result("英文", "high" if en > zh else "mid", f"拉丁计分 {en} vs 汉字 {zh}")
    if zh > en:
        return Result("中文", "low", f"样本偏少 汉字 {zh} vs 拉丁 {en}")
    return Result(OTHER, "low", f"无法判定 zh={zh} en={en}")


def load_overrides(path: str) -> dict[int, str]:
    """读取人工修正表：``歌曲id,类别``，一行一条，# 开头为注释。"""
    import csv

    overrides: dict[int, str] = {}
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            for row in csv.reader(fh):
                if not row or row[0].startswith("#"):
                    continue
                if len(row) < 2:
                    continue
                try:
                    sid = int(row[0].strip())
                except ValueError:
                    continue  # 表头
                category = row[1].strip()
                if category in CATEGORIES or category == OTHER:
                    overrides[sid] = category
    except FileNotFoundError:
        pass
    return overrides
