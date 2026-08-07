"""验证 RequestSessionMiddleware 在 endpoint 抛异常时不二次抛 TypeError

背景：Session.rollback() 是同步方法返回 None。
原代码 `await session.rollback()` 等于 `await None` → TypeError: object NoneType
can't be used in 'await' expression。这会把原异常掩盖。

修复后 middleware 异常路径必须调 `session.rollback()`（同步），保留原异常上抛。

实现：项目未注册 pytest-asyncio，用 asyncio.run() 在 sync test 中驱动 async middleware。
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest


def test_middleware_calls_rollback_synchronously_on_exception(monkeypatch):
    """endpoint 抛异常时，rollback 必须被同步调用（不 await None）"""
    from src.middleware.session import RequestSessionMiddleware

    state = {"rollback_sync_called": False}

    class FakeSession:
        def rollback(self):
            state["rollback_sync_called"] = True
            return None

        def commit(self):
            pass

        def close(self):
            pass

    import src.middleware.session as sm
    monkeypatch.setattr(sm, "_get_session_factory", lambda: lambda: FakeSession())

    async def broken_app(scope, receive, send):
        raise RuntimeError("endpoint fail")

    mw = RequestSessionMiddleware(broken_app)

    with pytest.raises(RuntimeError, match="endpoint fail"):
        asyncio.run(
            mw({"type": "http"}, lambda: None, lambda *a, **k: None)
        )

    assert state["rollback_sync_called"], (
        "rollback() 应在 endpoint 异常路径被同步调用（不 await）"
    )


def test_middleware_does_not_await_rollback(monkeypatch):
    """明确测试：原 bug 是 `await session.rollback()` 导致 TypeError

    修复后异常路径应该直接 raise 原异常，没有 TypeError 中间层。
    """
    from src.middleware.session import RequestSessionMiddleware

    class FakeSession:
        def rollback(self):
            return None

        def commit(self):
            pass

        def close(self):
            pass

    import src.middleware.session as sm
    monkeypatch.setattr(sm, "_get_session_factory", lambda: lambda: FakeSession())

    endpoint_exc = ValueError("real endpoint error")

    async def broken_app(scope, receive, send):
        raise endpoint_exc

    mw = RequestSessionMiddleware(broken_app)

    try:
        asyncio.run(
            mw({"type": "http"}, lambda: None, lambda *a, **k: None)
        )
    except BaseException as exc:
        assert exc is endpoint_exc, (
            f"应该 raise 原 endpoint 异常 {endpoint_exc!r}，"
            f"实际 {exc!r}（如果是 TypeError 说明仍在 await rollback()）"
        )
    else:
        pytest.fail("expected endpoint_exc to be raised")

