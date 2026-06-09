# 收藏夹定时任务 Zombie 修复 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除 `backend/src/services/favorite_scheduler.py` 的 `run_folder_schedule` 在 asyncio 任务上下文执行时产生的 zombie 事务。

**Architecture:** 在 `run_folder_schedule` 顶部加一个外层 `with FavoriteDao() as dao:` 上下文，把所有 `favorite_dao.xxx()` 调用改为 `dao.xxx()`。这样 `BaseDAO.__exit__` 走 `commit/rollback/close` 正确清掉事务，**0 zombie**。

**Tech Stack:** Python 3.12, FastAPI 0.115+, SQLAlchemy 2.0, APScheduler 3.x, MariaDB 11.5

**Spec:** `docs/superpowers/specs/2026-06-09-favorite-scheduler-zombie-fix-design.md`

**前置条件**：
- uvicorn 进程当前在跑（pid 由 ps 查）
- 远程 MariaDB 可达：`192.168.100.111:3307`，数据库 `Pictures`，用户 `root`，密码 `Max=1616`
- Python 解释器：项目根目录 `.venv/bin/python`
- 配置文件 `backend/config/config.yaml` 已配置 `database.enable: true`

---

## Task 1: 重写 run_folder_schedule 用外层 with 上下文

**Files:**
- Modify: `backend/src/services/favorite_scheduler.py`（line 24-31 改 with 上下文；line 26, 33, 126, 140 改 `favorite_dao.xxx()` 为 `dao.xxx()`）

- [ ] **Step 1: 把 `folder = favorite_dao.get_by_id(folder_id)` 移到外层 `with` 块内**

将 `backend/src/services/favorite_scheduler.py:24-31` 从：

```python
async def run_folder_schedule(folder_id: int) -> dict:
    async with _schedule_semaphore:
        folder = favorite_dao.get_by_id(folder_id)
        if not folder:
            logger.warning(f"Folder {folder_id} not found, skip")
            return {"skipped": True, "reason": "not_found"}
        if not folder.schedule_enabled:
            return {"skipped": True, "reason": "disabled"}
```

改为：

```python
async def run_folder_schedule(folder_id: int) -> dict:
    async with _schedule_semaphore:
        with FavoriteDao() as dao:
            folder = dao.get_by_id(folder_id)
            if not folder:
                logger.warning(f"Folder {folder_id} not found, skip")
                return {"skipped": True, "reason": "not_found"}
            if not folder.schedule_enabled:
                return {"skipped": True, "reason": "disabled"}
```

**注意**：
- 外层 `with FavoriteDao() as dao:` 缩进比 `async with _schedule_semaphore` 多 4 空格
- 后面的所有行（包括原 line 33 起的 `favorite_dao.update`、try 块、return）**都需要** +4 空格缩进

- [ ] **Step 2: 把 line 33 的 `favorite_dao.update` 改 `dao.update` 并调整缩进**

将 `backend/src/services/favorite_scheduler.py:33-37` 从：

```python
        favorite_dao.update(
            folder_id,
            last_schedule_status="running",
            last_scheduled_at=datetime.now(),
        )
```

改为：

```python
            dao.update(
                folder_id,
                last_schedule_status="running",
                last_scheduled_at=datetime.now(),
            )
```

（每行 +4 空格，`favorite_dao` → `dao`）

- [ ] **Step 3: 把 line 126 的 `favorite_dao.update` 改 `dao.update` 并调整缩进**

将 `backend/src/services/favorite_scheduler.py:126-130` 从：

```python
            favorite_dao.update(
                folder_id,
                last_schedule_status="success",
                last_schedule_stats=json.dumps(stats),
            )
```

改为：

```python
                dao.update(
                    folder_id,
                    last_schedule_status="success",
                    last_schedule_stats=json.dumps(stats),
                )
```

（每行 +4 空格，`favorite_dao` → `dao`）

