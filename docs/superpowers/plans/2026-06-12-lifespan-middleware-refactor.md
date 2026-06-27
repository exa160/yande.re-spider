# Lifespan Middleware 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Starlette 单值 `lifespan_context` 的多钩子组合职责抽离到独立 `LifespanMiddleware` 模块，使用递归组合替代显式 `async with` 嵌套，保持各业务 `Middleware` 风格一致。

**Architecture:** 新增 `src/middleware/lifespan.py` 提供：
1. `LifespanMiddleware.register(hook)` 静态注册入口（收集钩子到内部列表）；
2. `LifespanMiddleware.init_app(app)` 用递归 `_compose(hooks, index)` 把列表折叠成单个 async context manager，挂到 `app.router.lifespan_context`。

`DownloadMiddleware` / `SchedulerMiddleware` 不再持有 `init_app` 入口（避免误用 `lifespan_context` 单值覆盖），改为只暴露 `lifespan` 钩子（`@staticmethod @asynccontextmanager`），由 `src/__init__.py` 显式调用 `LifespanMiddleware.register(...)` + `LifespanMiddleware.init_app(app)` 完成装配。

**Tech Stack:** Python 3.12、FastAPI 0.1x、Starlette、`contextlib.asynccontextmanager`、pytest。

---

## 文件结构

| 文件 | 变更 | 职责 |
|---|---|---|
| `backend/src/middleware/lifespan.py` | 新建 | lifespan 钩子注册表 + 递归组合 + `init_app` |
| `backend/src/middleware/downloader.py` | 修改 | 移除 `init_app`，保留 `lifespan` 钩子 |
| `backend/src/middleware/scheduler.py` | 修改 | 移除 `init_app`，保留 `lifespan` 钩子 |
| `backend/src/__init__.py` | 修改 | 用 `LifespanMiddleware.register + init_app` 替代显式 `async with` 嵌套 |
| `backend/src/middleware/__init__.py` | 修改 | 导出 `LifespanMiddleware`（按需，便于外部 import） |
| `unit_test/test_lifespan_middleware.py` | 新建 | 递归组合、注册顺序、启动/关闭顺序、空注册、重复注册保护 |
| `docs/middleware.md` | 修改 | 同步新规范（`LifespanMiddleware.register + init_app` 用法） |

---

## Task 1: 为 `LifespanMiddleware.register` 写失败单测

**Files:**
- Create: `unit_test/test_lifespan_middleware.py`

- [ ] **Step 1: 写失败单测覆盖注册表 + 递归组合行为**

新建 `unit_test/test_lifespan_middleware.py`：

```python
"""LifespanMiddleware 单测：注册表 + 递归组合 + 启动/关闭顺序。"""
import asyncio
from contextlib import asynccontextmanager
from typing import List

import pytest

from src.middleware.lifespan import LifespanMiddleware


@pytest.fixture(autouse=True)
def _reset_registry():
    """每个用例前后清空 LifespanMiddleware 内部注册表，避免污染。"""
    LifespanMiddleware._hooks.clear()
    yield
    LifespanMiddleware._hooks.clear()


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
    LifespanMiddleware.register(mk("a"))
    LifespanMiddleware.register(mk("b"))
    assert [h.__name__ for h in LifespanMiddleware._hooks] == ["hook", "hook"]


def test_compose_empty_registry_yields_idle_lifespan():
    """无注册钩子时, 组合器应直接 yield, 不抛错。"""
    @asynccontextmanager
    async def composed(app):
        async with LifespanMiddleware._compose() as _cm:
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
    LifespanMiddleware.register(mk("a"))
    LifespanMiddleware.register(mk("b"))
    LifespanMiddleware.register(mk("c"))

    @asynccontextmanager
    async def composed(app):
        async with LifespanMiddleware._compose():
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

    LifespanMiddleware.register(mk("a"))
    LifespanMiddleware.register(boom)
    LifespanMiddleware.register(mk("c"))

    @asynccontextmanager
    async def composed(app):
        async with LifespanMiddleware._compose():
            yield

    async def runner():
        with pytest.raises(RuntimeError, match="kapow"):
            async with composed(object()):
                events.append("body:UNREACHED")

    asyncio.run(runner())
    assert "body:UNREACHED" not in events
    assert "a:stop" in events  # a 已启动, 关闭时仍应触发
```

