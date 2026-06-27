# 下载管理页 Tabs 分组改造 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把下载管理页（`Download.vue`）从单列表改为 5 Tabs 分组（全部/下载中/已完成/错误/已取消），支持状态徽标计数、移动端友好布局、仅"下载中" Tab 轮询、错误信息可折叠。

**Architecture:**
- **后端**：`DownloadTaskDao` 新增多状态过滤 + 排序 + 计数方法；`DownloadService` 暴露统一接口；API 路由扩展 query 参数；新增 `/download/tasks/count` 端点
- **前端**：`Download.vue` 整体重写为 5 Tabs + 移动端卡片 + 错误折叠；`api/index.js` 不变（已支持 `params` 数组）
- **数据流**：
  - 活跃任务（pending/downloading/paused）→ `task_store` 内存（实时进度）
  - 终态任务（completed/failed/cancelled）→ DB（持久化）
  - DAO 层统一对外接口，内部合并两个数据源
- **设计参考**：`docs/superpowers/specs/2026-06-21-download-page-tabs-design.md`

**Tech Stack:**
- 后端：FastAPI 0.110+ / SQLAlchemy 2.0 / pydantic v2 / pytest / SQLite（dev）/ MariaDB（prod）
- 前端：Vue 3.4+ Composition API / Element Plus 2.5+ / axios / Vite
- 测试：pytest + responses（HTTP mock）

**运行测试前置条件**：所有后端 pytest 命令必须在 `backend/` 目录下执行（`src` 包才能被识别）。前端 npm 命令在 `frontend/` 目录下执行。

---

## 架构关键决策（实现前提）

### 现状

- `DownloadService.get_tasks()` 当前**走 `task_store`（内存）** — 活跃任务（pending/downloading/paused）实时
- `DownloadTaskDao` 有 `query()` 方法（单 status + 分页 + 默认 `created_at desc`）— 但 **当前未被 Service 调用**
- 终态任务（completed/failed/cancelled）在 `task_store` 中被清除，**仅在 DB 中保留**

### 本次改造方案

**DAO 内部合并两个数据源**：

| 数据源 | 状态 | 用途 |
|---|---|---|
| `task_store._tasks`（内存） | pending / downloading / paused | 活跃任务，实时进度 |
| DB `download_tasks` 表 | 全部状态 | 持久化，特别是终态任务 |

**DAO 新方法**：

```python
def query_tasks(
    self, 
    status_list: Optional[List[TaskStatus]] = None,
    sort_by: str = "created_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> Tuple[List[dict], int]:
    """统一查询入口：合并内存活跃 + DB 终态"""
    # 1. 终态任务走 DB
    # 2. 活跃任务走 task_store
    # 3. 合并后排序 + 分页
    # 4. 返回 (list, total)
```

```python
def count_by_status(self) -> dict:
    """各状态任务计数（单次 DB GROUP BY + 内存活跃数）"""
    # 1. DB GROUP BY status
    # 2. 加上 task_store 中活跃任务数
    # 3. 返回完整 6 状态 dict
```

**Service 保持薄层**：

```python
@staticmethod
def get_tasks(status_list=None, sort_by="created_at", order="desc", page=1, page_size=20):
    return download_task_dao.query_tasks(status_list, sort_by, order, page, page_size)

@staticmethod
def get_status_counts():
    return download_task_dao.count_by_status()
```

### 状态归类

| Tab | 包含的 `TaskStatus` | 数据源 |
|---|---|---|
| 下载中 | pending / downloading / paused | task_store（内存） |
| 已完成 | completed | DB（终态） |
| 错误 | failed | DB（终态） |
| 已取消 | cancelled | DB（终态） |
| 全部 | 全部 | 合并 |

---

## File Structure

### 新增文件

- `backend/src/models/response/download.py` — 新增 `TaskStatusCount` 和 `TaskStatusCountResponse` 类
- `unit_test/api/v1/test_download_routes.py` — API 路由测试
- `unit_test/dao/test_download_task_dao_tabs.py` — DAO 多状态/排序/计数测试

### 修改文件

- `backend/src/dao/download_task_dao.py` — 新增 `query_tasks()`、`count_by_status()` 方法
- `backend/src/services/download.py` — `get_tasks` 签名扩展；新增 `get_status_counts()`
- `backend/src/api/v1/download.py` — 路由参数扩展 + 新增 `/tasks/count` 路由
- `frontend/src/views/Download.vue` — 整体重写（459 行 → 约 500 行）

### 不变文件

- `backend/src/infrastructure/download_queue.py` — `TaskStore` 接口不变，DAO 内部消费
- `backend/src/models/database/yande.py` — `DownloadTask` 模型不变（字段已就位）
- `frontend/src/api/index.js` — 已支持 `params` 数组

---

## Tasks

### Task 1: 在 `DownloadTaskDao` 添加 `count_by_status()` 方法

**Files:**
- Modify: `backend/src/dao/download_task_dao.py:108-160`（在 `query` 方法之后插入新方法）

- [ ] **Step 1: 写失败测试**

在 `unit_test/dao/test_download_task_dao_tabs.py` 创建测试文件：

