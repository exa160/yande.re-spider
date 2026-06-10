# 实施计划：Pure ASGI Middleware 修复 ContextVar 跨 task bug

**日期**：2026-06-10
**配套 spec**：`docs/superpowers/specs/2026-06-10-pure-asgi-middleware-design.md`
**实施者**：Sisyphus
**预计耗时**：22 分钟

---

## 阶段 1：准备 (2 分钟)

### 1.1 验证现状

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
# 确认 uvicorn 跑着 --reload 模式
ps -ef | grep -E "uvicorn.*app" | grep -v grep | head -3
# 确认 DB 干净
mysql -h 127.0.0.1 -u root -proot yandere -e "SELECT COUNT(*) FROM favorite_folders;"
# 确认 zombie baseline
mysql -h 127.0.0.1 -u root -proot -e "SELECT COUNT(*) FROM information_schema.INNODB_TRX WHERE trx_state='RUNNING';"
```

**预期**：uvicorn 进程存在，folder count 跟上次验证一致（≈6），zombie = 0

### 1.2 读源文件

```bash
cat backend/src/middleware/session.py
```

**目标**：精确知道要改的 3 处（line 11 `ContextVar default=None` / line 13-46 `RequestSessionMiddleware` / 关键 `get_session` fallback）

---

## 阶段 2：实施 (5 分钟)

### 2.1 重写 `backend/src/middleware/session.py`

**完整重写为 1 个文件 ~50 行**（参考 spec §3.2）

```python
"""HTTP 请求级别的 SQLAlchemy session 上下文管理

设计：Pure ASGI middleware (替代 BaseHTTPMiddleware)
原因：BaseHTTPMiddleware 内部用 anyio.create_task_group 把 endpoint 跑在新 task，
     ContextVar 跨 task 不共享 → DAO 静默 new session → dispatch commit 不到
     endpoint 写的 INSERT → 数据半开事务 (zombie)。
替代：纯 ASGI __call__(scope, receive, send) 直接 await self.app(),
     endpoint 跟 dispatch 在同一个 asyncio task，ContextVar 正确传播。
"""
from typing import Optional

from fastapi import FastAPI
from sqlalchemy.orm import Session
from starlette.types import ASGIApp, Receive, Scope, Send
from contextvars import ContextVar

from src.dao.database import _get_session_factory

# ContextVar 存储当前 HTTP 请求的 session
# default=None 是关键：Pure ASGI 后，跨 task 仍能正确传播 (同一 task 共享)
_request_session: ContextVar[Optional[Session]] = ContextVar(
    "request_session", default=None
)


