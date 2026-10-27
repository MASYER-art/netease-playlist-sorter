"""曲风标注测试。不依赖 pytest：``python tests/test_genres.py``"""

from types import SimpleNamespace

from netease_sorter.genres import GENRES, detect


def song(name="", artists="", album=""):
    return SimpleNamespace(name=name, artists=artists, album=album)


def test_edm_artist():
    assert "电子" in detect(song("Wake Me Up", "Avicii", "True"))


def test_remix_is_electronic():
    tags = detect(song("Faded (Remix)", "", ""))
    assert "电子" in tags


def test_anime_and_ost_multilabel():
    tags = detect(song("君の名は", "RADWIMPS", "TVアニメ『君の名は。』オリジナルサウンドトラック"))
    assert "二次元" in tags
    assert "原声" in tags


def test_classical():
    assert "古典" in detect(song("Nocturne Op.9 No.2", "Chopin", "Classical Piano"))


def test_rap():
    assert "说唱" in detect(song("Rap God", "Eminem", "The Marshall Mathers LP2"))


def test_fallback_without_language():
    assert detect(song("某个没有线索的歌", "某歌手", "某专辑")) == ["未标注"]


def test_fallback_by_language():
    assert detect(song("某个没有线索的歌", "", ""), lang="日语") == ["二次元"]
    assert detect(song("某个没有线索的歌", "", ""), lang="纯音乐") == ["轻音乐"]


def test_result_order_follows_genre_list():
    tags = detect(song("Anime Rock", "", "TVアニメ 主題歌"))
    assert tags == [g for g in GENRES if g in tags]


def test_no_false_positive_on_random_word():
    # "popular" 不该被 pop 命中（按词边界匹配）
    tags = detect(song("Popular Song", "", "Popular Hits"))
    assert "流行" not in tags


def main() -> None:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    main()
