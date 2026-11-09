"""Api.Using 指定账户后 _current_runtime 解析到对应账户运行时"""
from BilibiliAdapter.Core import BilibiliAdapter


class _RT:
    def __init__(self, name: str):
        self.name = name
        self.bot_id = name
        self.user_name = name


def _make_adapter() -> BilibiliAdapter:
    ad = BilibiliAdapter.__new__(BilibiliAdapter)
    ad._runtimes = {"a": _RT("a"), "x": _RT("x")}
    return ad


def test_using_resolves_named_runtime():
    ad = _make_adapter()
    api = BilibiliAdapter.Api(ad).Using("x")
    rt = ad._current_runtime(api._account_id or api.api_context.get("account_id"))
    assert rt is ad._runtimes["x"]


def test_without_using_falls_back_to_first_runtime():
    ad = _make_adapter()
    api = BilibiliAdapter.Api(ad)
    rt = ad._current_runtime(api._account_id or api.api_context.get("account_id"))
    assert rt is ad._runtimes["a"]