```python
"""DownloadTaskDao 多状态/排序/计数测试（TDD）"""
import pytest

from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao


@pytest.fixture
def dao():
    """每个测试用独立 session 上下文"""
    with DownloadTaskDao() as d:
        yield d


def test_count_by_status_empty_db_returns_all_zero(dao):
    """空库时所有状态返回 0"""
    counts = dao.count_by_status()
    assert counts == {
        "pending": 0, "downloading": 0, "paused": 0,
        "completed": 0, "failed": 0, "cancelled": 0,
    }


def test_count_by_status_groups_by_status(dao):
    """插入混合状态后按 status 分组统计"""
    # 插入 3 个 completed + 2 个 failed + 1 个 pending
    for i in range(3):
        dao.create(task_id=f"c-{i}", image_id=100 + i, file_name=f"c{i}.jpg")
        rec = dao.get_by_id(f"c-{i}")
        rec.status = TaskStatus.COMPLETED
    for i in range(2):
        dao.create(task_id=f"f-{i}", image_id=200 + i, file_name=f"f{i}.jpg")
        rec = dao.get_by_id(f"f-{i}")
        rec.status = TaskStatus.FAILED
    dao.create(task_id="p-0", image_id=300, file_name="p0.jpg")
    # pending 保持默认

    counts = dao.count_by_status()
    assert counts["completed"] == 3
    assert counts["failed"] == 2
    assert counts["pending"] == 1
    assert counts["downloading"] == 0
    assert counts["paused"] == 0
    assert counts["cancelled"] == 0
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/dao/test_download_task_dao_tabs.py::test_count_by_status_empty_db_returns_all_zero -v
```

预期：`AttributeError: 'DownloadTaskDao' object has no attribute 'count_by_status'`

- [ ] **Step 3: 实现 `count_by_status()`**

在 `backend/src/dao/download_task_dao.py` 文件中，找到 `query` 方法（约 108 行），在 `_to_dict` 静态方法之前，插入：

```python
    def count_by_status(self) -> dict:
        """按 status 统计任务数（单 SQL GROUP BY）
        
        Returns:
            dict 包含 6 个 TaskStatus 键，缺失状态为 0
        """
        rows = self.session.query(
            DownloadTask.status,
            func.count(DownloadTask.task_id)
        ).group_by(DownloadTask.status).all()
        
        result = {s.value: 0 for s in TaskStatus}
        for status_val, count in rows:
            key = status_val.value if hasattr(status_val, "value") else status_val
            result[key] = count
        return result
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/dao/test_download_task_dao_tabs.py -v
```

预期：两个测试都 PASS

- [ ] **Step 5: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
git add backend/src/dao/download_task_dao.py unit_test/dao/test_download_task_dao_tabs.py
git commit -m "feat(dao): add DownloadTaskDao.count_by_status() for status aggregation"
```

---

### Task 2: 在 `DownloadTaskDao` 添加 `query_tasks()` 多状态+排序方法

**Files:**
- Modify: `backend/src/dao/download_task_dao.py`（在 `query` 方法之后、`_to_dict` 之前）
- Test: `unit_test/dao/test_download_task_dao_tabs.py`

- [ ] **Step 1: 写失败测试**

在 `unit_test/dao/test_download_task_dao_tabs.py` 追加测试：

```python
def test_query_tasks_filters_by_single_status(dao):
    """单 status 过滤"""
    for i, s in enumerate([TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.FAILED]):
        dao.create(task_id=f"t-{i}", image_id=1000 + i, file_name=f"t{i}.jpg")
        rec = dao.get_by_id(f"t-{i}")
        rec.status = s

    results, total = dao.query_tasks(status_list=[TaskStatus.COMPLETED])
    assert total == 1
    assert len(results) == 1
    assert results[0]["status"] == "completed"


def test_query_tasks_filters_by_multiple_status(dao):
    """多 status 过滤（IN 查询）"""
    for i, s in enumerate([
        TaskStatus.PENDING, TaskStatus.DOWNLOADING, TaskStatus.PAUSED,
        TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
    ]):
        dao.create(task_id=f"t-{i}", image_id=2000 + i, file_name=f"t{i}.jpg")
        rec = dao.get_by_id(f"t-{i}")
        rec.status = s

    results, total = dao.query_tasks(
        status_list=[TaskStatus.PENDING, TaskStatus.DOWNLOADING, TaskStatus.PAUSED]
    )
    assert total == 3
    assert {r["status"] for r in results} == {"pending", "downloading", "paused"}


def test_query_tasks_sorts_by_created_at_desc(dao):
    """created_at desc 排序"""
    for i in range(3):
        dao.create(task_id=f"s-{i}", image_id=3000 + i, file_name=f"s{i}.jpg")
        rec = dao.get_by_id(f"s-{i}")
        rec.status = TaskStatus.COMPLETED

    results, _ = dao.query_tasks(sort_by="created_at", order="desc")
    # 最后创建的应该在前面
    assert results[0]["task_id"] == "s-2"
    assert results[-1]["task_id"] == "s-0"


def test_query_tasks_sorts_by_completed_at(dao):
    """completed_at desc 排序"""
    for i in range(3):
        dao.create(task_id=f"co-{i}", image_id=4000 + i, file_name=f"co{i}.jpg")
        rec = dao.get_by_id(f"co-{i}")
        rec.status = TaskStatus.COMPLETED

    results, _ = dao.query_tasks(sort_by="completed_at", order="desc")
    assert len(results) == 3


def test_query_tasks_rejects_invalid_sort_by(dao):
    """非法 sort_by 抛 ValueError"""
    with pytest.raises(ValueError, match="Invalid sort_by"):
        dao.query_tasks(sort_by="invalid_field")


def test_query_tasks_rejects_invalid_order(dao):
    """非法 order 抛 ValueError"""
    with pytest.raises(ValueError, match="Invalid order"):
        dao.query_tasks(order="invalid_order")


def test_query_tasks_pagination(dao):
    """分页正确"""
    for i in range(5):
        dao.create(task_id=f"p-{i}", image_id=5000 + i, file_name=f"p{i}.jpg")
        rec = dao.get_by_id(f"p-{i}")
        rec.status = TaskStatus.COMPLETED

    page1, total = dao.query_tasks(page=1, page_size=2)
    assert total == 5
    assert len(page1) == 2

    page3, _ = dao.query_tasks(page=3, page_size=2)
    assert len(page3) == 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/dao/test_download_task_dao_tabs.py::test_query_tasks_filters_by_single_status -v
