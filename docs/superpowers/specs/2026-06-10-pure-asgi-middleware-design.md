# Pure ASGI Middleware 替换 BaseHTTPMiddleware — 设计

**日期**：2026-06-10
**状态**：已批准（待实施）
**作者**：Sisyphus
**范围**：1 个文件

---

## 1. 背景

### 1.1 实证问题（2026-06-10 复现）

`backend/src/api/v1/favorites.py` 走 `RequestSessionMiddleware`（继承 `BaseHTTPMiddleware`）。`POST /api/v1/favorites` 返回 200 OK + id，但**DB 真实行数 0**（跨连接直查确认）。`INFORMATION_SCHEMA.INNODB_TRX` 产生 zombie（`is_read_only=0, rows_locked=0`）。

### 1.2 根因

`BaseHTTPMiddleware.dispatch` 内部用 `anyio.create_task_group` 把 `call_next(request)` 跑在**新 asyncio task** 里。**ContextVar 跨 asyncio task 不共享**（Python 官方保证）。所以：

- dispatch task 创建 session A + `_request_session.set(session A)`
- endpoint task 拿 `_request_session.get()` → `None`（ContextVar 跨 task 默认值）
- `RequestSessionMiddleware.get_session()` 静默 fallback new session B
- DAO 用 session B 做 INSERT，dispatch finally `session.commit()` commit 的是 A，A 没写过任何东西
- session B 永远不被 commit，INSERT 数据只在 ORM 内存，连接被 pool hold，事务半开 = zombie

### 1.3 官方推荐（2025-2026）

