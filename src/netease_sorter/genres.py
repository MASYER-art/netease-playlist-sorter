"""曲风启发式标注（多标签）。

网易云接口不返回曲风字段，这里只能用「标题 / 专辑 / 歌手」里的字符串线索去猜，
所以默认是多标签、允许为空，并且规则集中放在 ``RULES`` 里，方便按自己的库调整。

准确率明显低于语种判定，建议在网页里把它当成"筛子"而不是"结论"。
"""

from __future__ import annotations

from typing import Protocol

from .classify import hit_kw

GENRES = (
    "流行",
    "电子",
    "说唱",
    "摇滚",
    "金属",
    "民谣",
    "R&B",
    "爵士",
    "古典",
    "轻音乐",
    "国风",
    "二次元",
    "原声",
    "未标注",
)

# 顺序即优先级：一条歌可以命中多个（比如「二次元 + 原声」）
RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "电子",
        (
            "edm", "remix", "dj", "house", "techno", "trance", "dubstep", "electro",
            "future bass", "drum and bass", "dnb", "monstercat", "ncs", "电音", "电子",
            "avicii", "martin garrix", "kygo", "zedd", "alan walker", "vicetone",
            "marshmello", "skrillex", "calvin harris", "david guetta", "hardwell",
            "afrojack", "steve aoki", "illenium", "san holo", "odesza", "flume",
            "madeon", "porter robinson", "r3hab", "tiesto", "armin van buuren",
            "don diablo", "oliver heldens", "galantis", "chainsmokers",
        ),
    ),
    (
        "说唱",
        (
            "rap", "hip-hop", "hip hop", "hiphop", "trap", "说唱", "嘻哈",
            "cypher", "freestyle", "boom bap", "drill",
            "eminem", "kendrick lamar", "kanye", "jay-z", "travis scott", "j. cole",
        ),
    ),
    (
        "摇滚",
        (
            "rock", "摇滚", "punk", "朋克", "grunge", "indie rock", "britpop",
            "shoegaze", "post-rock", "乐队", "band",
        ),
    ),
    ("金属", ("metal", "金属", "metalcore", "deathcore", "screamo", "thrash", "doom")),
    ("民谣", ("folk", "民谣", "acoustic", "singer-songwriter", "校园民谣", "木吉他")),
    ("R&B", ("r&b", "rnb", "soul", "灵魂乐", "neo soul", "funk")),
    ("爵士", ("jazz", "爵士", "swing", "bossa", "blues", "蓝调", "big band")),
    (
        "古典",
        (
            "classical", "古典", "symphony", "交响", "concerto", "协奏", "sonata",
            "奏鸣", "orchestra", "管弦", "baroque", "巴赫", "莫扎特", "贝多芬",
            "肖邦", "柴可夫斯基", "德彪西", "拉赫玛尼诺夫", "vivaldi", "chopin",
            "debussy", "rachmaninoff", "beethoven", "mozart", "bach",
        ),
    ),
    ("国风", ("古风", "中国风", "戏腔", "水墨", "琵琶", "古筝", "二胡", "箫", "箜篌", "国乐")),
    (
        "二次元",
        (
            "アニメ", "anime", "ゲーム", "vocaloid", "初音", "東方", "touhou",
            "アイドル", "キャラクター", "galgame", "visual novel", "同人", "cv",
        ),
    ),
    (
        "原声",
        (
            "ost", "soundtrack", "サウンドトラック", "原声", "配乐", "劇場版", "剧场版",
            "主题曲", "主題歌", "印象曲", "original soundtrack", "motion picture", "bgm",
        ),
    ),
    ("流行", ("pop", "流行", "idol", "boy band", "girl group")),
)


class SongLike(Protocol):
    name: str
    artists: str
    album: str


def detect(
    song: SongLike,
    lang: str | None = None,
    rules: tuple[tuple[str, tuple[str, ...]], ...] = RULES,
) -> list[str]:
    """返回命中的曲风（按 ``GENRES`` 顺序）。

    没有任何关键词命中时，用 ``lang`` 做一个保守兜底：
    日语歌归「二次元」、纯音乐归「轻音乐」，其余归「未标注」。
    这些兜底只是先验，不代表真的知道曲风。
    """
    text = f"{song.name} {song.artists} {song.album}".lower()
    found = {genre for genre, keywords in rules if any(hit_kw(text, kw) for kw in keywords)}
    if not found:
        if lang == "日语":
            return ["二次元"]
        if lang == "纯音乐":
            return ["轻音乐"]
        return ["未标注"]
    return [genre for genre in GENRES if genre in found]


def join(genres: list[str]) -> str:
    return " / ".join(genres)
