# 收藏夹调度 Lifespan Zombie 事务修复 — 设计

**日期**：2026-06-09
**状态**：已批准（待实施）
**作者**：Sisyphus
**范围**：3 个文件，最小改动

---

## 1. 背景

`backend/src/middleware/scheduler.py` 在 v1.1.0 新增，是 FastAPI lifespan 启动时从 DB 加载已启用调度的收藏夹、注册到 APScheduler 的代码。

### 1.1 实证问题（2026-06-09 复现）

启动后 `INFORMATION_SCHEMA.INNODB_TRX` 出现 idle-in-transaction 长寿命事务：

```
(33565, 'RUNNING', started=2026-06-09 15:02:57, thread=2582, age=500+s)
```

外加用户报告：

- `POST /api/v1/favorites` 报 `PendingRollbackError` → 500
- 远程 MariaDB `Pictures.favorite_folders` 永远 0 行
- 前端展示的收藏夹数据是本地 SQLite 残留（5 条 v1.0.x 时代的数据）

### 1.2 根因

`scheduler.py:19-40` 用 `_get_session_factory()()` 创建 session，`session.close()` **不会**触发 SQLAlchemy 的 `pool_reset_on_return`（pool reset 只在 session 被连接池回收时触发，**close session 不等于还池**），导致事务半开。

**同时**：codebase 里有两套 session 生命周期管理（`RequestSessionMiddleware` + `BaseDAO`），`BaseDAO.__exit__` 无条件 `close` 传入的 session，可能跟 middleware 重复 close。

---

## 2. 目标 & 范围

### 2.1 目标

1. 消除 `scheduler.py` lifespan 里的手写 session 管理
2. 数据库操作走 `FavoriteDao`（符合分层：middleware → service → dao）
3. 防止 `BaseDAO.__exit__` 重复 close 外部传入的 session（修 zombie 隐患）

### 2.2 范围内（只动 3 个文件）

- `backend/src/middleware/scheduler.py` — 重写
- `backend/src/dao/favorite_dao.py` — 新增 `get_scheduled_folders()` 方法
- `backend/src/dao/database.py` — 修 `BaseDAO` 加 `owns_session` 防双层 close

### 2.3 范围外（保持现状）

- `RequestSessionMiddleware` 不动
- `BaseDAO.session` 懒加载 fallback 不动
- `services/favorite_scheduler.py`（后台定时任务，独立行为）
- `api/v1/favorites.py` 现有 `favorite_dao.xxx()` 调用
- 单元测试（项目当前没有 scheduler 中间件的测试）

### 2.4 设计权衡

用户原话「按 C 修复」「写得优雅一些」「用 dao」。本设计在「C 类问题（session 生命周期混乱 + scheduler 手写管理）」范畴内做到最小但优雅的修复，**不**做大改（如干掉 ContextVar、删除模块级 DAO 单例）。ContextVar 跨 task 的更彻底修复留作未来 PR。

---

## 3. 设计

### 3.1 BaseDAO 改造（`backend/src/dao/database.py:120-146`）

**改动**：加 `owns_session: bool` 属性，`__exit__` 只在 `owns_session=True` 时关闭 session。

```python
class BaseDAO:
    def __init__(self, session: Session = None):
        self._session = session
        # owns_session = True  → 这个 DAO 自己 new 了 session，__exit__ 负责关
        # owns_session = False → session 是外部传入（如 middleware 注入），__exit__ 不关
        self.owns_session = session is None

    def __enter__(self):
        if self._session is None:
            self._session = _get_session_factory()()
            self.owns_session = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session and self.owns_session:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
            self._session.close()
        return False
```

**关键行为变化**：

| 场景 | `owns_session` | `__exit__` 行为 |
|---|---|---|
| `with FavoriteDao() as dao:` | True（enter 时设置） | commit/rollback + close ✓ |
| `favorite_dao.get_all()`（模块级单例，无 `with`） | False | 不走 `__exit__`（不调用） |
| `BaseDAO(session=middleware_session).get_all()` | False（init 时设置） | 不关 session ✓ |

### 3.2 FavoriteDao 新增方法（`backend/src/dao/favorite_dao.py`）

**改动**：新增 `get_scheduled_folders()` 方法。

```python
def get_scheduled_folders(self) -> list[FavoriteFolder]:
    """取出所有启用了调度的收藏夹。供 lifespan 和定时任务使用。"""
    return (
        self.session.query(FavoriteFolder)
        .filter(FavoriteFolder.schedule_enabled == True)  # noqa: E712
        .all()
    )
```

**为什么不直接 import schedule_manager？** —— 违反分层（DAO 不应依赖基础设施层）。DAO 只负责**取数据**，**怎么注册**由调用方决定。

### 3.3 SchedulerMiddleware 重写（`backend/src/middleware/scheduler.py`）

**改动**：从 49 行嵌套 try/finally 重写为 30 行平铺 `with` 上下文。

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

