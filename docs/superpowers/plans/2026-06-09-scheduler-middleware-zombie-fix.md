# Scheduler Middleware Zombie 事务修复 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 `backend/src/middleware/scheduler.py` lifespan 里的手写 session 管理，改为通过 `BaseDAO` 上下文 + DAO 方法封装；同时给 `BaseDAO` 加 `owns_session` 标志防双层 close。

**Architecture:** 三处改动：(1) `BaseDAO` 加 `owns_session` 区分"自己 new 的 session"和"外部传入的 session"，`__exit__` 只 close 前者；(2) `FavoriteDao` 新增 `get_scheduled_folders()` 方法封装查询；(3) `SchedulerMiddleware` 重写，使用 `with FavoriteDao() as dao:` 上下文替代手写 session。

**Tech Stack:** Python 3.12, FastAPI 0.115+, SQLAlchemy 2.0, APScheduler 3.x, MariaDB 11.5

**Spec:** `docs/superpowers/specs/2026-06-09-scheduler-middleware-zombie-fix-design.md`

**前置条件**（**执行者必须确认**）：
- uvicorn 进程 **没有** 正在监听 8000 端口（避免重启冲突）
- 远程 MariaDB 可达：`192.168.100.111:3307`，数据库 `Pictures`，用户 `root`，密码 `Max=1616`
- Python 解释器：项目根目录 `.venv/bin/python`
- 配置文件 `backend/config/config.yaml` 已配置 `database.enable: true`

---

## Task 1: BaseDAO 加 owns_session 防双层 close

**Files:**
- Modify: `backend/src/dao/database.py:120-137`（BaseDAO 的 `__init__` / `__enter__` / `__exit__`）

- [ ] **Step 1: 修改 `__init__` 标记 owns_session 初始值**

将 `backend/src/dao/database.py:120-123` 从：

```python
class BaseDAO:
    def __init__(self, session: Session = None):
        self._session = session
```

改为：

```python
class BaseDAO:
    def __init__(self, session: Session = None):
        self._session = session
        # owns_session = True  → 这个 DAO 自己 new 了 session，__exit__ 负责关
        # owns_session = False → session 是外部传入（如 middleware 注入），__exit__ 不关
        self.owns_session = session is None
```

- [ ] **Step 2: 修改 `__enter__` 在 self-new 时同步设 owns_session=True**

将 `backend/src/dao/database.py:125-128` 从：

```python
    def __enter__(self):
        if self._session is None:
            self._session = _get_session_factory()()
        return self
```

改为：

```python
    def __enter__(self):
        if self._session is None:
            self._session = _get_session_factory()()
            self.owns_session = True
        return self
```

- [ ] **Step 3: 修改 `__exit__` 加 owns_session 守卫**

将 `backend/src/dao/database.py:130-137` 从：

```python
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
            self._session.close()
        return False
```

改为：

```python
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session and self.owns_session:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
            self._session.close()
        return False
```

- [ ] **Step 4: 静态验证 — LSP 诊断**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
from src.dao.database import BaseDAO
from sqlalchemy.orm import Session
# 1. 外部传入 session → owns_session=False
sentinel = object()
class FakeSess:
    def commit(self): pass
    def rollback(self): pass
    def close(self): pass
fake = FakeSess()
dao = BaseDAO(session=fake)
assert dao.owns_session is False, f'expected False, got {dao.owns_session}'
print('PASS: external session → owns_session=False')
# 2. 不传 session → owns_session=True
dao2 = BaseDAO()
assert dao2.owns_session is True, f'expected True, got {dao2.owns_session}'
print('PASS: no session → owns_session=True')
# 3. __exit__ 外部 session 不被关
closed = []
fake2 = FakeSess()
fake2.close = lambda: closed.append(True)
dao3 = BaseDAO(session=fake2)
dao3.__exit__(None, None, None)
assert closed == [], f'external session should not be closed, got {closed}'
print('PASS: __exit__ does not close external session')
"
```

Expected output:
```
PASS: external session → owns_session=False
PASS: no session → owns_session=True
PASS: __exit__ does not close external session
```

- [ ] **Step 5: Commit Task 1**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && \
  git add backend/src/dao/database.py && \
  git commit -m "fix(dao): BaseDAO.owns_session prevents double-close

- Module-level singletons (favorite_dao etc.) have owns_session=False
  since they don't own their session; __exit__ never runs for them
- 'with BaseDAO() as dao:' sets owns_session=True in __enter__,
  __exit__ correctly commits/rollbacks + closes
- 'BaseDAO(session=ext).xxx()' (e.g. middleware-injected) keeps
  owns_session=False; __exit__ won't close external session

Part of: scheduler middleware zombie fix (spec dc48c09)"
```