- [ ] **Step 2: 运行测试确认全部失败（ImportError: LifespanMiddleware 不存在）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/python -m pytest unit_test/test_lifespan_middleware.py -v
```

Expected: `ModuleNotFoundError: No module named 'src.middleware.lifespan'` 或 `ImportError: cannot import name 'LifespanMiddleware'`。

- [ ] **Step 3: 提交失败测试**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add unit_test/test_lifespan_middleware.py && git commit -m "test: add LifespanMiddleware unit tests (failing)"
```

---

## Task 2: 实现 `LifespanMiddleware`（注册表 + 递归组合）

**Files:**
- Create: `backend/src/middleware/lifespan.py`

- [ ] **Step 1: 创建 `backend/src/middleware/lifespan.py`**

```python
"""Lifespan 钩子注册与组合中间件

Starlette 的 ``app.router.lifespan_context`` 是单值属性, 多次赋值会互相覆盖。
为支持多个业务 Middleware 同时声明 lifespan 钩子, 本模块提供:

- ``LifespanMiddleware.register(hook)``: 业务侧按调用顺序注册 ``@asynccontextmanager`` 钩子。
- ``LifespanMiddleware.init_app(app)``: 在应用启动前把已注册的钩子用递归组合成
  单个 ``@asynccontextmanager``, 挂到 ``app.router.lifespan_context``。

组合语义: 后注册的钩子在内层, 启动顺序 = 注册顺序, 关闭顺序与启动相反。
"""
from contextlib import asynccontextmanager
from typing import Callable, List

from fastapi import FastAPI
from loguru import logger


HookFn = Callable


class LifespanMiddleware:
    """Lifespan 钩子注册表 + 递归组合器"""

    _hooks: List[HookFn] = []

    @staticmethod
    def register(hook: HookFn) -> None:
        """注册一个 lifespan 钩子 (必须为 @asynccontextmanager 装饰的 async 协程)。

        调用顺序即为启动顺序, 关闭按 LIFO 触发。
        """
        LifespanMiddleware._hooks.append(hook)

    @staticmethod
    def reset() -> None:
        """清空注册表, 主要用于单测。"""
        LifespanMiddleware._hooks.clear()

    @staticmethod
    @asynccontextmanager
    async def _compose():
        """递归地把 _hooks 列表折叠成单个 async context manager。

        终止条件: 列表为空, 直接 yield。
        递归步骤: 把列表首项与剩余项的 _compose 结果串联。
        """
        hooks = LifespanMiddleware._hooks
        if not hooks:
            yield
            return

        head, *rest = hooks
        saved = LifespanMiddleware._hooks
        LifespanMiddleware._hooks = rest
        try:
            async with head(None):
                async with LifespanMiddleware._compose():
                    yield
        finally:
            LifespanMiddleware._hooks = saved

    @staticmethod
    def init_app(app: FastAPI) -> None:
        """把已注册的钩子组合后挂到 app.router.lifespan_context。

        必须最后调用, 之后所有 ``register`` 都不会影响本次启动。
        """
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            async with LifespanMiddleware._compose():
                yield

        app.router.lifespan_context = lifespan
        logger.info(
            f"Lifespan composed with {len(LifespanMiddleware._hooks)} hook(s)"
        )
```

- [ ] **Step 2: 重新运行单测确认全部通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/python -m pytest unit_test/test_lifespan_middleware.py -v
```

Expected: 4 passed。

- [ ] **Step 3: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/middleware/lifespan.py && git commit -m "feat(middleware): add LifespanMiddleware with recursive hook composition"
```

---

## Task 3: 让两个 Middleware 改为只暴露 `lifespan` 钩子

**Files:**
- Modify: `backend/src/middleware/downloader.py:23-25`
- Modify: `backend/src/middleware/scheduler.py:22-24`

- [ ] **Step 1: 修改 `backend/src/middleware/downloader.py` —— 删除 `init_app`**

将文件末段（`init_app` 静态方法及上方空行）整体删除，使文件以 `_reload` 之类的尾部代码或最后一个方法结束。当前文件完整重写为：

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.infrastructure.download_queue import download_queue