**优雅点**：
- 数据库操作走 `FavoriteDao`，符合分层
- `with FavoriteDao() as dao:` 自动 commit/rollback/close，**无 zombie 风险**
- `_reload_schedules` 抽成静态方法，可独立测试
- lifespan 主体只剩 `start → reload → yield → shutdown` 四步
- reload 失败的 `except` 缩小到 reload 范围（不影响 scheduler 生命周期）

---

## 4. 数据流

### 4.1 启动时数据流

```
FastAPI lifespan
    └─> SchedulerMiddleware.lifespan
        ├─> schedule_manager.start()           # APScheduler 启动
        ├─> SchedulerMiddleware._reload_schedules()
        │       └─> with FavoriteDao() as dao:        # BaseDAO 创建 session
        │           ├─> dao.get_scheduled_folders()   # SELECT WHERE schedule_enabled=true
        │           └─> __exit__ → commit + close     # 走 pool_reset_on_return
        ├─> schedule_manager.reload_from_db(folder_dicts)
        └─> yield   # 等待 app 关闭
                └─> schedule_manager.shutdown(wait=False)
```

### 4.2 错误处理矩阵

| 场景 | 行为 |
|---|---|
| DB 不可达 | `with` 块触发 rollback + close；外层 `except` 记录日志并 `return`（不阻塞 app 启动） |
| `schedule_cron` 非法 | `reload_from_db` 内部已有 try/except 跳过该 folder |
| `schedule_manager.start()` 抛错 | lifespan 直接抛 → app 启动失败（符合预期） |
| lifespan 被取消 | `try/finally` → `shutdown` 兜底 |

---

## 5. 验证步骤

### 5.1 静态验证

- `lsp_diagnostics` 在 3 个改动的文件上无 error
- `git diff --stat` 仅触及 3 个文件

### 5.2 启动验证（无 zombie）

```bash
# 1. 重启 uvicorn（干净）
kill <uvicorn_pid>
cd backend && setsid .venv/bin/python -m uvicorn service:main_app --host 0.0.0.0 --port 8000 < /dev/null > /tmp/uvicorn.log 2>&1 &
disown
sleep 5

# 2. 查 zombie
python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
url = f'mariadb+mariadbconnector://root:{quote_plus(\"Max=1616\")}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'INNODB_TRX: {n}')  # 期望: 0
"

# 3. 30s 后再查
sleep 30
# 期望: 仍然 0
```

### 5.3 端到端验证

```bash
# 1. POST 创建带 schedule_enabled=true 的收藏夹
curl -X POST -H "Content-Type: application/json" -d '{
  "name": "test_schedule", "tags": "x", "schedule_enabled": true,
  "schedule_cron": "*/5 * * * *", "schedule_mode": "last_id"
}' http://127.0.0.1:8000/api/v1/favorites
# 期望: HTTP 200, id 正常

# 2. 重启 uvicorn（触发 lifespan reload）
# 3. 查 schedule_manager.get_all_jobs()（通过 /api/v1/favorites/<id>/schedule/status）
curl http://127.0.0.1:8000/api/v1/favorites/<id>/schedule/status
# 期望: 看到 schedule_enabled=true, schedule_cron 正确
```

### 5.4 清理验证

- 测试数据全部 DELETE 掉
- `favorite_folders` 行数 = 0
- `INNODB_TRX` 长时间（> 60s）保持 0

---

## 6. 不在本设计范围内（未来 PR 候选）

1. **`RequestSessionMiddleware` 用 `request.state` 替代 ContextVar** —— 解决 ContextVar 跨 asyncio task 不共享的根本问题
2. **`BaseDAO.session` 懒加载 fallback 改为报错** —— 强制所有 DAO 调用方用 `with` 上下文
3. **删除模块级 DAO 单例** —— 改为工厂方法或 request-scoped
4. **`services/favorite_scheduler.py` 同样改用 `with` 上下文**（其内部 14 处 `favorite_dao.xxx()` 调用）
5. **单元测试**（项目当前没有覆盖 scheduler 中间件）

---

## 7. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| `owns_session` 语义搞反，破坏现有 `with YandeDataRepository()` 行为 | 低 | 中 | 5.1 静态验证 + 5.2 启动验证 |
| `get_scheduled_folders` 查询有 bug 导致 lifespan 启动失败 | 低 | 高 | 5.2 启动验证 + `try/except` 不阻塞 app |
| 漏改某处导致 zombie 仍然产生 | 低 | 中 | 5.2 + 5.4 zombie 监控 |
| BaseDAO 改造影响 `favorite_dao.xxx()` 单例调用 | **极低** | — | `__exit__` 不被调用 = 行为不变 |

---

## 8. 实施时间估算

| 任务 | 估算 |
|---|---|
| 改 BaseDAO + 加 owns_session | 5 分钟 |
| 加 FavoriteDao.get_scheduled_folders | 3 分钟 |
| 重写 scheduler.py | 5 分钟 |
| 5.1 静态验证 | 2 分钟 |
| 5.2 + 5.3 启动 + e2e 验证 | 15 分钟 |
| **总计** | **30 分钟** |