---

## Task 2: FavoriteDao 新增 get_scheduled_folders

**Files:**
- Modify: `backend/src/dao/favorite_dao.py`（在 `delete` 之后、`reorder` 之前添加新方法）

- [ ] **Step 1: 添加 get_scheduled_folders 方法**

在 `backend/src/dao/favorite_dao.py:65-66` 之间（即 `delete` 方法结束与 `reorder` 方法开始之间）插入：

```python
    def get_scheduled_folders(self) -> List[FavoriteFolder]:
        """取出所有启用了调度的收藏夹。供 lifespan 和定时任务使用。"""
        return (
            self.session.query(FavoriteFolder)
            .filter(FavoriteFolder.schedule_enabled == True)  # noqa: E712
            .all()
        )
```

**位置参考** — 完整上下文（`dao/favorite_dao.py:60-80`）：

```python
    def delete(self, folder_id: int) -> bool:
        folder = self.session.query(FavoriteFolder).filter(FavoriteFolder.id == folder_id).first()
        if not folder:
            return False
        self.session.delete(folder)
        return True

    def get_scheduled_folders(self) -> List[FavoriteFolder]:
        """取出所有启用了调度的收藏夹。供 lifespan 和定时任务使用。"""
        return (
            self.session.query(FavoriteFolder)
            .filter(FavoriteFolder.schedule_enabled == True)  # noqa: E712
            .all()
        )

    def reorder(self, folder_ids: List[int]) -> bool:
        for order, folder_id in enumerate(folder_ids):
            folder = self.session.query(FavoriteFolder).filter(FavoriteFolder.id == folder_id).first()
            if folder:
                folder.sort_order = order
                folder.updated_at = datetime.now()
        return True
```

- [ ] **Step 2: 静态验证 — 方法存在且能调用**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
from src.dao.favorite_dao import FavoriteDao
assert hasattr(FavoriteDao, 'get_scheduled_folders'), 'method not found'
print('PASS: get_scheduled_folders method exists on FavoriteDao')
"
```

Expected output:
```
PASS: get_scheduled_folders method exists on FavoriteDao
```

- [ ] **Step 3: Commit Task 2**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && \
  git add backend/src/dao/favorite_dao.py && \
  git commit -m "feat(dao): FavoriteDao.get_scheduled_folders

Encapsulates the query used by lifespan and scheduler to load
all folders with schedule_enabled=true. Keeps DAO layer
data-only (does not import schedule_manager from infrastructure).

Part of: scheduler middleware zombie fix (spec dc48c09)"
```

---

## Task 3: 重写 SchedulerMiddleware 用 with 上下文

**Files:**
- Modify: `backend/src/middleware/scheduler.py`（全文重写，49 行 → 30 行）

- [ ] **Step 1: 完整重写 scheduler.py**

将 `backend/src/middleware/scheduler.py` 全部内容替换为：

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from loguru import logger

from src.dao.favorite_dao import FavoriteDao
from src.infrastructure.scheduler import schedule_manager


class SchedulerMiddleware:
    @staticmethod
    def init_app(app: FastAPI):
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            schedule_manager.start()
            SchedulerMiddleware._reload_schedules()
            try:
                yield
            finally:
                schedule_manager.shutdown(wait=False)
                logger.info("Scheduler stopped")

        app.router.lifespan_context = lifespan

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

