"""分类器单元测试。

不依赖 pytest 也能跑：``python tests/test_classify.py``
"""

from types import SimpleNamespace

from netease_sorter.classify import classify


def song(name="", artists="", album="", lyric="", pure=False):
    return SimpleNamespace(name=name, artists=artists, album=album, lyric=lyric, pure=pure)


def test_pure_music_flag_wins():
    result = classify(song("Autumn", "July", "Autumn", lyric="", pure=True))
    assert result.category == "纯音乐"
    assert result.confidence == "high"


def test_placeholder_lyric():
    lyric = "[00:00.00] 作曲 : July\n[00:05.00]纯音乐，请欣赏"
    assert classify(song("Autumn", "July", "", lyric)).category == "纯音乐"


def test_ost_substring_is_not_instrumental():
    """Post Malone 里含子串 ost，不能被当成 OST 纯音乐。"""
    lyric = "[00:01.00]I got the moves, I got the money\n[00:02.00]Call me Post Malone"
    result = classify(song("Post Malone (feat. RANI)", "Sam Feldt", "The Remixes", lyric))
    assert result.category == "英文", result


def test_english_with_chinese_translation():
    """带中文翻译歌词的英文歌，不能被判成中文。"""
    lyric = (
        "[00:01.00]I really want to stay at your house\n"
        "[00:02.00]我真的想留在你的房子里\n"
        "[00:03.00]And I hope this works out\n"
        "[00:04.00]我希望这一切能成真\n"
    )
    result = classify(song("I Really Want to Stay at Your House", "Rosa Walton", "", lyric))
    assert result.category == "英文", result


def test_chinese_song():
    lyric = (
        "[00:01.00]悬溺 - 葛东琪\n"
        "[00:02.00]我想要的 只是你在我身边\n"
        "[00:03.00]可是你却离我越来越远\n"
    )
    result = classify(song("悬溺", "葛东琪", "第二街区", lyric))
    assert result.category == "中文", result


def test_chinese_song_with_english_chorus():
    lyric = (
        "[00:01.00]我穿过人海只为找到你\n"
        "[00:02.00]Baby I love you 每一天\n"
        "[00:03.00]就算世界都改变 我也不会放开你的手\n"
    )
    assert classify(song("找到你", "某歌手", "", lyric)).category == "中文"


def test_japanese_song():
    lyric = (
        "[00:01.00]溢れ出した感情は\n"
        "[00:02.00]言葉にならないまま\n"
        "[00:03.00]君に届けたい\n"
    )
    result = classify(song("春となり", "あたらよ", "春となり", lyric))
    assert result.category == "日语", result


def test_korean_goes_to_other():
    lyric = "[00:01.00]사랑해 이 말밖에\n[00:02.00]난 할 수가 없어\n"
    assert classify(song("Falling U", "T-ara", "", lyric)).category == "其他"


def test_no_lyric_uses_title_script():
    assert classify(song("みなみかぜ", "", "")).category == "日语"
    assert classify(song("悬溺", "", "")).category == "中文"
    assert classify(song("Piano Sonata", "", "")).category == "纯音乐"


def test_unknown_script():
    assert classify(song("Приятные Сны", "", "", "")).category == "其他"


def main() -> None:
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    main()
