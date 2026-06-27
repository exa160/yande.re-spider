"""Lifespan 钩子注册与组合器

Starlette 的 ``app.router.lifespan_context`` 是单值属性, 多次赋值会互相覆盖。
为支持多个业务 Lifecycle 同时声明 lifespan 钩子, 本模块提供:

- ``LifespanRegistry.register(hook)``: 业务侧按调用顺序注册 ``@asynccontextmanager`` 钩子。
- ``LifespanRegistry.init_app(app)``: 在应用启动前把已注册的钩子用递归组合成
  单个 ``@asynccontextmanager``, 挂到 ``app.router.lifespan_context``。

组合语义: 后注册的钩子在内层, 启动顺序 = 注册顺序, 关闭顺序与启动相反。
"""
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Callable, List

from fastapi import FastAPI
from loguru import logger


HookFn = Callable[..., AbstractAsyncContextManager[None]]


class LifespanRegistry:
    """Lifespan 钩子注册表 + 递归组合器"""

    _hooks: List[HookFn] = []

    @staticmethod
    def register(hook: HookFn) -> None:
        """注册一个 lifespan 钩子 (必须为 @asynccontextmanager 装饰的 async 协程)。

        调用顺序即为启动顺序, 关闭按 LIFO 触发。
        """
        LifespanRegistry._hooks.append(hook)

    @staticmethod
    def reset() -> None:
        """清空注册表, 主要用于单测。"""
        LifespanRegistry._hooks.clear()

    @staticmethod
    @asynccontextmanager
    async def _compose():
        """递归地把 _hooks 列表折叠成单个 async context manager。

        终止条件: 列表为空, 直接 yield。
        递归步骤: 把列表首项与剩余项的 _compose 结果串联。
        """
        hooks = LifespanRegistry._hooks
        if not hooks:
            yield
            return

        head, *rest = hooks
        saved = LifespanRegistry._hooks
        LifespanRegistry._hooks = rest
        try:
            async with head(None):
                async with LifespanRegistry._compose():
                    yield
        finally:
            LifespanRegistry._hooks = saved

    @staticmethod
    def init_app(app: FastAPI) -> None:
        """把已注册的钩子组合后挂到 app.router.lifespan_context。

        必须最后调用, 之后所有 ``register`` 都不会影响本次启动。
        """
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with LifespanRegistry._compose():
                yield

        app.router.lifespan_context = lifespan
        logger.info(
            f"Lifespan composed with {len(LifespanRegistry._hooks)} hook(s)"
        )