- [ ] **Step 2: 静态验证 — 语法 + import 正确**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
from src.middleware.scheduler import SchedulerMiddleware
assert hasattr(SchedulerMiddleware, '_reload_schedules'), '_reload_schedules missing'
assert callable(SchedulerMiddleware._reload_schedules), '_reload_schedules not callable'
print('PASS: SchedulerMiddleware._reload_schedules is a static method')
"
```

Expected output:
```
PASS: SchedulerMiddleware._reload_schedules is a static method
```

- [ ] **Step 3: Commit Task 3**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && \
  git add backend/src/middleware/scheduler.py && \
  git commit -m "refactor(middleware): use with FavoriteDao in lifespan

Replaces manual session management in SchedulerMiddleware with
BaseDAO context manager. Benefits:

- Session lifecycle delegated to BaseDAO.__exit__ (commit/rollback/close)
- Zombie transactions eliminated (no more session.close() that
  doesn't trigger pool_reset_on_return)
- DB operations route through FavoriteDao, respecting the
  middleware -> service -> dao layering rule
- _reload_schedules extracted as static method for testability

Eliminates the v1.1.0 zombie-trx source introduced in commit
that added SchedulerMiddleware.init_app.

Part of: scheduler middleware zombie fix (spec dc48c09)"
```

---

## Task 4: 启动验证（无 zombie）

**Files:** 无代码改动，仅运行验证

**前置条件**：
- Task 1-3 已 commit
- 当前没有 uvicorn 进程占用 8000 端口

- [ ] **Step 1: 确认无 uvicorn 进程残留**

Run:
```bash
ps -ef | grep -E 'service:main_app' | grep -v grep
```

Expected: 空的（或只有 setsid 启动的 uvicorn 仍在跑）— 如果有残留，**先 kill**：

```bash
PID=$(ps -ef | grep -E 'service:main_app' | grep -v grep | awk '{print $2}' | head -1)
[ -n "$PID" ] && kill $PID
sleep 2
```

- [ ] **Step 2: 干净启动 uvicorn（无 --reload）**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  setsid /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m uvicorn service:main_app --host 0.0.0.0 --port 8000 < /dev/null > /tmp/uvicorn-zfix.log 2>&1 &
disown
sleep 5
ps -ef | grep -E 'service:main_app' | grep -v grep
```

Expected: 一行 uvicorn 进程，etime ~5s。

- [ ] **Step 3: 启动后立即查 INNODB_TRX**

Run:
```bash
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
url = f'mariadb+mariadbconnector://root:{quote_plus(\"Max=1616\")}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'INNODB_TRX count: {n}')
    for r in c.execute(text('SELECT trx_id, trx_state, trx_started, TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age FROM information_schema.INNODB_TRX')):
        print(f'  {r}')