[Starlette 官方文档](https://starlette.dev/middleware/) 明确：

> "Using `BaseHTTPMiddleware` will prevent changes to `contextvars.ContextVar`s from propagating upwards... To overcome these limitations, use pure ASGI middleware."

2025-05 PR #2943 进一步澄清 BaseHTTPMiddleware 还会破坏后续 Pure ASGI Middleware 的 ContextVar 传播。

---

## 2. 目标 & 范围

### 2.1 目标

将 `RequestSessionMiddleware` 从 `BaseHTTPMiddleware` 改为 **Pure ASGI middleware**，修复 ContextVar 跨 task 失效问题。

### 2.2 范围内（只动 1 个文件）

- `backend/src/middleware/session.py` — 完整重写

### 2.3 范围外（保持现状）

- `BaseDAO` 不动（`owns_session` 标志保留）
- DAO 调用方一行不改
- `RequestSessionMiddleware.get_session()` / `init_app()` / `remove_session()` API 保持兼容（`src/__init__.py` 不需要改）
- 其他 6 个 middleware 不动
- `BaseHTTPMiddleware` 第三方使用不受影响（其他文件没用）

---

## 3. 设计

### 3.1 Pure ASGI Middleware 关键差异

| 检查项 | BaseHTTPMiddleware | Pure ASGI |
|---|---|---|
| 继承 | `BaseHTTPMiddleware` | 普通类 + `__call__(scope, receive, send)` |
| `await self.app(scope, ...)` | 内部 `anyio.create_task_group()` spawn 新 task | **直接 await**（同 task） |
| ContextVar 传播 | ❌ 跨 task 失效 | ✅ 同 task 共享 |
| `request.state` 访问 | ✓ | ✓ |
| `add_middleware` 兼容 | `app.add_middleware(BaseHTTPMiddlewareSubclass)` | `app.add_middleware(Middleware, PureASGIClass)` |

### 3.2 关键代码改动

**新 `session.py`**（完整重写）：

```python
from typing import Optional
from fastapi import FastAPI
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.types import ASGIApp, Scope, Receive, Send
from contextvars import ContextVar

from src.dao.database import _get_session_factory

_request_session: ContextVar[Optional[Session]] = ContextVar("request_session", default=None)


class RequestSessionMiddleware:
    """Pure ASGI middleware - ContextVar 在同 task 内正确传播"""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        session = _get_session_factory()()
        token = _request_session.set(session)
        try:
            await self.app(scope, receive, send)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            _request_session.reset(token)
            session.close()

    @staticmethod
    def get_session() -> Session:
        """严格模式：ContextVar 为 None 时直接报错（不再静默 new session）

        之前的 BaseHTTPMiddleware 版本因跨 task ContextVar 失效 + 静默 fallback
        导致 INSERT 数据只在 ORM 内存，dispatch finally commit 不到。
        改 Pure ASGI 后 ContextVar 正常传播，如果仍 None 说明真有问题，立即报错。
        """
        session = _request_session.get()
        if session is None:
            raise RuntimeError(
                "RequestSessionMiddleware not active. "
                "DAO called outside HTTP request context, or "
                "BaseHTTPMiddleware cross-task ContextVar bug regressed."
            )
        return session

    @staticmethod
    def init_app(app: FastAPI):
        """注册到 FastAPI app（API 兼容）"""
        from starlette.middleware import Middleware
        app.add_middleware(Middleware, RequestSessionMiddleware)

    @staticmethod
    def remove_session() -> None:
        _request_session.set(None)
```

### 3.3 关键变化

1. **去掉 `BaseHTTPMiddleware` 继承**（line 14）
2. **自己实现 `__call__(scope, receive, send)`** —— ASGI 接口（line 19-33）
3. **用 `ContextVar.set()` 返回的 token** + `reset(token)`（line 24, 31）—— 更严格的 cleanup
4. **`get_session()` fallback 改为 `raise RuntimeError`**（line 41-47）—— 不再静默 new session
5. **`init_app()` 用 `app.add_middleware(Middleware, RequestSessionMiddleware)`**（line 51）—— Pure ASGI 注册方式

### 3.4 `src/__init__.py` 不需要改

`init_app()` / `get_session()` / `remove_session()` API 兼容。`app.add_middleware` 接受不同类的中间件（内部是 `starlette.middleware.Middleware` 包装），调用方代码 0 改动。

---

## 4. 数据流

### 4.1 修复后 POST 流程

```
Pure ASGI dispatch (同 task):
    session A = factory()
    token = _request_session.set(A)        ← 在 dispatch task 可见
    await self.app(scope, receive, send)  ← 同 task, 端点也在这个 task
        endpoint:
            _request_session.get() → A     ← ✅ 同一个 session
            fav_dao.create():
                self.session = get_session() → A   ← ✅ 同一个
                INSERT ... (session A 内存里)
                self.session.flush()
            return
    session A.commit()                       ← ✅ INSERT 真的 commit
    _request_session.reset(token)
    session.close()
```

### 4.2 错误处理

| 场景 | 行为 |
|---|---|
| 正常请求 | 创建 session → set → endpoint 用 → commit → close |
| endpoint 抛异常 | rollback → 重新抛 → close |
| 非 HTTP scope（lifespan/websocket） | 不创建 session，直接 `await self.app(scope, ...)` |

### 4.3 严格模式的意义

| 场景 | 修复前 | 修复后 |
|---|---|---|
| 正常 HTTP 请求 | ✓ 静默工作（实际是 buggy） | ✓ 正常 |
| lifespan scheduler 任务（asyncio 任务） | 静默 new session → zombie | **RuntimeError 立即报错** |
| 任何 ContextVar 失效 | 静默 fallback | **RuntimeError 立即报错** |

---

## 5. 验证步骤

### 5.1 静态验证

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
# 1. import 不报错
from src.middleware.session import RequestSessionMiddleware, _request_session
print('PASS: import OK')

# 2. 不再继承 BaseHTTPMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
assert not issubclass(RequestSessionMiddleware, BaseHTTPMiddleware), 'must not inherit BaseHTTPMiddleware'
print('PASS: 不继承 BaseHTTPMiddleware')

# 3. 实现了 ASGI __call__
assert callable(getattr(RequestSessionMiddleware, '__call__', None))
print('PASS: __call__ 存在')

# 4. get_session 严格模式 (无 ContextVar 时报错)
try:
    RequestSessionMiddleware.get_session()
    print('FAIL: get_session 未报错')
except RuntimeError as e:
    print(f'PASS: get_session 严格模式: {e}')
"
```

### 5.2 端到端验证（关键）

| 步骤 | 期望 |
|---|---|
| 重启 uvicorn | 启动正常，`Loaded 0 scheduled folders from DB` |
| baseline zombie = 0 | 干净 |
| `POST /api/v1/favorites` | 200 OK + `id=N` |
| 立即查 DB（跨连接）| **count = 1**，**新行存在**（不是只在内存）|
| 连续 POST 5 次 | 每次都进 DB，count 累加 1, 2, 3, 4, 5 |
| INNODB_TRX | 每次 POST 后 = 0（事务正确提交）|
| `GET /api/v1/favorites` | 返回 5 个 folder |
| `DELETE /api/v1/favorites/{id}` | 200 OK，DB count 减 1 |
| lifespan 跑 scheduler 任务 | 不再产生 zombie（ContextVar 正确传播）|

### 5.3 严格模式触发测试

| 步骤 | 期望 |
|---|---|
| lifespan 启动时 `_reload_schedules()` 内 `with FavoriteDao() as dao:` | ✓ 正常 |
| lifespan 不应该触发 `get_session()` | 无 RuntimeError |

---

## 6. 不在本设计范围

- `BaseDAO` 重构
- DAO 调用方改 `with` 上下文
- `RequestSessionMiddleware.remove_session()` 重新设计（仍保留 set(None) 兼容）
- 其他 middleware 改造

---

## 7. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| `add_middleware(Middleware, ...)` 顺序问题 | 低 | 中 | 启动时 uvicorn 启动失败会立刻显式报错 |
| Pure ASGI middleware 影响其他 endpoint 行为 | 低 | 中 | 启动后跑 8 个端点 e2e 验证 |
| `request.state` 兼容性 | 低 | 低 | 新版不依赖 request.state |
| 严格模式导致其他代码炸 | 中 | 中 | 启动 lifespan 时立即验证不报错 |
| 跟 `add_middleware(BaseHTTPMiddlewareSubclass)` 已有调用方式冲突 | 极低 | 高 | `init_app()` 改用 `add_middleware(Middleware, ...)` 跟现有调用方解耦 |

---

## 8. 实施时间估算

| 任务 | 估算 |
|---|---|
| 重写 session.py | 5 分钟 |
| 静态验证 | 2 分钟 |
| 端到端 8 端点验证 + 严格模式触发 | 15 分钟 |
| **总计** | **22 分钟** |