class RequestSessionMiddleware:
    """Pure ASGI middleware: 同一 task 内共享 session，commit/rollback 完整

    对外 API 与原 BaseHTTPMiddleware 版本兼容:
    - init_app(app): FastAPI app 注册
    - get_session(): DAO 拿 session（严格模式：None 时报错）
    - remove_session(): 清空 ContextVar (兼容保留)
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # 非 HTTP scope (lifespan/websocket) 不需要 session
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # 创建新 session 绑定到当前 task 的 ContextVar
        session = _get_session_factory()()
        token = _request_session.set(session)
        try:
            # 直接 await，不 spawn 新 task → ContextVar 正确传播
            await self.app(scope, receive, send)
            # endpoint 全部成功后 commit (INSERT 真的进 DB)
            session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # token 严格 reset, 不留污染
            _request_session.reset(token)
            session.close()

    @staticmethod
    def get_session() -> Session:
        """获取当前请求的 session (严格模式)

        之前 BaseHTTPMiddleware 版本 fallback 到 _get_session_factory()()
        会静默 new session，掩盖了 ContextVar 失效问题。
        改 Pure ASGI 后 ContextVar 正常传播，如果仍 None 说明:
        1. DAO 被 lifespan/定时任务直接调用 (应该用 with FavoriteDao() as dao:)
        2. ContextVar 跨 task 失效问题回归 (必须立即报错)
        """
        session = _request_session.get()
        if session is None:
            raise RuntimeError(
                "RequestSessionMiddleware not active. "
                "DAO called outside HTTP request context, or "
                "ContextVar cross-task propagation regressed. "
                "For background tasks, use 'with FavoriteDao() as dao:'."
            )
        return session

    @staticmethod
    def init_app(app: FastAPI) -> None:
        """注册到 FastAPI app

        Pure ASGI middleware 用 starlette.middleware.Middleware 包装后注册
        """
        from starlette.middleware import Middleware
        app.add_middleware(Middleware, RequestSessionMiddleware)

    @staticmethod
    def remove_session() -> None:
        """清空 ContextVar (兼容保留, 通常不需要)"""
        _request_session.set(None)
```

### 2.2 静态检查

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
from src.middleware.session import RequestSessionMiddleware, _request_session
print('PASS: import')

from starlette.middleware.base import BaseHTTPMiddleware
assert not issubclass(RequestSessionMiddleware, BaseHTTPMiddleware), 'still inherits'
print('PASS: 不再继承 BaseHTTPMiddleware')

# 严格模式触发
try:
    RequestSessionMiddleware.get_session()
    print('FAIL')
except RuntimeError as e:
    print(f'PASS: 严格模式触发: {e}')
"
```

---

## 阶段 3：动态验证 (15 分钟)

### 3.1 重启 uvicorn

```bash
# 杀掉现有 reload 模式进程
kill 186236 2>/dev/null
# 重新启动 (reload 模式)
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  nohup /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m uvicorn src.app:app --host 0.0.0.0 --port 8765 --reload > /tmp/uvicorn-v113.log 2>&1 &
echo "PID: $!"
sleep 3
# 确认启动成功, lifespan 跑过
tail -20 /tmp/uvicorn-v113.log | grep -E "Started|Loaded|Application startup|ERROR|Traceback"
```

**预期**：
- `Application startup complete`
- `Loaded N scheduled folders from DB` (N 跟之前一致)
- 无 `ERROR` / `Traceback`

### 3.2 验证：POST 真的写进 DB

```bash
# baseline count
BEFORE=$(mysql -h 127.0.0.1 -u root -proot -sN -e "SELECT COUNT(*) FROM yandere.favorite_folders;")
echo "BEFORE: $BEFORE"

# POST 1 个 folder
curl -s -X POST http://localhost:8765/api/v1/favorites \
  -H "Content-Type: application/json" \
  -d '{"name": "asgi-test-1", "interval": 300, "tags": ["test"], "max_pages": 1}' \
  | python -m json.tool

sleep 1

# 跨连接直查 DB
AFTER=$(mysql -h 127.0.0.1 -u root -proot -sN -e "SELECT COUNT(*) FROM yandere.favorite_folders;")
echo "AFTER:  $AFTER"

if [ "$AFTER" -gt "$BEFORE" ]; then
  echo "✓ POST 真的写进 DB"
else
  echo "✗ 修复失败"
fi

# zombie 检查
ZOMBIE=$(mysql -h 127.0.0.1 -u root -proot -sN -e "SELECT COUNT(*) FROM information_schema.INNODB_TRX WHERE trx_state='RUNNING' AND trx_is_read_only=0 AND trx_rows_locked=0;")
echo "ZOMBIE: $ZOMBIE"
```

**预期**：
- `BEFORE: N` → `AFTER: N+1`
- `ZOMBIE: 0`

### 3.3 验证：连续 5 次 POST 都入库

```bash
for i in 2 3 4 5 6; do
  curl -s -X POST http://localhost:8765/api/v1/favorites \
    -H "Content-Type: application/json" \
    -d "{\"name\": \"asgi-test-$i\", \"interval\": 300, \"tags\": [\"test\"], \"max_pages\": 1}" \
    -o /dev/null -w "POST $i: %{http_code}\n"
done
sleep 2

COUNT=$(mysql -h 127.0.0.1 -u root -proot -sN -e "SELECT COUNT(*) FROM yandere.favorite_folders WHERE name LIKE 'asgi-test-%';")
echo "TOTAL asgi-test folders in DB: $COUNT"
```

**预期**：`TOTAL = 6`（1 + 5）

### 3.4 验证：8 个端点 e2e 不报错

```bash
# 1. list
curl -s http://localhost:8765/api/v1/favorites -o /dev/null -w "GET list: %{http_code}\n"

# 2. get single
ID=$(curl -s http://localhost:8765/api/v1/favorites | python -c "import json,sys; d=json.load(sys.stdin); print(d['data'][0]['id'])")
curl -s "http://localhost:8765/api/v1/favorites/$ID" -o /dev/null -w "GET single: %{http_code}\n"

# 3. update
curl -s -X PATCH "http://localhost:8765/api/v1/favorites/$ID" \
  -H "Content-Type: application/json" \
  -d '{"name": "asgi-test-1-updated"}' \
  -o /dev/null -w "PATCH: %{http_code}\n"

# 4. schedule now
curl -s -X POST "http://localhost:8765/api/v1/favorites/$ID/schedule-now" -o /dev/null -w "POST schedule-now: %{http_code}\n"

# 5. get status
curl -s "http://localhost:8765/api/v1/favorites/$ID/status" -o /dev/null -w "GET status: %{http_code}\n"

# 6. list by status
curl -s "http://localhost:8765/api/v1/favorites?status=idle" -o /dev/null -w "GET list?status: %{http_code}\n"

# 7. get scheduler status
curl -s "http://localhost:8765/api/v1/favorites/scheduler/status" -o /dev/null -w "GET scheduler/status: %{http_code}\n"

# 8. delete
curl -s -X DELETE "http://localhost:8765/api/v1/favorites/$ID" -o /dev/null -w "DELETE: %{http_code}\n"
```

**预期**：所有 8 个端点都 200 OK 或 4xx（业务逻辑错误，**不是 500**）

### 3.5 验证：严格模式不误伤 lifespan

```bash
# 看 uvicorn 启动日志，确认 lifespan 阶段没有 RuntimeError
grep -E "RuntimeError|ContextVar" /tmp/uvicorn-v113.log | head -5
```

**预期**：空（lifespan 用 `with FavoriteDao() as dao:` 不经过 middleware）

### 3.6 验证：lifespan scheduler 真不 zombie

```bash
# 启动后等 5 秒, 看 zombie 状态
sleep 5
ZOMBIE=$(mysql -h 127.0.0.1 -u root -proot -sN -e "SELECT COUNT(*) FROM information_schema.INNODB_TRX WHERE trx_state='RUNNING' AND trx_is_read_only=0 AND trx_rows_locked=0;")
echo "ZOMBIE after 5s: $ZOMBIE"
```

**预期**：`ZOMBIE: 0`

---

## 阶段 4：清理 + commit (5 分钟)

### 4.1 清理测试数据（不删历史）

```bash
mysql -h 127.0.0.1 -u root -proot yandere -e "DELETE FROM favorite_folders WHERE name LIKE 'asgi-test-%';"
# 确认历史数据没动
mysql -h 127.0.0.1 -u root -proot yandere -e "SELECT id, name FROM favorite_folders;"
```

### 4.2 提交

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git status
git diff --stat
git add backend/src/middleware/session.py
git commit -m "fix(middleware): Pure ASGI middleware to fix ContextVar cross-task bug

BaseHTTPMiddleware.dispatch() uses anyio.create_task_group() to run
endpoints in a new asyncio task. ContextVars do NOT propagate across
asyncio task boundaries (Python language guarantee). Result:

  - dispatch task: creates session A, sets _request_session
  - endpoint task: _request_session.get() returns None (cross-task default)
  - RequestSessionMiddleware.get_session() silently fell back to
    _get_session_factory()() = new session B
  - DAO INSERT wrote into B's memory (not committed)
  - dispatch finally committed session A (never had the INSERT)
  - session B half-open transaction: zombie

This Pure ASGI implementation:

  - Direct await self.app(scope, receive, send) — no task spawn
  - ContextVar propagates correctly within same task
  - get_session() in strict mode: RuntimeError instead of silent
    fallback (makes future regressions immediately visible)
  - API-compatible with init_app / get_session / remove_session

Verified:
  - POST /api/v1/favorites: 200 OK + DB count++ (real persistence)
  - 6 consecutive POSTs all land in DB
  - 8 endpoints e2e 200 OK
  - 0 zombie transactions after restart + 5s

After: v1.1.1 (zombie stale read) + v1.1.2 (JSON str fallback) +
       v1.1.3 (ContextVar cross-task) — root cause fully fixed.

Refs: https://starlette.dev/middleware/ (BaseHTTPMiddleware limitations)
Refs: https://github.com/encode/starlette/issues/1678 (deprecation proposal)
Refs: https://github.com/encode/starlette/pull/2943 (cross-task limit)
Refs: https://github.com/encode/starlette/discussions/2160 (deprecation plan)"
```

### 4.3 push + 询问 tag

```bash
git push origin next_dev
# 不主动打 tag，问用户确认
```

---

## 阶段 5：交付

- [ ] spec + plan commit
- [ ] 实施 commit + push
- [ ] 询问用户是否打 v1.1.3 tag + 提 PR #5
- [ ] （可选）GH Action latest 守卫 + 三个 version 源修复（独立 PR）

---

## 风险回退

如果阶段 3 失败：
1. `git checkout origin/next_dev -- backend/src/middleware/session.py`
2. kill uvicorn + 重启
3. 把测试数据 delete
4. 重新走 plan

## 时间日志

| 阶段 | 计划 | 实际 |
|---|---|---|
| 1 准备 | 2 min | ___ |
| 2 实施 | 5 min | ___ |
| 3 验证 | 15 min | ___ |
| 4 提交 | 5 min | ___ |
| **合计** | **22 min** | ___ |