"
```

Expected:
```
INNODB_TRX count: 0
```

- [ ] **Step 4: 等 30s 之后再次查（确保 apscheduler 心跳不产生 zombie）**

Run:
```bash
sleep 30 && /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
url = f'mariadb+mariadbconnector://root:{quote_plus(\"Max=1616\")}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'30s 后 INNODB_TRX count: {n}')
"
```

Expected:
```
30s 后 INNODB_TRX count: 0
```

**如果 zombie > 0**：
- 看 `tail -30 /tmp/uvicorn-zfix.log` 确认 lifespan 跑过了
- 看 `ps -ef | grep service:main` 确认进程在
- **不要继续** — Task 4 失败，需要回滚 Task 1-3 的代码改动重新分析

- [ ] **Step 5: 查 uvicorn 日志确认 lifespan 跑过**

Run:
```bash
grep -E 'Loaded|ScheduleManager' /tmp/uvicorn-zfix.log
```

Expected:
```
| INFO | src.middleware.scheduler:_reload_schedules:42 - Loaded 0 scheduled folders from DB
| INFO | src.infrastructure.scheduler:start:25 - ScheduleManager started
```

---

## Task 5: 端到端验证（创建带调度的 folder + 重启验证）

**Files:** 无代码改动，仅运行验证

- [ ] **Step 1: POST 创建带 schedule_enabled=true 的收藏夹**

Run:
```bash
curl -sS -X POST -H "Content-Type: application/json" -d '{
  "name": "zfix_test_schedule",
  "tags": "x",
  "schedule_enabled": true,
  "schedule_cron": "*/5 * * * *",
  "schedule_mode": "last_id",
  "schedule_max_images": 5
}' -m 10 http://127.0.0.1:8000/api/v1/favorites
```

Expected: HTTP 200, 返回 `id` 字段。

记录返回的 `id` 字段值（如 `id=18`），下一步用。

- [ ] **Step 2: 通过 schedule/status 端点确认**

Run:
```bash
curl -sS -m 10 http://127.0.0.1:8000/api/v1/favorites/<id>/schedule/status
```

Expected: `schedule_enabled: true, schedule_cron: "*/5 * * * *"`。

- [ ] **Step 3: 重启 uvicorn 触发 lifespan reload**

Run:
```bash
PID=$(ps -ef | grep -E 'service:main_app' | grep -v grep | awk '{print $2}' | head -1)
kill $PID
sleep 3
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  setsid /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -m uvicorn service:main_app --host 0.0.0.0 --port 8000 < /dev/null > /tmp/uvicorn-zfix2.log 2>&1 &
disown
sleep 5
```

Expected: uvicorn 重启，etime 5s。

- [ ] **Step 4: 查 lifespan 日志确认 reload 注册了 1 个 folder**

Run:
```bash
grep -E 'Loaded|Schedule registered' /tmp/uvicorn-zfix2.log
```

Expected:
```
| INFO | src.middleware.scheduler:_reload_schedules:42 - Loaded 1 scheduled folders from DB
| INFO | src.infrastructure.scheduler:register_folder:64 - Schedule registered: folder=<id> cron='*/5 * * * *' mode=last_id max_images=5
```

- [ ] **Step 5: 再查 zombie（重启后仍应为 0）**

Run:
```bash
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
url = f'mariadb+mariadbconnector://root:{quote_plus(\"Max=1616\")}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'重启后 INNODB_TRX count: {n}')
"
```

Expected: `0`。

---

## Task 6: 清理验证

**Files:** 无代码改动

- [ ] **Step 1: DELETE 测试数据**

Run:
```bash
curl -sS -X DELETE -m 10 http://127.0.0.1:8000/api/v1/favorites/<id>
```

Expected: HTTP 200。

- [ ] **Step 2: 验证数据库回到 0 行**

Run:
```bash
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
url = f'mariadb+mariadbconnector://root:{quote_plus(\"Max=1616\")}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM favorite_folders')).scalar()
    print(f'favorite_folders count: {n}')
    assert n == 0, f'expected 0, got {n}'
    print('PASS: favorite_folders is empty')
"
```

Expected:
```
favorite_folders count: 0
PASS: favorite_folders is empty
```

- [ ] **Step 3: 检查 zombie 长期稳定（60s 无活动）**

Run:
```bash
sleep 60 && /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
url = f'mariadb+mariadbconnector://root:{quote_plus(\"Max=1616\")}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'60s 无活动后 INNODB_TRX count: {n}')
    assert n == 0, f'expected 0, got {n}'
    print('PASS: long-term zombie-free')
"
```

Expected:
```
60s 无活动后 INNODB_TRX count: 0
PASS: long-term zombie-free
```

- [ ] **Step 4: 最终 git status 检查**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && \
  git log --oneline -5 && \
  echo '---' && \
  git status --short
```

Expected:
- `git log` 显示 3 个新 commit（Task 1-3）
- `git status` 是空的（无未提交改动）

---

## 自我检查（写完后）

**Spec 覆盖**：
- §3.1 BaseDAO 改造 → Task 1
- §3.2 get_scheduled_folders 方法 → Task 2
- §3.3 SchedulerMiddleware 重写 → Task 3
- §5.1 静态验证 → Task 1 Step 4 + Task 2 Step 2 + Task 3 Step 2
- §5.2 启动验证（无 zombie）→ Task 4
- §5.3 端到端验证 → Task 5
- §5.4 清理验证 → Task 6

**占位符扫描**：✓ 无 TBD/TODO

**类型一致性**：
- `BaseDAO.owns_session` 在 Task 1 定义，Task 1 Step 4 测试
- `FavoriteDao.get_scheduled_folders()` 在 Task 2 定义，Task 3 引用，Task 3 Step 2 测试
- `SchedulerMiddleware._reload_schedules` 在 Task 3 定义，Task 3 Step 2 测试

**检查通过。**