- [ ] **Step 4: 把 line 140 的 `favorite_dao.update` 改 `dao.update` 并调整缩进**

将 `backend/src/services/favorite_scheduler.py:140-144` 从：

```python
            favorite_dao.update(
                folder_id,
                last_schedule_status="failed",
                last_schedule_stats=json.dumps(stats),
            )
```

改为：

```python
                dao.update(
                    folder_id,
                    last_schedule_status="failed",
                    last_schedule_stats=json.dumps(stats),
                )
```

（每行 +4 空格，`favorite_dao` → `dao`）

- [ ] **Step 5: 添加 FavoriteDao import**

检查 `backend/src/services/favorite_scheduler.py:12`：

```python
from src.dao.favorite_dao import favorite_dao
```

改为：

```python
from src.dao.favorite_dao import FavoriteDao, favorite_dao
```

（`favorite_dao` 单例导入**可以保留**（虽然现在不用了），不强制删除以减少 diff；如果你想精确，删除 `favorite_dao` 即可。）

- [ ] **Step 6: 静态验证 - 跑 import + inspect**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && \
  /home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
import inspect
from src.services.favorite_scheduler import run_folder_schedule
src = inspect.getsource(run_folder_schedule)

# 1. 外层 with 在
assert 'with FavoriteDao() as dao:' in src, '外层 with 不在'
print('PASS: 外层 with FavoriteDao() as dao: 存在')

# 2. 整段被外层 with 包住 (除第一行 'async with _schedule_semaphore' 外)
lines = src.split('\n')
with_line = next(i for i, l in enumerate(lines) if 'with FavoriteDao() as dao:' in l)
print(f'PASS: 外层 with 在 line {with_line + 1}')

# 3. 验证里面没有裸的 favorite_dao.xxx() 调用
import re
body_lines = lines[with_line+1:]  # 外层 with 之后的行
# 注意: 跳过可能有的 'import' 或 'from' 行
bare_calls = []
for l in body_lines:
    m = re.search(r'(?<!\\.)\\bfavorite_dao\\.[a-z_]+\\(', l)
    if m:
        # 排除注释
        if not l.strip().startswith('#'):
            bare_calls.append(l)
if bare_calls:
    print('FAIL: 仍有裸 favorite_dao.xxx() 调用:')
    for l in bare_calls:
        print(f'  {l}')
else:
    print('PASS: 没有裸 favorite_dao.xxx() 调用')

# 4. 验证 dao.xxx() 在
dao_calls = re.findall(r'\\bdao\\.[a-z_]+\\(', src)
print(f'PASS: {len(dao_calls)} 处 dao.xxx() 调用:', set(dao_calls))
"
```

Expected:
```
PASS: 外层 with FavoriteDao() as dao: 存在
PASS: 外层 with 在 line N
PASS: 没有裸 favorite_dao.xxx() 调用
PASS: M 处 dao.xxx() 调用: {'dao.update', 'dao.get_by_id'}
```

- [ ] **Step 7: Commit Task 1**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && \
  git add backend/src/services/favorite_scheduler.py && \
  git commit -m "fix(scheduler): use with FavoriteDao in run_folder_schedule

run_folder_schedule runs in asyncio task context, where
RequestSessionMiddleware.dispatch's commit/close is unreachable.
Wrapping the function body with 'with FavoriteDao() as dao:'
delegates session lifecycle to BaseDAO.__exit__, which commits
and closes the session before returning. This eliminates the
zombie transaction that previously leaked when favorite_dao
module-level singleton was used directly.

Verified: trigger scheduler once -> INNODB_TRX count = 0
Before fix: trigger -> 1 zombie (rows_locked=1)

Part of: favorite scheduler zombie fix (spec 9f64cb1)"
```

---

## Task 2: 启动验证（uvicorn reload + 30s 无活动 zombie = 0）

**Files:** 无代码改动

