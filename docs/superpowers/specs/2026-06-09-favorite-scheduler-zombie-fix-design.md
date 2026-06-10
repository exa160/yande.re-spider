# 收藏夹定时任务 Zombie 事务修复 — 设计

**日期**：2026-06-09
**状态**：已批准（待实施）
**作者**：Sisyphus
**范围**：1 个文件，最小改动

---

## 1. 背景

`backend/src/services/favorite_scheduler.py` 里的 `run_folder_schedule()` 是 v1.1.0 新增的 APScheduler 任务。该任务通过 `asyncio.create_task()` 在 **asyncio 任务上下文**（不是 Request 上下文）执行，期间调用 3 处 `favorite_dao.update()`。

### 1.1 实证问题（2026-06-09 复现）

启动 scheduler 任务，**`INNODB_TRX` 必然出现 idle-in-transaction zombie**：

| 上下文 | zombie 数 |
|---|---|
| HTTP `POST /api/v1/favorites`（走 Request 上下文） | 0 ✓ |
| HTTP `POST /api/v1/favorites/{id}/schedule/trigger`（走 asyncio 任务上下文） | 1 ⚠️ |
| cron 触发 `run_folder_schedule`（走 asyncio 任务上下文） | 1 ⚠️ |

### 1.2 根因（实证确认）

`run_folder_schedule` 里的 3 处 `favorite_dao.update()` 走 `BaseDAO.session` 懒加载（`database.py:139-146`）：

1. `asyncio.create_task(run_folder_schedule)` 在新 asyncio task 里启动
2. `ContextVar _request_session` **跨 asyncio task 不共享**（`request.state` 才共享）→ 新 task 里 `_request_session.get() == None`
3. `RequestSessionMiddleware.get_session()` 看 None → 自己 `_get_session_factory()()` new 一个 session
4. `favorite_dao.update()` 内部 `self.session.flush()` 写 UPDATE 到 MySQL，**但不 commit**
5. `run_folder_schedule` 结束后这个 session **永远不被关闭**（模块级单例 `favorite_dao = FavoriteDao()` 不走 `with` 上下文 → `BaseDAO.__exit__` 永远不被调）
6. 连接在 pool 里 idle 但事务半开 → MariaDB 端 `INNODB_TRX` 永久 RUNNING

**为什么 Request 上下文没事**：

- `RequestSessionMiddleware.dispatch` 创建 session + 注入 ContextVar（dispatch 那个 task）
- endpoint 调 `favorite_dao.xxx()` 走懒加载拿到 dispatch 的 session
- dispatch finally `commit() + close()` 正确清掉事务
- **dispatch finally 跟 scheduler 任务的 session 不是同一个**（不同 task），commit 帮不了 scheduler 留下的 zombie

### 1.3 用户确认的策略

> "在 fastapi 上下文范围内的单例应该不受影响，在中间件定时任务中的单例才应该改为 with 使用"

**严格按此策略**：**只改 `services/favorite_scheduler.py`**。

---

## 2. 目标 & 范围

### 2.1 目标

消除 `run_folder_schedule` 在 asyncio 任务上下文执行时产生的 zombie 事务。

### 2.2 范围内（只动 1 个文件）

- `backend/src/services/favorite_scheduler.py` — 把 3 处 `favorite_dao.xxx()` 调用改用 `with FavoriteDao() as dao:` 上下文

### 2.3 范围外（保持现状）

- `api/v1/favorites.py` 里 6 处 `favorite_dao.xxx()` 调用（Request 上下文，dispatch 已 commit，**实证 0 zombie**）
- `services/favorites.py` 里 `favorite_dao.xxx()` 调用（被 Request 上下文 endpoint 调用，dispatch 已 commit，**实证 0 zombie**）
- `BaseDAO`、`RequestSessionMiddleware` 本身（上一轮已修）
- `services/favorite_scheduler.py` 里 `with YandeDataRepository() as repo:`（**已经用 with 上下文**，无需改）

---

## 3. 设计

### 3.1 改动结构

在 `run_folder_schedule` 顶部加一个外层 `with FavoriteDao() as dao:`，把 3 处 `favorite_dao.xxx()` 调用**全部**替换为 `dao.xxx()`。这样：

- 整个 `run_folder_schedule` 执行期间**共享一个 session**
- `__exit__` 走 `commit/rollback/close`，**事务被正确关闭**
- 不会产生 zombie

### 3.2 重写后的代码结构

```python
async def run_folder_schedule(folder_id: int) -> dict:
    async with _schedule_semaphore:
        with FavoriteDao() as dao:                       # ← 关键: 外层 with
            folder = dao.get_by_id(folder_id)
            if not folder: ...
            if not folder.schedule_enabled: ...

            dao.update(folder_id, last_schedule_status="running", ...)

            stats = {...}
            start = time.monotonic()

            try:
                # ... 主要逻辑 (内含 with YandeDataRepository() as repo: 块)
                
                dao.update(folder_id, last_schedule_status="success", ...)
                return stats
            except Exception as e:
                dao.update(folder_id, last_schedule_status="failed", ...)
                return stats
```

### 3.3 为什么不保留 3 个独立 `with` 块

理论上可以写 3 个 `with FavoriteDao() as dao:`，但**外层 1 个 `with` 更简洁**：
- 整个 task 共享一个 session
- 资源使用更少（pool 里少占一个连接）
- 出错时 `__exit__` 统一 rollback