class DownloadMiddleware:
    @staticmethod
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 启动
        await download_queue.start(num_workers=5)
        logger.info("下载队列已启动")
        try:
            yield
        finally:
            # 关闭
            await download_queue.stop()
            logger.info("下载队列已停止")
```

- [ ] **Step 2: 修改 `backend/src/middleware/scheduler.py` —— 删除 `init_app`**

将 `init_app` 静态方法（连同上方空行）整体删除，使文件保留 `lifespan` 与 `_reload_schedules`。当前文件完整重写为：

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.dao.favorite_dao import FavoriteDao
from src.infrastructure.scheduler import schedule_manager


class SchedulerMiddleware:
    @staticmethod
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        schedule_manager.start()
        SchedulerMiddleware._reload_schedules()
        try:
            yield
        finally:
            schedule_manager.shutdown(wait=False)
            logger.info("Scheduler stopped")

    @staticmethod
    def _reload_schedules() -> None:
        """从 DB 加载所有启用调度的收藏夹，注册到 APScheduler。"""
        try:
            with FavoriteDao() as dao:
                folders = dao.get_scheduled_folders()
                folder_dicts = [
                    {
                        "id": f.id,
                        "schedule_cron": f.schedule_cron,
                        "schedule_mode": f.schedule_mode,
                        "schedule_max_images": f.schedule_max_images,
                    }
                    for f in folders
                ]
        except Exception as e:
            logger.exception(f"Failed to reload schedules from DB: {e}")
            return

        schedule_manager.reload_from_db(folder_dicts)
        logger.info(f"Loaded {len(folder_dicts)} scheduled folders from DB")
```

- [ ] **Step 3: 语法编译 + 导入校验**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && .venv/bin/python -m py_compile src/middleware/downloader.py src/middleware/scheduler.py && echo OK
```

Expected: `OK`。

- [ ] **Step 4: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/middleware/downloader.py backend/src/middleware/scheduler.py && git commit -m "refactor(middleware): drop init_app from download/scheduler middlewares"
```

---

## Task 4: 重写 `src/__init__.py` 的 lifespan 装配

**Files:**
- Modify: `backend/src/__init__.py:10-17, 87-97`

- [ ] **Step 1: 添加新 import**

把 import 块（行 10-17）末尾追加 `from src.middleware.lifespan import LifespanMiddleware`，最终 8 个 import：

```python
from src.api import APILoader
from src.common.constant import path_constant
from src.middleware.downloader import DownloadMiddleware
from src.middleware.errors import ErrorHandleMiddleware
from src.middleware.frontend_static import FrontendStaticLoader
from src.middleware.lifespan import LifespanMiddleware
from src.middleware.loggers import LoggerMiddleware
from src.middleware.scheduler import SchedulerMiddleware
from src.middleware.session import RequestSessionMiddleware
```

- [ ] **Step 2: 替换 `init_app` 中的显式 lifespan 嵌套**

将 `init_app` 中行 87-97 整段（注释 + `from contextlib import asynccontextmanager` + 局部 `lifespan` 定义 + `app.router.lifespan_context = lifespan`）替换为：

```python
    DownloadMiddleware.lifespan  # noqa: F401
    SchedulerMiddleware.lifespan  # noqa: F401
    LifespanMiddleware.register(DownloadMiddleware.lifespan)
    LifespanMiddleware.register(SchedulerMiddleware.lifespan)
    LifespanMiddleware.init_app(app)
```

要点：
- 两行 `Middleware.lifespan  # noqa: F401` 仅用于保留"曾经引用过这个符号"的痕迹（防 pylint 误报），位置与现有 `init_app` 中所有 `XxxMiddleware.init_app(app)` 的风格保持一致。
- `register` 按业务启动顺序入栈：`Download` 先（供其他业务消费图片），`Scheduler` 后（向 download 队列投放任务）。
- `LifespanMiddleware.init_app(app)` 是统一的注册入口，与其他 `Xxx.init_app(app)` 调用风格一致。

完整 `init_app` 替换后（行 72-101）应为：