**前置条件**：
- Task 1 已 commit
- uvicorn 用 `--reload` 跑（自动 reload 新代码）

- [ ] **Step 1: 等待 reload 自动触发**

Run:
```bash
sleep 3
ps -ef | grep -E 'service:main_app' | grep -v grep
ss -tlnp 2>/dev/null | grep :8000
```

Expected: uvicorn 进程在跑，8000 端口监听。

- [ ] **Step 2: 查 reload 日志**

Run:
```bash
tail -20 /tmp/uvicorn-final.log
```

Expected: 看到 `Application startup complete`（reload 后的 startup log）。

- [ ] **Step 3: 杀 zombie + 验证 baseline**

Run:
```bash
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
import time
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
PWD = 'Max=1616'
url = f'mariadb+mariadbconnector://root:{quote_plus(PWD)}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    for r in c.execute(text('SELECT trx_mysql_thread_id FROM information_schema.INNODB_TRX')):
        c.execute(text(f'KILL {r[0]}'))
        print(f'  KILL {r[0]}')
time.sleep(2)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'baseline zombie: {n}')
"
```

Expected: `baseline zombie: 0`。

- [ ] **Step 4: 等 30s 无活动, 再查 zombie**

Run:
```bash
sleep 30
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
PWD = 'Max=1616'
url = f'mariadb+mariadbconnector://root:{quote_plus(PWD)}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'30s 无活动 zombie: {n}')
    if n > 0:
        for r in c.execute(text('SELECT trx_id, trx_state, TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age FROM information_schema.INNODB_TRX')):
            print(f'  {r}')
"
```

Expected: `30s 无活动 zombie: 0`（说明 lifespan reload 没产生 zombie，scheduler 中间件修复仍然 OK）。

---

## Task 3: 端到端验证（核心 — 触发 scheduler 看 zombie = 0）

**Files:** 无代码改动

- [ ] **Step 1: POST 一个 schedule_enabled=true 的 folder**

Run:
```bash
curl -sS -X POST -H "Content-Type: application/json" -d '{
  "name": "zfix_v3", "tags": "x", "schedule_enabled": true,
  "schedule_cron": "0 0 1 1 *", "schedule_mode": "last_id"
}' -m 10 http://127.0.0.1:8000/api/v1/favorites | head -c 300
echo
```

Expected: HTTP 200, 返回 `id` 字段。**记录 id 值**（如 `id=N`），下一步用。

- [ ] **Step 2: 查 trigger 之前 zombie**

Run:
```bash
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
PWD = 'Max=1616'
url = f'mariadb+mariadbconnector://root:{quote_plus(PWD)}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'trigger 前 zombie: {n}')
"
```

Expected: `trigger 前 zombie: 0`。

- [ ] **Step 3: trigger 一次 scheduler**

Run:
```bash
curl -sS -X POST -m 30 "http://127.0.0.1:8000/api/v1/favorites/<id>/schedule/trigger" | head -c 300
echo
```

Expected: HTTP 200, `{"code":"0000","message":"触发成功",...}`。

- [ ] **Step 4: 立即查 zombie（关键验证）**

Run:
```bash
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
PWD = 'Max=1616'
url = f'mariadb+mariadbconnector://root:{quote_plus(PWD)}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'trigger 后立即 zombie: {n}')
    if n > 0:
        for r in c.execute(text('SELECT trx_id, trx_state, TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age, trx_rows_locked FROM information_schema.INNODB_TRX')):
            print(f'  {r}')
    else:
        print('  ✅ 0 zombie - 修复成功')
"
```

Expected: `trigger 后立即 zombie: 0` ✅

**如果 zombie > 0**：
- **不要继续** — Task 3 失败
- 看 `tail -20 /tmp/uvicorn-final.log` 找异常
- 可能 reload 没生效：手动 `kill <uvicorn_pid>` + `setsid python -m uvicorn ...` 重启

