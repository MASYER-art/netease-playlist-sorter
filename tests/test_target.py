"""歌单落点解析的单元测试。python tests/test_target.py"""

from netease_sorter.target import TargetError, resolve

UID = 42


def pl(pid, name, count=0, owner=UID):
    return {"id": pid, "name": name, "trackCount": count, "userId": owner}


def test_empty_account_creates():
    t = resolve("新歌单", [], UID)
    assert t.action == "create" and t.playlist_id is None


def test_name_not_found_creates():
    t = resolve("新歌单", [pl(1, "别的歌单", 10)], UID)
    assert t.action == "create"


def test_empty_same_name_reused():
    t = resolve("新歌单", [pl(1, "新歌单", 0)], UID)
    assert t.action == "reuse" and t.playlist_id == 1


def test_non_empty_same_name_refused_without_append():
    try:
        resolve("新歌单", [pl(1, "新歌单", 10)], UID)
    except TargetError as exc:
        assert "已存在" in str(exc)
    else:
        raise AssertionError("应该拒绝")


def test_append_allows_non_empty():
    t = resolve("新歌单", [pl(1, "新歌单", 10)], UID, append=True)
    assert t.action == "reuse" and t.playlist_id == 1


def test_duplicate_names_refused():
    try:
        resolve("同名", [pl(1, "同名", 0), pl(2, "同名", 0)], UID)
    except TargetError as exc:
        assert "2 个" in str(exc)
    else:
        raise AssertionError("重名应该报错")


def test_foreign_playlist_refused():
    try:
        resolve("别人的", [pl(9, "别人的", 0, owner=7)], UID)
    except TargetError as exc:
        assert "不是你创建" in str(exc)
    else:
        raise AssertionError("应该拒绝写入别人的歌单")


def test_known_id_wins_even_after_rename():
    t = resolve("改过的名字", [pl(5, "旧名字", 3)], UID, known_id=5)
    assert t.action == "reuse" and t.playlist_id == 5


def test_known_id_missing_falls_back_to_name():
    t = resolve("新歌单", [pl(1, "新歌单", 0)], UID, known_id=999)
    assert t.action == "reuse" and t.playlist_id == 1


def test_blank_name_refused():
    try:
        resolve("   ", [], UID)
    except TargetError:
        pass
    else:
        raise AssertionError("空名字应该报错")


def main() -> None:
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print(f"\n{len(tests)} passed")


if __name__ == "__main__":
    main()
