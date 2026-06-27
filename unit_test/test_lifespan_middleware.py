"""LifespanRegistry 单测：注册表 + 递归组合 + 启动/关闭顺序。"""
import asyncio
from contextlib import asynccontextmanager
from typing import List

import pytest

from src.lifecycle.lifespan import LifespanRegistry


@pytest.fixture(autouse=True)
def _reset_registry():
    """每个用例前后清空 LifespanRegistry 内部注册表，避免污染。"""
    LifespanRegistry._hooks.clear()
    yield
    LifespanRegistry._hooks.clear()


def _make_recorder():
    events: List[str] = []

    def hook_factory(name: str):
        @asynccontextmanager
        async def hook(app):
            events.append(f"{name}:start")
            try:
                yield
            finally:
                events.append(f"{name}:stop")
        return hook

    return events, hook_factory


def test_register_appends_hooks_in_order():
    events, mk = _make_recorder()
    hook_a = mk("a")
    hook_b = mk("b")
    LifespanRegistry.register(hook_a)
    LifespanRegistry.register(hook_b)
    assert LifespanRegistry._hooks == [hook_a, hook_b]


def test_compose_empty_registry_yields_idle_lifespan():
    """无注册钩子时, 组合器应直接 yield, 不抛错。"""
    @asynccontextmanager
    async def composed(app):
        async with LifespanRegistry._compose() as _cm:
            yield _cm

    ran = False

    async def runner():
        nonlocal ran
        async with composed(object()):
            ran = True

    asyncio.run(runner())
    assert ran is True


def test_compose_executes_hooks_in_registration_order():
    events, mk = _make_recorder()
    LifespanRegistry.register(mk("a"))
    LifespanRegistry.register(mk("b"))
    LifespanRegistry.register(mk("c"))

    @asynccontextmanager
    async def composed(app):
        async with LifespanRegistry._compose():
            yield

    async def runner():
        async with composed(object()):
            events.append("body")

    asyncio.run(runner())
    assert events == [
        "a:start", "b:start", "c:start",
        "body",
        "c:stop", "b:stop", "a:stop",
    ]


def test_compose_stops_lower_hooks_when_upper_raises():
    """启动时任一钩子抛错, 应阻止后续启动并触发已启动钩子的关闭。"""
    events, mk = _make_recorder()

    @asynccontextmanager
    async def boom(app):
        events.append("b:start")
        raise RuntimeError("kapow")
        yield  # unreachable, but @asynccontextmanager requires it

    LifespanRegistry.register(mk("a"))
    LifespanRegistry.register(boom)
    LifespanRegistry.register(mk("c"))

    @asynccontextmanager
    async def composed(app):
        async with LifespanRegistry._compose():
            yield

    async def runner():
        with pytest.raises(RuntimeError, match="kapow"):
            async with composed(object()):
                events.append("body:UNREACHED")

    asyncio.run(runner())
    assert "body:UNREACHED" not in events
    assert "a:stop" in events