```

预期：`AttributeError: 'DownloadTaskDao' object has no attribute 'query_tasks'`

- [ ] **Step 3: 实现 `query_tasks()`**

在 `backend/src/dao/download_task_dao.py` 中，找到 `query` 方法（约 108 行），在其后插入：

```python
    def query_tasks(
        self,
        status_list: Optional[List[TaskStatus]] = None,
        sort_by: str = "created_at",
        order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[dict], int]:
        """分页查询任务（多状态过滤 + 排序 + 分页）
        
        Args:
            status_list: 状态过滤列表；None/[] 表示所有
            sort_by: 排序字段（白名单：created_at/updated_at/completed_at/progress）
            order: 'asc' | 'desc'
            page: 页码（从 1 开始）
            page_size: 每页数量
        
        Returns:
            (任务 dict 列表, 总数)
        
        Raises:
            ValueError: 非法 sort_by 或 order
        """
        # 1. 白名单校验
        allowed_sort = {"created_at", "updated_at", "completed_at", "progress"}
        if sort_by not in allowed_sort:
            raise ValueError(f"Invalid sort_by: {sort_by}. Must be one of {allowed_sort}")
        if order not in ("asc", "desc"):
            raise ValueError(f"Invalid order: {order}. Must be 'asc' or 'desc'")
        
        # 2. 构造 query
        stmt = select(DownloadTask)
        count_stmt = select(func.count()).select_from(DownloadTask)
        
        if status_list:
            status_values = [s.value if hasattr(s, "value") else s for s in status_list]
            stmt = stmt.filter(DownloadTask.status.in_(status_values))
            count_stmt = count_stmt.filter(DownloadTask.status.in_(status_values))
        
        total = self.session.execute(count_stmt).scalar() or 0
        
        sort_col = getattr(DownloadTask, sort_by)
        if order == "asc":
            stmt = stmt.order_by(sort_col.asc())
        else:
            stmt = stmt.order_by(sort_col.desc())
        
        stmt = stmt.offset((page - 1) * page_size).limit(page_size)
        records = self.session.execute(stmt).scalars().all()
        
        return [self._to_dict(r) for r in records], total
```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/dao/test_download_task_dao_tabs.py -v
```

预期：所有 8 个测试 PASS

- [ ] **Step 5: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
git add backend/src/dao/download_task_dao.py unit_test/dao/test_download_task_dao_tabs.py
git commit -m "feat(dao): add DownloadTaskDao.query_tasks() with multi-status and sort support"
```

---

### Task 3: 在 `DownloadService` 添加新接口

**Files:**
- Modify: `backend/src/services/download.py:92-110`（替换 `get_tasks` 静态方法）

- [ ] **Step 1: 写失败测试**

在 `unit_test/dao/test_download_task_dao_tabs.py` 追加（或者新建 `unit_test/services/test_download_service_tabs.py`）：

```python
# unit_test/services/test_download_service_tabs.py
"""DownloadService 多状态/排序/计数测试（TDD）"""
import pytest

from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao
from src.services.download import DownloadService


@pytest.fixture
def setup_tasks():
    """准备混合状态任务数据"""
    with DownloadTaskDao() as dao:
        for i, s in enumerate([
            TaskStatus.PENDING, TaskStatus.DOWNLOADING, TaskStatus.PAUSED,
            TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
        ]):
            dao.create(task_id=f"svc-{i}", image_id=10000 + i, file_name=f"svc{i}.jpg")
            rec = dao.get_by_id(f"svc-{i}")
            rec.status = s
    yield
    # 清理
    from src.dao.download_task_dao import download_task_dao
    with download_task_dao as dao:
        for i in range(6):
            try:
                dao.delete(f"svc-{i}")
            except Exception:
                pass


def test_service_get_tasks_accepts_status_list(setup_tasks):
    """Service.get_tasks 接受 status_list"""
    tasks, total = DownloadService.get_tasks(
        status_list=[TaskStatus.PENDING, TaskStatus.DOWNLOADING]
    )
    assert total == 2


def test_service_get_tasks_default_sort(setup_tasks):
    """默认 sort_by=created_at, order=desc"""
    tasks, _ = DownloadService.get_tasks()
    assert len(tasks) > 0


def test_service_get_status_counts_returns_full_dict(setup_tasks):
    """Service.get_status_counts 返回完整 6 状态字段"""
    counts = DownloadService.get_status_counts()
    assert set(counts.keys()) == {
        "pending", "downloading", "paused",
        "completed", "failed", "cancelled",
    }
    assert counts["completed"] >= 1
    assert counts["failed"] >= 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/services/test_download_service_tabs.py -v