- [ ] **Step 5: 30s 后再查 zombie（确认不残留）**

Run:
```bash
sleep 30
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
PWD = 'Max=1616'
url = f'mariadb+mariadbconnector://root:{quote_plus(PWD)}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'30s 后 zombie: {n}')
    if n > 0:
        for r in c.execute(text('SELECT trx_id, trx_state, TIMESTAMPDIFF(SECOND, trx_started, NOW()) AS age, trx_rows_locked FROM information_schema.INNODB_TRX')):
            print(f'  {r}')
    else:
        print('  ✅ 0 zombie 长期稳定')
"
```

Expected: `30s 后 zombie: 0` ✅

- [ ] **Step 6: 验证 scheduler 业务功能仍正常**

Run:
```bash
curl -sS -m 5 http://127.0.0.1:8000/api/v1/favorites/<id>/schedule/status
echo
```

Expected: HTTP 200, `schedule_enabled: true, schedule_cron: "0 0 1 1 *"`。说明 scheduler 业务功能仍正常。

---

## Task 4: 清理验证

**Files:** 无代码改动

- [ ] **Step 1: DELETE 测试数据**

Run:
```bash
curl -sS -X DELETE -m 5 "http://127.0.0.1:8000/api/v1/favorites/<id>"
echo
```

Expected: HTTP 200。如果报 500，**改用 SQL**：
```bash
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
PWD = 'Max=1616'
url = f'mariadb+mariadbconnector://root:{quote_plus(PWD)}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.begin() as c:
    rc = c.execute(text('DELETE FROM favorite_folders WHERE id=<id>')).rowcount
    print(f'deleted: {rc}')
"
```

- [ ] **Step 2: 验证 favorite_folders = 0**

Run:
```bash
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
PWD = 'Max=1616'
url = f'mariadb+mariadbconnector://root:{quote_plus(PWD)}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM favorite_folders')).scalar()
    print(f'favorite_folders count: {n}')
    assert n == 0, f'expected 0, got {n}'
    print('PASS: favorite_folders is empty')
"
```

Expected: `favorite_folders count: 0`。

- [ ] **Step 3: 60s 无活动 zombie 检查**

Run:
```bash
sleep 60
/home/exa160/opencode/yande.re-spider-next-dev/.venv/bin/python -c "
from sqlalchemy import create_engine, text
from urllib.parse import quote_plus
PWD = 'Max=1616'
url = f'mariadb+mariadbconnector://root:{quote_plus(PWD)}@192.168.100.111:3307/Pictures'
eng = create_engine(url)
with eng.connect() as c:
    n = c.execute(text('SELECT COUNT(*) FROM information_schema.INNODB_TRX')).scalar()
    print(f'60s 无活动 zombie: {n}')
    assert n == 0, f'expected 0, got {n}'
    print('PASS: 60s 后仍 0 zombie')
"
```

Expected: `PASS: 60s 后仍 0 zombie`。

- [ ] **Step 4: 最终 git 状态检查**

Run:
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && \
  git log --oneline -5 && \
  echo '---' && \
  git status --short
```

Expected:
- `git log` 显示 1 个新 commit（Task 1）
- `git status` 空（除前面几轮的副产物 `config.yaml` / `pyproject.toml` / `uv.lock`）

---

## 自我检查

**Spec 覆盖**：
- §3.1 改动结构 → Task 1 Step 1
- §3.4 数据流 → 不在 plan（informational）
- §5.1 静态验证 → Task 1 Step 6
- §5.2 启动验证 → Task 2
- §5.3 端到端验证 → Task 3
- §5.4 清理验证 → Task 4

**占位符扫描**：✓ 无 TBD/TODO

**类型一致性**：
- `FavoriteDao` import 在 Task 1 Step 5
- `dao.get_by_id` / `dao.update` 在 Task 1 Step 1-4
- `with FavoriteDao() as dao:` 在 Task 1 Step 1

**检查通过。**