### 3.4 与现有 `YandeDataRepository` with 块的关系

`run_folder_schedule` 内部已经 2 处 `with YandeDataRepository() as repo:`（line 56, 100）。这 2 个 `with` 块**独立**于外层 `with FavoriteDao() as dao:`，**互不影响**：

- `YandeDataRepository` 走 `BaseDAO.__enter__` → 检查 `_session is None` → 是 None → `_get_session_factory()()` new 一个**独立的 session**
- 这个独立 session 跟外层 `FavoriteDao` 的 session **不共享事务**
- `YandeDataRepository.__exit__` 走 `commit/rollback/close`，**正确清掉**自己那个 session
- 跟外层 `FavoriteDao.__exit__` 互不干扰

---

## 4. 数据流

### 4.1 修复后 run_folder_schedule 数据流

```
asyncio.create_task(run_folder_schedule(folder_id))
    └─> with FavoriteDao() as dao:               # BaseDAO 创建 session 1
        ├─> dao.get_by_id(folder_id)              # SELECT
        ├─> dao.update(folder_id, "running", ...) # UPDATE
        ├─> with YandeDataRepository() as repo:   # BaseDAO 创建 session 2 (独立)
        │       └─> ... 查 yande_data ...
        ├─> for item in items:
        │       with YandeDataRepository() as repo: # session 3, 4, 5... (独立)
        │           └─> ... upsert ...
        ├─> dao.update(folder_id, "success", ...) # UPDATE
        └─> __exit__ → commit + close session 1   # ← 关键: 正确清掉
```

### 4.2 错误处理

| 场景 | 行为 |
|---|---|
| DB 不可达（`dao.get_by_id` 抛 OperationalError） | 外层 `__exit__` 走 `rollback + close`；不阻塞 scheduler |
| `dao.update("running")` 后 try 块抛错 | 外层 `__exit__` 走 `rollback + close`（**包括**之前 flush 的 UPDATE 一起回滚） |
| `dao.update("failed")` 后正常返回 | 外层 `__exit__` 走 `commit + close`（UPDATE 提交）|
| `dao.update("success")` 后正常返回 | 同上 |
| inner `with YandeDataRepository()` 抛错 | 那个独立 session 自己回滚 + close；不影响外层 |

---

## 5. 验证步骤

### 5.1 静态验证

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
from src.services.favorite_scheduler import run_folder_schedule
import inspect
src = inspect.getsource(run_folder_schedule)
# 断言: 整段被 with FavoriteDao() as dao: 包住
assert 'with FavoriteDao() as dao:' in src, '外层 with 不在'
# 断言: 没有裸的 favorite_dao.xxx() 调用 (除了 __init__ 之外)
import re
# 排除 'from src.dao.favorite_dao import favorite_dao' 这一行
body = src.split('async def run_folder_schedule(folder_id: int) -> dict:', 1)[1]
# 检查不是 'with ... favorite_dao' 的调用
for m in re.finditer(r'(?<!with )(?<!from src\\.dao\\.favorite_dao import )favorite_dao\\.[a-z_]+\\(', body):
    print('  BARE CALL:', m.group())
print('PASS: all favorite_dao.xxx() inside with context')
"
```

### 5.2 启动验证

1. 干净启动 uvicorn
2. baseline zombie = 0
3. 30s 无活动后 zombie 仍然 0

### 5.3 端到端验证（核心）

1. 通过 API POST 一个 `schedule_enabled=true` 的 folder
2. baseline zombie = 0
3. 通过 API trigger 一次 `run_folder_schedule`
4. 立即查 zombie = **0**（修复目标）
5. 30s 后查 zombie 仍然 = **0**
6. 验证 scheduler 任务仍然能成功 enqueue 下载任务（`new_images > 0`）

### 5.4 清理验证

- DELETE 测试数据
- DB 回到 0 行
- 60s 无活动 zombie = 0

---

## 6. 不在本设计范围（未来 PR 候选）

1. **`api/v1/favorites.py` 现有 `favorite_dao.xxx()` 调用改 `with` 上下文** — 虽然 0 zombie，但风格更一致
2. **`services/favorites.py` 同上**
3. **彻底修 `RequestSessionMiddleware` + `BaseDAO.session` 懒加载** — 用 `request.state` 替代 ContextVar

---

## 7. 风险评估

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 外层 `with` 把"running"+"success" UPDATE 合并到同一事务，意图变化 | 低 | 低 | 5.3 验证 scheduler 仍能 enqueue |
| `YandeDataRepository` inner `with` 跟 outer `with` 交互产生 deadlock | 极低 | 中 | 5.3 验证任务成功 |
| 漏改某处导致 zombie 仍然产生 | 低 | 中 | 5.3 + 5.4 zombie 监控 |
| `BaseDAO.__exit__` 关闭 outer session 跟 inner `YandeDataRepository` 的 session 冲突 | **极低** | — | inner session 独立 new（__enter__ 检查 `_session is None`） |

---

## 8. 实施时间估算

| 任务 | 估算 |
|---|---|
| 重写 `run_folder_schedule` | 5 分钟 |
| 5.1 静态验证 | 2 分钟 |
| 5.2 + 5.3 + 5.4 启动/e2e/清理验证 | 15 分钟 |
| **总计** | **22 分钟** |