```

预期：`TypeError: get_tasks() got an unexpected keyword argument 'status_list'`

- [ ] **Step 3: 修改 `DownloadService.get_tasks`**

替换 `backend/src/services/download.py` 中 `get_tasks` 方法（约 92-110 行）：

```python
    @staticmethod
    def get_tasks(
        status_list: Optional[List[TaskStatus]] = None,
        sort_by: str = "created_at",
        order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> Tuple[List[dict], int]:
        """
        获取任务列表（多状态过滤 + 排序 + 分页）

        Args:
            status_list: 状态过滤列表；None/[] 表示所有
            sort_by: 排序字段（created_at/updated_at/completed_at/progress）
            order: 'asc' | 'desc'
            page: 页码
            page_size: 每页数量

        Returns:
            (任务列表, 总数)
        """
        from src.dao.download_task_dao import download_task_dao
        return download_task_dao.query_tasks(
            status_list=status_list,
            sort_by=sort_by,
            order=order,
            page=page,
            page_size=page_size,
        )
```

- [ ] **Step 4: 添加 `get_status_counts` 方法**

在 `DownloadService` 类中 `get_tasks` 之后插入：

```python
    @staticmethod
    def get_status_counts() -> dict:
        """
        获取各状态任务数量（DB GROUP BY）

        Returns:
            完整 6 状态计数字典
        """
        from src.dao.download_task_dao import download_task_dao
        return download_task_dao.count_by_status()
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/services/test_download_service_tabs.py -v
```

预期：3 个测试 PASS

- [ ] **Step 6: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
git add backend/src/services/download.py unit_test/services/test_download_service_tabs.py
git commit -m "feat(services): extend DownloadService.get_tasks for multi-status and add get_status_counts"
```

---

### Task 4: 添加 `TaskStatusCount` 响应模型

**Files:**
- Modify: `backend/src/models/response/download.py:1-79`（在文件末尾追加）

- [ ] **Step 1: 写失败测试**

在 `unit_test/services/test_download_service_tabs.py` 追加（或者新文件）：

```python
# unit_test/test_response_models.py
"""响应模型测试"""
import pytest
from pydantic import ValidationError

from src.models.response.download import TaskStatusCount, TaskStatusCountResponse


def test_task_status_count_default_values():
    """所有字段默认为 0"""
    c = TaskStatusCount()
    assert c.pending == 0
    assert c.downloading == 0
    assert c.paused == 0
    assert c.completed == 0
    assert c.failed == 0
    assert c.cancelled == 0


def test_task_status_count_with_values():
    """传入值正确序列化"""
    c = TaskStatusCount(pending=1, downloading=2, completed=100)
    assert c.pending == 1
    assert c.downloading == 2
    assert c.completed == 100
    assert c.failed == 0  # 默认


def test_task_status_count_response_structure():
    """响应结构包含 code/message/data"""
    resp = TaskStatusCountResponse(
        message="OK",
        data=TaskStatusCount(pending=5, failed=2)
    )
    assert resp.code == "0000"  # BaseResponse 默认
    assert resp.message == "OK"
    assert resp.data.pending == 5
    assert resp.data.failed == 2
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/test_response_models.py -v
```

预期：`ImportError: cannot import name 'TaskStatusCount'`

- [ ] **Step 3: 实现响应模型**

在 `backend/src/models/response/download.py` 末尾追加：

```python
class TaskStatusCount(BaseModel):
    """各状态任务计数"""

    pending: int = Field(0, description="等待中任务数")
    downloading: int = Field(0, description="下载中任务数")
    paused: int = Field(0, description="已暂停任务数")
    completed: int = Field(0, description="已完成任务数")
    failed: int = Field(0, description="失败任务数")
    cancelled: int = Field(0, description="已取消任务数")


class TaskStatusCountResponse(BaseResponse[TaskStatusCount]):
    """任务状态计数响应"""

    ...
```

**注意**：检查文件顶部是否已导入 `Field`（pydantic）。如果没有，添加：

```python
from pydantic import BaseModel, Field
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/test_response_models.py -v
```

预期：3 个测试 PASS

- [ ] **Step 5: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
git add backend/src/models/response/download.py unit_test/test_response_models.py
git commit -m "feat(response): add TaskStatusCount and TaskStatusCountResponse models"
```

---

### Task 5: 修改 `get_download_tasks` 路由支持多状态+排序

**Files:**
- Modify: `backend/src/api/v1/download.py:62-78`（替换 `get_download_tasks` 函数）

- [ ] **Step 1: 写失败测试**

新建 `unit_test/api/v1/test_download_routes.py`：

```python
"""下载管理 API 路由测试（TDD）"""
import pytest
from fastapi.testclient import TestClient

# 注意：测试在 backend/ 目录下运行，service.py 就在同目录
from service import main_app  # FastAPI app
from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao


@pytest.fixture
def client():
    return TestClient(main_app)


@pytest.fixture
def setup_data():
    """准备测试数据"""
    with DownloadTaskDao() as dao:
        for i, s in enumerate([
            TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.FAILED,
        ]):
            dao.create(task_id=f"api-{i}", image_id=20000 + i, file_name=f"api{i}.jpg")
            rec = dao.get_by_id(f"api-{i}")
            rec.status = s
    yield
    with DownloadTaskDao() as dao:
        for i in range(3):
            try:
                dao.delete(f"api-{i}")
            except Exception:
                pass


def test_get_tasks_with_single_status_param(client, setup_data):
    """?status=completed 过滤"""
    resp = client.get("/api/v1/download/tasks?status=completed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


def test_get_tasks_with_multiple_status_params(client, setup_data):
    """?status=pending&status=failed 多值过滤"""
    resp = client.get("/api/v1/download/tasks?status=pending&status=failed")
    assert resp.status_code == 200
    data = resp.json()
    statuses = {t["status"] for t in data["data"]}
    assert statuses.issubset({"pending", "failed"})


def test_get_tasks_with_sort_by_and_order(client, setup_data):
    """?sort_by=created_at&order=asc 排序"""
    resp = client.get("/api/v1/download/tasks?sort_by=created_at&order=asc")
    assert resp.status_code == 200


def test_get_tasks_rejects_invalid_sort_by(client, setup_data):
    """非法 sort_by 返回 422"""
    resp = client.get("/api/v1/download/tasks?sort_by=invalid_field")
    assert resp.status_code == 422


def test_get_tasks_rejects_invalid_order(client, setup_data):
    """非法 order 返回 422"""
    resp = client.get("/api/v1/download/tasks?order=invalid_order")
    assert resp.status_code == 422


def test_get_tasks_without_status_returns_all(client, setup_data):
    """不传 status 返回所有任务（向后兼容）"""
    resp = client.get("/api/v1/download/tasks")
    assert resp.status_code == 200
    assert "data" in resp.json()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/api/v1/test_download_routes.py::test_get_tasks_with_multiple_status_params -v
```

预期：测试可能因为多值参数被解析为单个字符串而失败

- [ ] **Step 3: 修改路由签名**

在 `backend/src/api/v1/download.py` 顶部添加导入：

```python
from typing import List, Literal, Optional
```

替换 `get_download_tasks` 函数（约 62-78 行）：

```python
@router.get("/tasks", response_model=TaskListResponse, summary="获取任务列表")
async def get_download_tasks(
    status: Optional[List[TaskStatus]] = Query(None, description="任务状态过滤（多值）"),
    sort_by: Literal["created_at", "updated_at", "completed_at", "progress"] = Query(
        "created_at", description="排序字段"
    ),
    order: Literal["asc", "desc"] = Query("desc", description="排序方向"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
) -> TaskListResponse:
    """获取下载任务列表（支持多状态过滤、排序、分页）"""
    try:
        tasks, total = DownloadService.get_tasks(
            status_list=status,
            sort_by=sort_by,
            order=order,
            page=page,
            page_size=page_size,
        )
        return TaskListResponse(
            total=total,
            page=page,
            page_size=page_size,
            data=tasks
        )
    except ValueError as e:
        raise APIException(ErrMsg.PARAM_ERROR, data={"detail": str(e)})
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

**注意**：`DownloadService.get_tasks` 当前是 `staticmethod`，调用时无需 `self`。

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/api/v1/test_download_routes.py -v
```

预期：6 个测试 PASS

- [ ] **Step 5: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
git add backend/src/api/v1/download.py unit_test/api/v1/test_download_routes.py
git commit -m "feat(api): extend GET /download/tasks with multi-status filter and sort params"
```

---

### Task 6: 新增 `/download/tasks/count` 路由

**Files:**
- Modify: `backend/src/api/v1/download.py`（在 `get_download_tasks` 之后插入新路由）

- [ ] **Step 1: 写失败测试**

在 `unit_test/api/v1/test_download_routes.py` 追加：

```python
def test_get_tasks_count_returns_all_six_statuses(client, setup_data):
    """/tasks/count 返回完整 6 状态计数"""
    resp = client.get("/api/v1/download/tasks/count")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {
        "pending", "downloading", "paused",
        "completed", "failed", "cancelled",
    }
    # 数据存在
    assert all(isinstance(data[k], int) for k in data)


def test_get_tasks_count_reflects_db_state(client, setup_data):
    """/tasks/count 反映 DB 中数据"""
    resp = client.get("/api/v1/download/tasks/count")
    data = resp.json()["data"]
    # setup_data 插入了 1 pending + 1 completed + 1 failed
    assert data["pending"] >= 1
    assert data["completed"] >= 1
    assert data["failed"] >= 1
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/api/v1/test_download_routes.py::test_get_tasks_count_returns_all_six_statuses -v
```

预期：404 Not Found（路由不存在）

- [ ] **Step 3: 实现新路由**

在 `backend/src/api/v1/download.py` 中，找到 `get_download_tasks` 之后（约 78 行后），插入：

```python
@router.get(
    "/tasks/count",
    response_model=TaskStatusCountResponse,
    summary="获取各状态任务计数",
)
async def get_task_status_counts() -> TaskStatusCountResponse:
    """获取各状态任务数量（单次 SQL GROUP BY）"""
    try:
        counts = DownloadService.get_status_counts()
        return TaskStatusCountResponse(message=ErrMsg.OK.msg, data=counts)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

在文件顶部添加导入：

```python
from src.models.response.download import (
    ProgressResponse,
    TaskListResponse,
    DownloadTaskResponse,
    TaskCreatedResponse,
    TaskCreatedData,
    BatchTaskCreatedResponse,
    BatchTaskCreatedData,
    TaskStatusCountResponse,
)
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/api/v1/test_download_routes.py -v
```

预期：所有 8 个测试 PASS

- [ ] **Step 5: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
git add backend/src/api/v1/download.py
git commit -m "feat(api): add GET /download/tasks/count endpoint for status aggregation"
```

---

### Task 7: 前端 Download.vue 整体重写（5 Tabs + 计数 + 轮询）

**Files:**
- Modify: `frontend/src/views/Download.vue`（完整重写，459 行 → 约 500 行）

- [ ] **Step 1: 备份并删除旧文件（不提交）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
cp frontend/src/views/Download.vue /tmp/Download.vue.bak
```

- [ ] **Step 2: 写新文件**

完全替换 `frontend/src/views/Download.vue` 内容：

```vue
<template>
  <div class="download-page">
    <!-- 工具栏 -->
    <div class="toolbar">
      <span class="title">下载任务</span>
      <el-button type="primary" size="small" @click="refreshAll">
        <el-icon><Refresh /></el-icon>
        刷新
      </el-button>
    </div>

    <!-- 5 Tabs -->
    <el-tabs v-model="activeTab" class="task-tabs" @tab-change="onTabChange">
      <el-tab-pane
        v-for="tab in tabs"
        :key="tab.key"
        :name="tab.key"
      >
        <template #label>
          <span class="tab-label">
            {{ tab.label }}
            <el-badge
              v-if="counts[tab.key] !== null && counts[tab.key] > 0"
              :value="counts[tab.key]"
              :type="tab.badgeType"
              :max="999"
              class="tab-badge"
            />
          </span>
        </template>

        <!-- 移动端卡片视图 -->
        <div v-if="isMobile" v-loading="loading" class="task-cards">
          <div v-for="task in tasks" :key="task.task_id" class="task-card">
            <div class="card-header">
              <span class="card-id">{{ getFileName(task) }}</span>
              <el-tag :type="getStatusType(task.status)" size="small">
                {{ getStatusText(task.status) }}
              </el-tag>
            </div>
            <div class="card-progress">
              <el-progress
                :percentage="Math.round(task.progress * 100)"
                :status="getProgressStatus(task.status)"
                :stroke-width="6"
              />
            </div>
            <div class="card-info">
              <span class="card-size">
                {{ formatFileSize(task.downloaded_size) }} / {{ task.file_size ? formatFileSize(task.file_size) : '-' }}
              </span>
              <span v-if="task.speed" class="card-speed">{{ formatSpeed(task.speed) }}</span>
            </div>
            <!-- 错误信息（仅 failed Tab） -->
            <div v-if="activeTab === 'failed' && task.error_message" class="card-error">
              <el-button text size="small" @click="toggleError(task.task_id)">
                <el-icon><Warning /></el-icon>
                {{ errorExpanded[task.task_id] ? '收起错误' : '查看错误' }}
              </el-button>
              <div v-show="errorExpanded[task.task_id]" class="error-detail">
                {{ task.error_message }}
              </div>
            </div>
            <!-- 操作按钮 -->
            <div class="card-actions">
              <el-button
                v-if="task.status === 'failed'"
                type="primary"
                size="small"
                @click="onCardAction({action:'start', task})"
              >重试</el-button>
              <el-button
                v-if="task.status === 'downloading'"
                type="warning"
                size="small"
                @click="onCardAction({action:'pause', task})"
              >暂停</el-button>
              <el-button
                v-if="task.status === 'paused'"
                type="success"
                size="small"
                @click="onCardAction({action:'resume', task})"
              >恢复</el-button>
              <el-button
                v-if="['pending', 'downloading', 'paused'].includes(task.status)"
                size="small"
                @click="onCardAction({action:'cancel', task})"
              >取消</el-button>
              <el-button
                type="danger"
                size="small"
                @click="onCardAction({action:'delete', task})"
              >删除</el-button>
            </div>
          </div>
          <el-empty
            v-if="tasks.length === 0 && !loading"
            :description="emptyText"
          />
        </div>

        <!-- PC 端表格视图 -->
        <el-table
          v-else
          v-loading="loading"
          :data="tasks"
          style="width: 100%"
          size="small"
        >
          <el-table-column prop="image_id" label="图片ID" width="90" />
          <el-table-column label="文件名" show-overflow-tooltip>
            <template #default="{ row }">
              {{ getFileName(row) }}
            </template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="getStatusType(row.status)" size="small">
                {{ getStatusText(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="进度" width="140">
            <template #default="{ row }">
              <el-progress
                :percentage="Math.round(row.progress * 100)"
                :status="getProgressStatus(row.status)"
                :stroke-width="8"
              />
            </template>
          </el-table-column>
          <el-table-column label="大小" width="160" show-overflow-tooltip>
            <template #default="{ row }">
              {{ formatFileSize(row.downloaded_size) }} / {{ row.file_size ? formatFileSize(row.file_size) : '-' }}
            </template>
          </el-table-column>
          <el-table-column
            v-if="activeTab === 'failed'"
            label="错误信息"
            show-overflow-tooltip
          >
            <template #default="{ row }">
              {{ row.error_message || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="速度" width="90">
            <template #default="{ row }">
              <span v-if="row.speed">{{ formatSpeed(row.speed) }}</span>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'failed'"
                type="primary"
                size="small"
                link
                @click="onCardAction({action:'start', task:row})"
              >重试</el-button>
              <el-button
                v-if="row.status === 'downloading'"
                type="warning"
                size="small"
                link
                @click="onCardAction({action:'pause', task:row})"
              >暂停</el-button>
              <el-button
                v-if="row.status === 'paused'"
                type="success"
                size="small"
                link
                @click="onCardAction({action:'resume', task:row})"
              >恢复</el-button>
              <el-button
                v-if="['pending', 'downloading', 'paused'].includes(row.status)"
                size="small"
                link
                @click="onCardAction({action:'cancel', task:row})"
              >取消</el-button>
              <el-button
                type="danger"
                size="small"
                link
                @click="onCardAction({action:'delete', task:row})"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 分页 -->
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="isMobile ? 10 : 20"
          :total="total"
          :layout="isMobile ? 'total, prev, next' : 'total, prev, pager, next'"
          class="pagination"
          @current-change="loadTasks"
        />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, onBeforeMount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Warning } from '@element-plus/icons-vue'
import api from '@/api'

// Tab 配置
const tabs = [
  { key: 'all',       label: '全部',    badgeType: 'primary' },
  { key: 'active',    label: '下载中',  badgeType: 'primary' },
  { key: 'completed', label: '已完成',  badgeType: 'success' },
  { key: 'failed',    label: '错误',    badgeType: 'danger'  },
  { key: 'cancelled', label: '已取消',  badgeType: 'info'    },
]

const TAB_STATUS_MAP = {
  all:       null,
  active:    ['pending', 'downloading', 'paused'],
  completed: ['completed'],
  failed:    ['failed'],
  cancelled: ['cancelled'],
}

const TAB_SORT_MAP = {
  all:       { sort_by: 'created_at',   order: 'desc' },
  active:    { sort_by: 'created_at',   order: 'asc'  },
  completed: { sort_by: 'completed_at', order: 'desc' },
  failed:    { sort_by: 'completed_at', order: 'desc' },
  cancelled: { sort_by: 'completed_at', order: 'desc' },
}

// 状态
const activeTab = ref('active')
const tasks = ref([])
const loading = ref(false)
const currentPage = ref(1)
const total = ref(0)
const isMobile = ref(false)
const errorExpanded = ref({})
const counts = ref({
  all: null, active: null, completed: null, failed: null, cancelled: null
})

// 移动端检测
const checkMobile = () => {
  isMobile.value = window.innerWidth <= 768
}

onBeforeMount(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
})

// 工具函数
const getStatusText = (status) => ({
  pending:    '等待中',
  downloading:'下载中',
  paused:     '已暂停',
  completed:  '已完成',
  failed:     '失败',
  cancelled:  '已取消',
}[status] || status)

const getStatusType = (status) => {
  const types = {
    pending:    'info',
    downloading:'primary',
    paused:     'warning',
    completed:  'success',
    failed:     'danger',
    cancelled:  'info'
  }
  return types[status] || 'info'
}

const getProgressStatus = (status) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return null
}

const getFileName = (task) => {
  return task.file_name || task.yande_data?.id || task.image_id || '-'
}

const formatFileSize = (bytes) => {
  if (!bytes) return '0 B'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`
}

const formatSpeed = (bytesPerSecond) => {
  if (!bytesPerSecond) return '0 B/s'
  if (bytesPerSecond < 1024) return `${bytesPerSecond.toFixed(0)} B/s`
  if (bytesPerSecond < 1024 * 1024) return `${(bytesPerSecond / 1024).toFixed(1)} KB/s`
  return `${(bytesPerSecond / 1024 / 1024).toFixed(1)} MB/s`
}

const emptyText = computed(() => {
  const map = {
    all:       '暂无下载任务',
    active:    '当前没有进行中的任务',
    completed: '还没有完成的任务',
    failed:    '没有失败的任务',
    cancelled: '没有取消的任务',
  }
  return map[activeTab.value] || '暂无下载任务'
})

// 数据加载
const loadCounts = async () => {
  try {
    const resp = await api.get('/download/tasks/count')
    const data = resp.data?.data || resp.data || {}
    counts.value = {
      all:       (data.pending || 0) + (data.downloading || 0) + (data.paused || 0)
                 + (data.completed || 0) + (data.failed || 0) + (data.cancelled || 0),
      active:    (data.pending || 0) + (data.downloading || 0) + (data.paused || 0),
      completed: data.completed || 0,
      failed:    data.failed || 0,
      cancelled: data.cancelled || 0,
    }
  } catch (e) {
    // 失败不阻塞任务列表
    console.warn('[Download] load counts failed', e)
  }
}

const loadTasks = async (showLoading = true) => {
  if (showLoading) loading.value = true
  try {
    const tab = activeTab.value
    const statusList = TAB_STATUS_MAP[tab]
    const sort = TAB_SORT_MAP[tab]
    const params = {
      page: currentPage.value,
      page_size: isMobile.value ? 10 : 20,
      sort_by: sort.sort_by,
      order: sort.order,
    }
    if (statusList) {
      params.status = [...statusList]
    }
    const response = await api.get('/download/tasks', { params })
    const body = response.data?.data !== undefined ? response.data : response
    tasks.value = Array.isArray(body.data) ? body.data : []
    total.value = body.total || 0
  } catch (error) {
    ElMessage.error('加载任务列表失败：' + (error?.response?.data?.message || error.message))
  } finally {
    if (showLoading) loading.value = false
  }
}

const refreshAll = async () => {
  await Promise.all([loadTasks(), loadCounts()])
}

// 轮询：仅"下载中" Tab 启动
let pollTimer = null
const startPolling = () => {
  if (pollTimer) return
  pollTimer = setInterval(() => {
    if (activeTab.value === 'active') {
      loadTasks(false)
    }
  }, 2000)
}
const stopPolling = () => {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

const onTabChange = () => {
  currentPage.value = 1
  errorExpanded.value = {}
  loadTasks()
  loadCounts()
}

// 兜底：watch 同步轮询状态
watch(activeTab, (v) => {
  if (v === 'active') startPolling()
  else stopPolling()
})

// 操作处理
const onCardAction = async ({ action, task }) => {
  const actions = {
    start:   { url: `/download/task/${task.task_id}/start`,   msg: '任务已启动' },
    pause:   { url: `/download/task/${task.task_id}/pause`,   msg: '任务已暂停' },
    resume:  { url: `/download/task/${task.task_id}/resume`,  msg: '任务已恢复' },
    cancel:  { url: `/download/task/${task.task_id}/cancel`,  msg: '任务已取消', confirm: '确定要取消该任务吗？' },
    delete:  { url: `/download/task/${task.task_id}`,         msg: '任务已删除', method: 'delete', confirm: '确定要删除该任务吗？' },
  }
  const cfg = actions[action]
  if (!cfg) return

  if (cfg.confirm) {
    try {
      await ElMessageBox.confirm(cfg.confirm, '提示', { type: 'warning' })
    } catch (e) {
      if (e === 'cancel') return
      throw e
    }
  }

  try {
    const method = cfg.method || 'post'
    await api[method](cfg.url)
    ElMessage.success(cfg.msg)
    await Promise.all([loadTasks(), loadCounts()])
  } catch (e) {
    ElMessage.error(`${cfg.msg}失败：${e?.response?.data?.message || e.message}`)
  }
}

const toggleError = (taskId) => {
  errorExpanded.value[taskId] = !errorExpanded.value[taskId]
}

// 生命周期
onMounted(async () => {
  await Promise.all([loadTasks(), loadCounts()])
  if (activeTab.value === 'active') startPolling()
})

onUnmounted(() => {
  stopPolling()
  window.removeEventListener('resize', checkMobile)
})
</script>

<style scoped>
.download-page {
  padding: 15px;
}

.toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 15px;
}

.title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.task-tabs {
  margin-bottom: 10px;
}
.task-tabs :deep(.el-tabs__nav-wrap--scrollable) {
  padding: 0 8px;
}
.task-tabs :deep(.el-tabs__item) {
  font-size: 13px;
  padding: 0 12px !important;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.tab-badge {
  margin-left: 2px;
}

.task-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 0 8px;
}

.task-card {
  background: var(--bg-primary);
  border-radius: 8px;
  padding: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.card-id {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  word-break: break-all;
}

.card-progress {
  margin-bottom: 6px;
}

.card-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}

.card-size {
  font-size: 12px;
  color: var(--text-muted);
}

.card-speed {
  font-size: 12px;
  color: var(--text-primary);
  font-weight: 500;
}

.card-error {
  margin: 8px 0;
  padding: 8px;
  background: #fef0f0;
  border-radius: 4px;
  font-size: 12px;
}
.error-detail {
  margin-top: 6px;
  color: #f56c6c;
  word-break: break-all;
  white-space: pre-wrap;
}

.card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.card-actions .el-button {
  flex: 1;
  min-width: 60px;
}

.pagination {
  margin-top: 15px;
  justify-content: center;
}

@media screen and (max-width: 768px) {
  .toolbar {
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
  }
  .toolbar .el-button {
    width: 100%;
  }
  .task-tabs :deep(.el-tabs__header) {
    margin-bottom: 10px;
  }
  .task-card {
    padding: 10px;
  }
}
</style>
```

- [ ] **Step 3: 检查语法和导入**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
# 检查 Vue 文件能编译
npx vue-tsc --noEmit src/views/Download.vue 2>/dev/null || true
# 或者启动 dev server 检查
timeout 10 npm run dev 2>&1 | head -30 || echo "Dev server check skipped"
```

预期：没有 TypeScript 错误

- [ ] **Step 4: 提交**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
git add frontend/src/views/Download.vue
git commit -m "feat(frontend): refactor Download.vue with 5 Tabs (all/active/completed/failed/cancelled)"
```

---

### Task 8: 集成测试 + 浏览器手动验证

**Files:**
- 无（验证步骤）

- [ ] **Step 1: 启动后端服务**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
uvicorn service:main_app --host 0.0.0.0 --port 8000 --reload
```

预期：服务启动，监听 8000 端口

- [ ] **Step 2: 启动前端 dev server**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npm run dev
```

预期：Vite dev server 启动，监听 3000 端口

- [ ] **Step 3: 浏览器访问 http://localhost:3000/download**

手动验证清单：

| # | 场景 | 期望 |
|---|---|---|
| F1 | 首次进入页面 | 默认"下载中" Tab，Tab 头部有徽标（数字） |
| F2 | 点击"全部" Tab | 列表显示所有任务；轮询停止 |
| F3 | 点击"已完成" Tab | 列表显示 completed 任务；轮询停止 |
| F4 | 点击"错误" Tab | 列表显示 failed 任务；轮询停止 |
| F5 | 点击"已取消" Tab | 列表显示 cancelled 任务；轮询停止 |
| F6 | 切回"下载中" Tab | 轮询重启（可观察网络请求 2s 一次） |
| F7 | 点击"重试"按钮（failed 任务） | 任务状态变 `downloading`，徽标数字变化 |
| F8 | 调整窗口宽度到 768px 以下 | 自动切换为卡片视图，Tabs 横向滑动 |
| F9 | 错误 Tab 点击"查看错误" | 错误信息展开，再次点击折叠 |
| F10 | 计数 API 故意挂掉（如关闭后端） | 徽标消失或显示 0，任务列表正常 |
| F11 | 删除最后一页唯一任务 | 自动跳到上一页 |

- [ ] **Step 4: 验证完成后停止服务**

```bash
# 停止 uvicorn 和 vite
pkill -f "uvicorn service:main_app" || true
pkill -f "vite" || true
```

- [ ] **Step 5: 提交（如果浏览器验证后有微调）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
git status  # 检查是否有未提交的修改
```

预期：所有改动已在前面的 task 中提交；如有问题，单独 commit

---

### Task 9: 运行完整测试套件

**Files:**
- 无

- [ ] **Step 1: 运行后端测试**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/dao/test_download_task_dao_tabs.py ../unit_test/services/test_download_service_tabs.py ../unit_test/test_response_models.py ../unit_test/api/v1/test_download_routes.py -v
```

预期：所有测试 PASS

- [ ] **Step 2: 运行全部后端测试（确保不破坏现有）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
../.venv/bin/python -m pytest ../unit_test/ -v --timeout=60
```

预期：所有现有测试 PASS（特别是 `test_downloader.py` 等与下载相关的）

- [ ] **Step 3: 检查 LSP 诊断（前端）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/frontend
npx vue-tsc --noEmit -p tsconfig.json 2>&1 | head -30 || echo "vue-tsc not available, skipping"
```

预期：无 TypeScript 错误

- [ ] **Step 4: 最终提交（如果需要）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
git status
# 如果有任何未提交的微调
git add -A
git commit -m "chore: post-implementation cleanup"
```

预期：所有改动已提交

---

## 验收清单

完成所有 task 后，验证：

- [ ] 后端 `GET /download/tasks?status=pending&status=paused&sort_by=created_at&order=asc` 返回正确数据
- [ ] 后端 `GET /download/tasks?sort_by=invalid` 返回 422
- [ ] 后端 `GET /download/tasks/count` 返回 6 状态完整计数
- [ ] 后端测试 17 个（DAO 8 + Service 3 + Response 3 + API 8 = 22 个）全部 PASS
- [ ] 前端 5 Tabs 切换正常
- [ ] 移动端 768px 视口下卡片视图正常
- [ ] 错误 Tab 错误信息可折叠
- [ ] 状态文本显示中文
- [ ] 仅"下载中" Tab 轮询

---

## 风险与回滚

| 风险 | 缓解 |
|---|---|
| `TaskStore` 内存与 DB 数据不一致 | DAO 同时读内存和 DB；活跃任务以内存为准 |
| 多值 `status` 参数序列化失败 | 已被 Pydantic `List[TaskStatus]` 接受 |
| 排序字段在 SQLite/MySQL 行为不一致 | 默认行为一致（NULL 在 desc 时排后） |
| 前端 el-tabs 移动端宽度不足 | el-tabs 默认支持横向滑动 |
| 计数 API 失败阻塞列表 | `loadCounts` catch 后仅 console.warn |

**回滚方案**：所有改动在 9 个独立 commit 中，任意 commit 可单独 revert。

---

## 参考文档

- `docs/superpowers/specs/2026-06-21-download-page-tabs-design.md` — 设计文档
- `AGENTS.md` — 项目代码规范
- `docs/dao.md` — DAO 编写规范
- `docs/api-route.md` — API 路由模板
- `docs/response.md` — BaseResponse 响应约定
- `backend/src/dao/download_task_dao.py` — 现有 DAO 实现参考
- `backend/src/services/download.py` — 现有 Service 实现参考
- `backend/src/infrastructure/download_queue.py` — TaskStore 实现参考