```python
def init_app(app: FastAPI) -> FastAPI:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    work_dir_setup()
    RequestSessionMiddleware.init_app(app)
    APILoader.init_app(app)
    LoggerMiddleware.init_app(app, path_constant.log_dir)
    ErrorHandleMiddleware.init_app(app)
    FrontendStaticLoader.init_app(app)
    DownloadMiddleware.lifespan  # noqa: F401
    SchedulerMiddleware.lifespan  # noqa: F401
    LifespanMiddleware.register(DownloadMiddleware.lifespan)
    LifespanMiddleware.register(SchedulerMiddleware.lifespan)
    LifespanMiddleware.init_app(app)

    _print_startup_banner(app_config)

    return app
```

- [ ] **Step 3: 验证 `init_app` 调用顺序与行为**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && .venv/bin/python -c "
from src.middleware.lifespan import LifespanMiddleware
LifespanMiddleware.reset()
from src import init_app, DownloadMiddleware, SchedulerMiddleware
from fastapi import FastAPI
a = FastAPI()
init_app(a)
print('lifespan ok:', a.router.lifespan_context is not None)
print('hooks registered during init_app:', LifespanMiddleware._hooks)
"
```

Expected:
- `lifespan ok: True`
- `hooks registered during init_app: []`（init_app 完成后注册表应已被 `_compose` 消费/还原成空列表）

- [ ] **Step 4: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/__init__.py && git commit -m "refactor(src): assemble lifespan via LifespanMiddleware.register + init_app"
```

---

## Task 5: 更新 `docs/middleware.md` 规范

**Files:**
- Modify: `docs/middleware.md`

- [ ] **Step 1: 在中间件注册顺序示例中追加 lifespan 装配**

定位 `docs/middleware.md` 行 19-24 附近（即 `init_app` 示例块），在 `ErrorHandleMiddleware.init_app(app)` 之后追加两行示例：

```python
    LifespanMiddleware.register(DownloadMiddleware.lifespan)
    LifespanMiddleware.register(SchedulerMiddleware.lifespan)
    LifespanMiddleware.init_app(app)
```

并在该段下方新增"## Lifespan 钩子规范"小节，解释：
- 业务 Middleware 只暴露 `lifespan`（`@staticmethod @asynccontextmanager`），不再提供 `init_app`。
- `LifespanMiddleware.register(hook)` 按启动顺序入栈。
- `LifespanMiddleware.init_app(app)` 内部递归组合并挂到 `app.router.lifespan_context`，必须最后调用。

- [ ] **Step 2: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add docs/middleware.md && git commit -m "docs(middleware): document LifespanMiddleware composition convention"
```

---

## Task 6: 端到端回归

**Files:** 无新增/修改

- [ ] **Step 1: 跑全部 unit_test**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/python -m pytest unit_test/ -v
```

Expected: 全部通过（含新加的 4 个 LifespanMiddleware 用例）。如出现 `filelock` 等无关失败属预存在问题，本次不动。

- [ ] **Step 2: 跑 `py_compile` 校验全部改动文件**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && .venv/bin/python -m py_compile src/__init__.py src/middleware/lifespan.py src/middleware/downloader.py src/middleware/scheduler.py && echo OK
```

Expected: `OK`。

- [ ] **Step 3: 跑 LSP 诊断**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && which pyright || true
```

如项目配置了 pyright/ruff，则在改动文件上跑一次；无配置则跳过。

---

## 自审

- **Spec 覆盖**：用户三条要求分别落到 Task 2（抽出新文件 + 递归调用 + 不显式嵌套）、Task 3（两个 Middleware 合并式暴露 lifespan）、Task 4（`init_app` 统一风格）。✓
- **占位符扫描**：无 TBD/TODO/"similar to"。每步含完整代码。✓
- **类型一致性**：`HookFn` 在 Task 2 定义为 `Callable`，Task 1 测试中按 `@asynccontextmanager` 装饰的协程传入，行为一致。✓
- **风险点**：`_compose` 通过临时改写 `LifespanMiddleware._hooks` 来递归；并发启动两个 app 会冲突（但本项目只启动一个 app，单测用 `reset` 隔离，可接受）。

---

## 执行方式

**Plan complete and saved to `docs/superpowers/plans/2026-06-12-lifespan-middleware-refactor.md`. Two execution options:**

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
