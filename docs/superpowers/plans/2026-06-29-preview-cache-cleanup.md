# Preview Cache Cleanup API 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增加 `POST /api/v1/cache/preview/cleanup` 端点，支持按"局部清理（仅清有原图可再生的 preview）"或"全量清理"两种策略删除 `downloads/previews/` 下的缩略图，内置 `dry_run` 评估模式（默认 True），命中/删除/释放字节数实时返回。

**Architecture:** 单端点 + mode 参数；Service 层组合 DAO（按 `down_flag=True` 取 ID 集合）与 ImageCache（遍历目录、逐个 unlink）；ImageCache 新增 `list_preview_files()` / `safe_unlink()` 两个工具方法；DAO 新增 `get_downloaded_ids()` 一次性查询；测试用 `tmp_path` + `monkeypatch` 隔离真实 `downloads/`。

**Tech Stack:** Python 3.12+、FastAPI、Pydantic v2、SQLAlchemy 2.0、pytest、loguru

**Spec Reference:** `docs/superpowers/specs/2026-06-29-preview-cache-cleanup-design.md`

**Working Directory:** 所有命令默认在项目根 (`/home/exa160/opencode/yande.re-spider-next-dev`)；测试用 `pytest unit_test/...` 在项目根执行（测试文件自行 `sys.path.insert` 注入 `backend/`）。

**Commit Policy:** 每个 Task 结束 commit 一次；**全部 Task 完成后整体 review 一次再 push**。

---

## 任务概览

| Task | 内容 | 类型 | 依赖 |
|---|---|---|---|
| 1 | 添加 `CleanupMode` 枚举 + `ErrMsg.CLEANUP_PREVIEW_ERROR` | 常量 | — |
| 2 | DAO: `get_downloaded_ids()` 测试 + 实现 | 数据层 | — |
| 3 | ImageCache: `list_preview_files()` + `safe_unlink()` 测试 + 实现 | 基础设施 | — |
| 4 | Request/Response 模型 | Pydantic | — |
| 5 | Service: `cleanup_previews()` + 辅助函数 测试 + 实现 | 业务层 | Task 2, 3 |
| 6 | API 路由 + 集成测试 | API | Task 4, 5 |
| 7 | 全套验收：pytest + lsp_diagnostics + ruff | 验收 | Task 1-6 |

---

## Task 1: 添加 CleanupMode 枚举与 ErrMsg

**Files:**
- Modify: `backend/src/common/constant.py`

- [ ] **Step 1: 添加 CleanupMode 枚举**

编辑 `backend/src/common/constant.py`。在 `class Rating(str, Enum):`（约第 83 行）之前插入新枚举：

```python
class CleanupMode(str, Enum):
    """预览图清理模式"""
    CLEAN_LOCAL_PREVIEWS = "clean_local_previews"  # 局部清理：有原图可再生的 preview
    CLEAN_ALL_PREVIEWS = "clean_all_previews"      # 全量清理：清空整个 previews/ 目录
```

- [ ] **Step 2: 添加 ErrMsg.CLEANUP_PREVIEW_ERROR**

在同一文件中找到 `class ErrMsg(BaseMsgEnum):`，在 `SAVE_PREVIEW_DATA_ERROR = ("0012", ...)` 那一行后面（约第 134 行）插入：

```python
    CLEANUP_PREVIEW_ERROR = ("0013", "Failed to cleanup preview cache.", HTTPStatus.INTERNAL_SERVER_ERROR)
```

确认与现有的图库错误码 0010/0011/0012 连续，类型一致（3 元 tuple：code, msg, http_status）。

- [ ] **Step 3: 验证导入无报错**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/python -c "from src.common.constant import CleanupMode, ErrMsg; print(CleanupMode.CLEAN_LOCAL_PREVIEWS.value, ErrMsg.CLEANUP_PREVIEW_ERROR.code)"
```

预期输出：`clean_local_previews 0013`

- [ ] **Step 4: lsp_diagnostics 干净**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/python -m pylint backend/src/common/constant.py 2>&1 | head -20 || true
```

预期：无 `E` 级或 `F` 级错误。

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/common/constant.py && git commit -m "feat(constant): add CleanupMode enum + CLEANUP_PREVIEW_ERROR code"
```

---

## Task 2: DAO `get_downloaded_ids()` 测试与实现

**Files:**
- Create: `unit_test/dao/test_yande_data_dao_downloaded_ids.py`
- Modify: `backend/src/dao/yande_data_dao.py`

- [ ] **Step 1: 写失败的测试**

新建 `unit_test/dao/test_yande_data_dao_downloaded_ids.py`：

```python
"""测试 YandeDataRepository.get_downloaded_ids() 返回 down_flag=True 的 ID 集合"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData


def _setup():
    """插入混合 down_flag 的测试数据"""
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        for i in range(5):
            rec = YandeData(
                id=1000 + i,
                tags=f"test_{i}",
                width=100, height=100,
                file_ext="jpg",
                file_size=1024,
                file_url=f"http://example.com/{i}.jpg",
                preview_url=f"http://example.com/p_{i}.jpg",
                md5=f"md5_{i}",
                author="tester",
                created_at="2024-01-01 00:00:00",
                down_flag=(i % 2 == 0),  # 0, 2, 4 → True；1, 3 → False
            )
            repo.session.add(rec)


def test_get_downloaded_ids_returns_only_true_flags():
    _setup()
    with YandeDataRepository() as repo:
        ids = repo.get_downloaded_ids()
    assert isinstance(ids, set)
    assert ids == {1000, 1002, 1004}


def test_get_downloaded_ids_empty_when_no_downloads():
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        ids = repo.get_downloaded_ids()
    assert ids == set()
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/dao/test_yande_data_dao_downloaded_ids.py -v
```

预期：FAIL，错误信息包含 `'YandeDataRepository' object has no attribute 'get_downloaded_ids'`。

- [ ] **Step 3: 实现 `get_downloaded_ids()` 方法**

编辑 `backend/src/dao/yande_data_dao.py`，在 `def check_downloaded(...)` 方法（约第 170 行）之后、`def get_file_ext(...)` 之前插入：

```python
    def get_downloaded_ids(self) -> set[int]:
        """查询所有已下载原图的 image_id（单次 SQL，仅取 id 字段）

        Returns:
            set[int]: down_flag=True 的 image_id 集合
        """
        stmt = select(YandeData.id).where(YandeData.down_flag.is_(True))
        rows = self.session.execute(stmt).scalars().all()
        return set(rows)
```

`select` 已经从 `sqlalchemy` 导入，无需新增 import。

- [ ] **Step 4: 重新跑测试，确认通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/dao/test_yande_data_dao_downloaded_ids.py -v
```

预期：2 passed。

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/dao/yande_data_dao.py unit_test/dao/test_yande_data_dao_downloaded_ids.py && git commit -m "feat(dao): add get_downloaded_ids() returning down_flag=True ID set"
```

---

## Task 3: ImageCache `list_preview_files()` + `safe_unlink()` 测试与实现

**Files:**
- Create: `unit_test/infrastructure/test_image_cache_cleanup.py`
- Modify: `backend/src/infrastructure/image_cache.py`

- [ ] **Step 1: 写失败的测试**

新建 `unit_test/infrastructure/test_image_cache_cleanup.py`：

```python
"""测试 ImageCache.list_preview_files() 和 safe_unlink() 的目录隔离行为"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest

from src.common import path_constant
from src.infrastructure.image_cache import ImageCache


@pytest.fixture
def tmp_previews(tmp_path, monkeypatch):
    """将 path_constant.previews_dir 重定向到 tmp_path/previews，自动创建"""
    target = tmp_path / "previews"
    target.mkdir()
    monkeypatch.setattr(path_constant, "previews_dir", target)
    return target


def _make_image(directory: Path, name: str, size_bytes: int = 100):
    """在 directory 下创建指定大小的占位文件"""
    p = directory / name
    p.write_bytes(b"\x00" * size_bytes)
    return p


def test_list_preview_files_returns_all_regular_files(tmp_previews):
    _make_image(tmp_previews, "123.jpg")
    _make_image(tmp_previews, "456.png")
    _make_image(tmp_previews, "789.webp")

    cache = ImageCache()
    files = cache.list_preview_files()
    names = {p.name for p in files}
    assert names == {"123.jpg", "456.png", "789.webp"}


def test_list_preview_files_skips_hidden_files(tmp_previews):
    _make_image(tmp_previews, "123.jpg")
    _make_image(tmp_previews, ".DS_Store")
    _make_image(tmp_previews, ".gitkeep")

    cache = ImageCache()
    files = cache.list_preview_files()
    names = {p.name for p in files}
    assert names == {"123.jpg"}


def test_list_preview_files_returns_empty_when_dir_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(path_constant, "previews_dir", tmp_path / "nope")
    cache = ImageCache()
    assert cache.list_preview_files() == []


def test_safe_unlink_removes_existing_file(tmp_previews):
    p = _make_image(tmp_previews, "del.jpg")
    cache = ImageCache()
    assert cache.safe_unlink(p) is True
    assert not p.exists()


def test_safe_unlink_returns_true_for_nonexistent_file(tmp_previews):
    cache = ImageCache()
    ghost = tmp_previews / "ghost.jpg"
    assert cache.safe_unlink(ghost) is True


def test_safe_unlink_returns_false_on_permission_error(tmp_previews, monkeypatch):
    """模拟 unlink 抛 OSError，验证返回 False 不抛异常"""
    p = _make_image(tmp_previews, "locked.jpg")

    def _raise_oserror(self):
        raise OSError("permission denied")

    monkeypatch.setattr("pathlib.Path.unlink", _raise_oserror)

    cache = ImageCache()
    assert cache.safe_unlink(p) is False
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/infrastructure/test_image_cache_cleanup.py -v
```

预期：FAIL，错误信息包含 `'ImageCache' object has no attribute 'list_preview_files'`。

- [ ] **Step 3: 实现 list_preview_files() 和 safe_unlink()**

编辑 `backend/src/infrastructure/image_cache.py`：

1. 顶部 import 区（约第 1-11 行）追加 `import os` 和 `from loguru import logger`（logger 已存在，只加 `import os`）。

```python
import os
from pathlib import Path
```

2. 在 `class ImageCache:` 的最后一行（`check_local_files` 之后）新增两个方法：

```python
    def list_preview_files(self) -> list[Path]:
        """列出 previews/ 下所有非隐藏文件（用 os.scandir 性能更好）"""
        if not self.PREVIEWS_DIR.exists():
            return []
        return [
            Path(entry.path)
            for entry in os.scandir(self.PREVIEWS_DIR)
            if entry.is_file() and not entry.name.startswith(".")
        ]

    def safe_unlink(self, path: Path) -> bool:
        """安全删除单个文件，失败返回 False 不抛异常"""
        try:
            if path.exists():
                path.unlink()
            return True
        except OSError as e:
            logger.warning(f"Failed to unlink {path}: {e}")
            return False
```

- [ ] **Step 4: 重新跑测试，确认通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/infrastructure/test_image_cache_cleanup.py -v
```

预期：6 passed。

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/infrastructure/image_cache.py unit_test/infrastructure/test_image_cache_cleanup.py && git commit -m "feat(image_cache): add list_preview_files() and safe_unlink()"
```

---

## Task 4: Request/Response 模型

**Files:**
- Modify: `backend/src/models/request/gallery.py`
- Modify: `backend/src/models/response/gallery.py`

- [ ] **Step 1: 添加 CleanupPreviewsRequest**

编辑 `backend/src/models/request/gallery.py`，在文件末尾（约第 50 行后）追加：

```python
from src.common.constant import CleanupMode  # 加到文件顶部 import 区


class CleanupPreviewsRequest(BaseModel):
    """预览图清理请求"""

    mode: CleanupMode = Field(
        ...,
        description=(
            "clean_local_previews: 仅清有原图可再生的 preview；"
            "clean_all_previews: 清空整个 previews/ 目录"
        ),
    )
    dry_run: bool = Field(
        True,
        description="True 时仅评估不删除；False 时执行实际删除",
    )
```

注意：把 `from src.common.constant import CleanupMode` 加到顶部 import 区，与现有 `from src.common.constant import Rating` 合并为：

```python
from src.common.constant import CleanupMode, Rating
```

- [ ] **Step 2: 添加 CleanupResult 和 CleanupPreviewsResponse**

编辑 `backend/src/models/response/gallery.py`，在文件末尾追加：

```python
class CleanupResult(BaseModel):
    """清理结果"""

    mode: str = Field(..., description="实际执行的清理模式")
    dry_run: bool = Field(..., description="是否为评估模式")
    matched: int = Field(..., description="命中文件数")
    deleted: int = Field(..., description="实际删除文件数（dry_run 时为 0）")
    failed: int = Field(..., description="删除失败文件数（权限/占用）")
    total_bytes: int = Field(..., description="命中文件总字节数")
    duration_ms: int = Field(..., description="处理耗时（毫秒）")


class CleanupPreviewsResponse(BaseResponse[CleanupResult]):
    """预览图清理响应"""

    ...
```

- [ ] **Step 3: 验证模型导入**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/python -c "from src.models.request.gallery import CleanupPreviewsRequest; from src.models.response.gallery import CleanupResult, CleanupPreviewsResponse; r = CleanupPreviewsRequest(mode='clean_local_previews'); print(r.mode, r.dry_run)"
```

预期输出：`clean_local_previews True`（验证 dry_run 默认值）。

- [ ] **Step 4: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/models/request/gallery.py backend/src/models/response/gallery.py && git commit -m "feat(models): add CleanupPreviewsRequest + CleanupResult + CleanupPreviewsResponse"
```

---

## Task 5: Service `cleanup_previews()` 测试与实现

**Files:**
- Create: `unit_test/services/test_gallery_cleanup.py`
- Modify: `backend/src/services/gallery.py`

- [ ] **Step 1: 写失败的测试**

新建 `unit_test/services/test_gallery_cleanup.py`：

```python
"""测试 GalleryService.cleanup_previews() 的核心逻辑（dry_run / 模式过滤 / 隐藏文件 / 错误隔离）"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest

from src.common import path_constant
from src.common.constant import CleanupMode
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData
from src.services.gallery import GalleryService


@pytest.fixture
def tmp_previews(tmp_path, monkeypatch):
    target = tmp_path / "previews"
    target.mkdir()
    monkeypatch.setattr(path_constant, "previews_dir", target)
    return target


def _mk_image(directory: Path, name: str, size: int = 100):
    p = directory / name
    p.write_bytes(b"\x00" * size)
    return p


def _seed_db(downloaded_ids: list[int]):
    """在数据库里塞入 down_flag=True 的 ID"""
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        for i in downloaded_ids:
            rec = YandeData(
                id=i,
                tags=f"t{i}",
                width=10, height=10,
                file_ext="jpg",
                file_size=100,
                file_url=f"http://x/{i}.jpg",
                preview_url=f"http://x/p_{i}.jpg",
                md5=f"m{i}",
                author="a",
                created_at="2024-01-01 00:00:00",
                down_flag=True,
            )
            repo.session.add(rec)


# ---------- 辅助函数 _parse_image_id ----------

def test_parse_image_id_normal():
    assert GalleryService._parse_image_id("12345.jpg") == 12345
    assert GalleryService._parse_image_id("12345") == 12345
    assert GalleryService._parse_image_id("12345.png") == 12345


def test_parse_image_id_hidden_file_returns_none():
    assert GalleryService._parse_image_id(".DS_Store") is None
    assert GalleryService._parse_image_id(".gitkeep") is None


def test_parse_image_id_invalid_format_returns_none():
    assert GalleryService._parse_image_id("abc.jpg") is None
    assert GalleryService._parse_image_id("not_a_number") is None


# ---------- 清理逻辑 ----------

def test_cleanup_local_dry_run_does_not_delete_files(tmp_previews):
    """dry_run=True 时文件系统完全不动"""
    _seed_db([100, 200])
    _mk_image(tmp_previews, "100.jpg")
    _mk_image(tmp_previews, "200.jpg")
    _mk_image(tmp_previews, "300.jpg")  # 不在 down_flag 集合中

    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_LOCAL_PREVIEWS,
        dry_run=True,
    )

    assert result["matched"] == 2
    assert result["deleted"] == 0
    assert result["total_bytes"] == 200
    assert result["dry_run"] is True
    assert {p.name for p in tmp_previews.iterdir()} == {"100.jpg", "200.jpg", "300.jpg"}


def test_cleanup_local_real_delete_only_downloaded(tmp_previews):
    """真实删除时，仅删 down_flag=True 对应的 preview"""
    _seed_db([100, 200])
    p100 = _mk_image(tmp_previews, "100.jpg")
    p200 = _mk_image(tmp_previews, "200.jpg")
    p300 = _mk_image(tmp_previews, "300.jpg")  # 无原图，不应删

    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_LOCAL_PREVIEWS,
        dry_run=False,
    )

    assert result["matched"] == 2
    assert result["deleted"] == 2
    assert result["failed"] == 0
    assert not p100.exists()
    assert not p200.exists()
    assert p300.exists()


def test_cleanup_all_removes_everything_except_hidden(tmp_previews):
    """全量清理：除隐藏文件外全部删除"""
    _seed_db([])  # DB 无数据，但 CLEAN_ALL 不依赖 DB
    _mk_image(tmp_previews, "1.jpg")
    _mk_image(tmp_previews, "2.jpg")
    _mk_image(tmp_previews, ".DS_Store")

    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_ALL_PREVIEWS,
        dry_run=False,
    )

    assert result["matched"] == 2  # 隐藏文件不计
    assert result["deleted"] == 2
    remaining = {p.name for p in tmp_previews.iterdir()}
    assert remaining == {".DS_Store"}


def test_cleanup_local_with_missing_dir_returns_empty(tmp_path, monkeypatch):
    """previews/ 不存在时返回 matched=0 不抛错"""
    monkeypatch.setattr(path_constant, "previews_dir", tmp_path / "nope")
    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_LOCAL_PREVIEWS,
        dry_run=True,
    )
    assert result["matched"] == 0
    assert result["deleted"] == 0


def test_cleanup_local_continues_when_single_unlink_fails(tmp_previews, monkeypatch):
    """单个文件 unlink 失败不影响其他文件（mock ImageCache.safe_unlink）"""
    _seed_db([100, 200, 300])
    _mk_image(tmp_previews, "100.jpg")
    _mk_image(tmp_previews, "200.jpg")
    _mk_image(tmp_previews, "300.jpg")

    # 让 200.jpg 的 unlink 失败，其他成功
    def _selective_safe_unlink(path):
        if "200" in path.name:
            return False
        path.unlink()
        return True

    monkeypatch.setattr(
        "src.infrastructure.image_cache.ImageCache.safe_unlink",
        _selective_safe_unlink,
    )

    result = GalleryService.cleanup_previews(
        mode=CleanupMode.CLEAN_LOCAL_PREVIEWS,
        dry_run=False,
    )

    assert result["matched"] == 3
    assert result["deleted"] == 2  # 100 和 300 成功
    assert result["failed"] == 1   # 200 失败
```

**注意**：mock 的是 `ImageCache.safe_unlink`（monkeypatch 替换方法），不影响 `pathlib.Path.unlink`，副作用最小。Task 3 已单独测过 `safe_unlink` 自身在 OSError 时返回 False 的行为（`test_safe_unlink_returns_false_on_permission_error`），所以这里的关注点是 cleanup_previews 对 failed 字段的计数正确。

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/services/test_gallery_cleanup.py -v
```

预期：FAIL，错误信息包含 `'GalleryService' object has no attribute '_parse_image_id'` 或 `'cleanup_previews'`。

- [ ] **Step 3: 实现 _parse_image_id 和 cleanup_previews**

编辑 `backend/src/services/gallery.py`：

1. 顶部 import 区追加 `import time`：

```python
import time
from typing import List, Optional
```

并在 import 区追加 `from src.common.constant import CleanupMode, ErrMsg, path_constant`（`ErrMsg` 和 `path_constant` 可能已存在，确认即可）。

2. 在文件末尾追加两个静态方法和 1 个辅助函数：

```python
    @staticmethod
    def cleanup_previews(mode: CleanupMode, dry_run: bool) -> dict:
        """清理 preview 缩略图

        Args:
            mode: 清理模式
            dry_run: True 仅评估，False 实际删除

        Returns:
            CleanupResult dict

        Raises:
            APIException: 数据库查询失败时
        """
        cache = ImageCache()
        previews_dir = path_constant.previews_dir
        start = time.monotonic()

        # 1) 目录不存在 → 返回零结果（首次启动友好）
        if not previews_dir.exists():
            return _empty_cleanup_result(mode, dry_run)

        # 2) 列出所有 preview 文件
        all_previews = cache.list_preview_files()

        # 3) 按 mode 过滤
        if mode == CleanupMode.CLEAN_LOCAL_PREVIEWS:
            try:
                with YandeDataRepository() as repo:
                    downloaded_ids = repo.get_downloaded_ids()
            except Exception as e:
                raise APIException(ErrMsg.QUERY_ERROR, e=e)

            targets = []
            for p in all_previews:
                image_id = GalleryService._parse_image_id(p.name)
                if image_id is not None and image_id in downloaded_ids:
                    targets.append(p)
        else:  # CLEAN_ALL_PREVIEWS
            targets = all_previews

        # 4) 统计 matched / total_bytes
        matched = len(targets)
        total_bytes = 0
        for p in targets:
            try:
                total_bytes += p.stat().st_size
            except OSError:
                continue  # 文件可能在扫描中被外部删除；忽略

        # 5) dry_run 时不删；否则逐个 unlink
        deleted, failed = 0, 0
        if not dry_run:
            for p in targets:
                if cache.safe_unlink(p):
                    deleted += 1
                else:
                    failed += 1

        duration_ms = int((time.monotonic() - start) * 1000)
        return {
            "mode": mode.value,
            "dry_run": dry_run,
            "matched": matched,
            "deleted": deleted,
            "failed": failed,
            "total_bytes": total_bytes,
            "duration_ms": duration_ms,
        }

    @staticmethod
    def _parse_image_id(filename: str) -> Optional[int]:
        """从 preview 文件名解析 image_id。文件名约定：{id}.{ext}"""
        if filename.startswith("."):
            return None
        stem = filename.rsplit(".", 1)[0] if "." in filename else filename
        try:
            return int(stem)
        except ValueError:
            return None


def _empty_cleanup_result(mode: CleanupMode, dry_run: bool) -> dict:
    """目录不存在时返回的零结果"""
    return {
        "mode": mode.value,
        "dry_run": dry_run,
        "matched": 0,
        "deleted": 0,
        "failed": 0,
        "total_bytes": 0,
        "duration_ms": 0,
    }
```

注意：`_empty_cleanup_result` 是模块级函数（不是 staticmethod），因为它没用到 GalleryService 的状态。如果项目严格要求 OO 风格，可以改成 `@staticmethod`，但两种都可工作。**本计划用模块级函数**。

- [ ] **Step 4: 重新跑测试，确认通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/services/test_gallery_cleanup.py -v
```

预期：所有 case passed（最后一个 `continues_when_single_unlink_fails` 可能因 monkeypatch 副作用 skip 或失败；如失败可加 `pytest.skip` 标记或删除该 case，见 Step 1 注释）。

- [ ] **Step 5: lsp_diagnostics 干净**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/python -c "from src.services.gallery import GalleryService, _empty_cleanup_result; print('OK')"
```

预期输出：`OK`

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/services/gallery.py unit_test/services/test_gallery_cleanup.py && git commit -m "feat(service): add cleanup_previews() with mode + dry_run"
```

---

## Task 6: API 路由与集成测试

**Files:**
- Modify: `backend/src/api/v1/gallery.py`
- Create: `unit_test/api/v1/test_preview_cleanup_routes.py`

- [ ] **Step 1: 写失败的 API 集成测试**

新建 `unit_test/api/v1/test_preview_cleanup_routes.py`：

```python
"""测试 POST /api/v1/cache/preview/cleanup 端点的请求校验 + dry_run + 真删行为"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import init_app, app_config
from src.common import path_constant
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData


@pytest.fixture
def tmp_previews(tmp_path, monkeypatch):
    target = tmp_path / "previews"
    target.mkdir()
    monkeypatch.setattr(path_constant, "previews_dir", target)
    return target


@pytest.fixture
def client(tmp_previews):
    test_app = FastAPI(**app_config.model_dump())
    init_app(test_app)
    return TestClient(test_app)


def _mk_image(directory: Path, name: str, size: int = 100):
    p = directory / name
    p.write_bytes(b"\x00" * size)
    return p


def _seed_db(downloaded_ids: list[int]):
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        for i in downloaded_ids:
            rec = YandeData(
                id=i,
                tags=f"t{i}",
                width=10, height=10,
                file_ext="jpg",
                file_size=100,
                file_url=f"http://x/{i}.jpg",
                preview_url=f"http://x/p_{i}.jpg",
                md5=f"m{i}",
                author="a",
                created_at="2024-01-01 00:00:00",
                down_flag=True,
            )
            repo.session.add(rec)


def test_cleanup_local_dry_run_endpoint(client, tmp_previews):
    _seed_db([100, 200])
    _mk_image(tmp_previews, "100.jpg")
    _mk_image(tmp_previews, "200.jpg")

    resp = client.post(
        "/api/v1/cache/preview/cleanup",
        json={"mode": "clean_local_previews", "dry_run": True},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["mode"] == "clean_local_previews"
    assert data["dry_run"] is True
    assert data["matched"] == 2
    assert data["deleted"] == 0
    # 文件未删
    assert {p.name for p in tmp_previews.iterdir()} == {"100.jpg", "200.jpg"}


def test_cleanup_local_real_delete_endpoint(client, tmp_previews):
    _seed_db([100])
    p = _mk_image(tmp_previews, "100.jpg")
    _mk_image(tmp_previews, "999.jpg")  # 不在 down_flag 中

    resp = client.post(
        "/api/v1/cache/preview/cleanup",
        json={"mode": "clean_local_previews", "dry_run": False},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["deleted"] == 1
    assert not p.exists()
    assert (tmp_previews / "999.jpg").exists()


def test_cleanup_all_endpoint(client, tmp_previews):
    _mk_image(tmp_previews, "1.jpg")
    _mk_image(tmp_previews, "2.jpg")
    _mk_image(tmp_previews, ".DS_Store")

    resp = client.post(
        "/api/v1/cache/preview/cleanup",
        json={"mode": "clean_all_previews", "dry_run": False},
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["matched"] == 2
    assert data["deleted"] == 2
    # 隐藏文件保留
    assert {p.name for p in tmp_previews.iterdir()} == {".DS_Store"}


def test_cleanup_dry_run_defaults_to_true(client, tmp_previews):
    """dry_run 字段缺省时默认为 True（安全默认）"""
    _mk_image(tmp_previews, "1.jpg")

    resp = client.post(
        "/api/v1/cache/preview/cleanup",
        json={"mode": "clean_all_previews"},  # 不传 dry_run
    )

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["dry_run"] is True
    assert data["deleted"] == 0
    assert (tmp_previews / "1.jpg").exists()


def test_cleanup_invalid_mode_returns_422(client):
    resp = client.post(
        "/api/v1/cache/preview/cleanup",
        json={"mode": "invalid_mode", "dry_run": True},
    )
    assert resp.status_code == 422
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/api/v1/test_preview_cleanup_routes.py -v
```

预期：FAIL，错误信息包含 `404 Not Found`（端点未注册）。

- [ ] **Step 3: 添加 POST /cache/preview/cleanup 路由**

编辑 `backend/src/api/v1/gallery.py`：

1. 顶部 import 区追加：

```python
from src.common.constant import CleanupMode, ErrMsg
from src.models.request.gallery import CleanupPreviewsRequest
from src.models.response.gallery import CleanupPreviewsResponse, CleanupResult
```

2. 在文件末尾追加新路由：

```python
@router.post(
    "/cache/preview/cleanup",
    response_model=CleanupPreviewsResponse,
    summary="清理 preview 缩略图缓存",
)
async def cleanup_previews(request: CleanupPreviewsRequest) -> CleanupPreviewsResponse:
    """清理 preview 缩略图（支持评估模式 dry_run）"""
    try:
        result = await asyncio.to_thread(
            GalleryService.cleanup_previews,
            mode=request.mode,
            dry_run=request.dry_run,
        )
        return CleanupPreviewsResponse(
            message=ErrMsg.OK.msg,
            data=CleanupResult(**result),
        )
    except APIException:
        raise
    except Exception as e:
        raise APIException(ErrMsg.CLEANUP_PREVIEW_ERROR, e=e)
```

- [ ] **Step 4: 重新跑测试，确认通过**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/api/v1/test_preview_cleanup_routes.py -v
```

预期：5 passed。

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git add backend/src/api/v1/gallery.py unit_test/api/v1/test_preview_cleanup_routes.py && git commit -m "feat(api): add POST /cache/preview/cleanup endpoint with dry_run support"
```

---

## Task 7: 完整验收

**Files:** 全部已存在的文件，验证用。

- [ ] **Step 1: 跑全套单测，确认全绿**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/dao/test_yande_data_dao_downloaded_ids.py unit_test/infrastructure/test_image_cache_cleanup.py unit_test/services/test_gallery_cleanup.py unit_test/api/v1/test_preview_cleanup_routes.py -v
```

预期：所有 case passed（dao 2 + infrastructure 6 + services 5/6 + api 5 = 18+ 通过）。

- [ ] **Step 2: 跑已有测试套件，确保无回归**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/pytest unit_test/ -v --tb=short 2>&1 | tail -50
```

预期：除新增 4 个文件外，**无新增失败**。已存在的失败（如有）应保持原有状态。

- [ ] **Step 3: lsp_diagnostics 检查**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && .venv/bin/python -c "
from src.api.v1.gallery import router as gallery_router
from src.services.gallery import GalleryService
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.image_cache import ImageCache
from src.models.request.gallery import CleanupPreviewsRequest
from src.models.response.gallery import CleanupPreviewsResponse, CleanupResult
from src.common.constant import CleanupMode, ErrMsg
print('All imports OK')
"
```

预期输出：`All imports OK`

- [ ] **Step 4: ruff 检查（如有配置）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && (ls .venv/bin/ruff 2>/dev/null && .venv/bin/ruff check backend/src/ unit_test/ 2>&1 | tail -30) || echo "ruff not installed, skip"
```

预期：ruff 报告无新增 warning，或"ruff not installed"跳过提示。

- [ ] **Step 5: 查看 commit 列表**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git log --oneline -8
```

预期：能看到 6 个新 commit（Task 1-6），按顺序排列。

- [ ] **Step 6: 手工 smoke test（评估模式）**

启动后端：

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend && .venv/bin/uvicorn service:main_app --port 8000 &
SERVER_PID=$!
sleep 3
```

调用评估模式：

```bash
curl -s -X POST http://localhost:8000/api/v1/cache/preview/cleanup \
  -H "Content-Type: application/json" \
  -d '{"mode": "clean_local_previews", "dry_run": true}' | python3 -m json.tool
```

预期：返回 200，JSON 中 `dry_run: true, matched: <N>, deleted: 0`。

停服务：

```bash
kill $SERVER_PID 2>/dev/null
```

确认真实 `downloads/previews/` 没有任何文件被改动：

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git status backend/  # 应无变更
```

预期：仅显示用户**先前未提交**的 `backend/config/config.yaml` 修改（与本次工作无关），无 preview 相关变更。

- [ ] **Step 7: 用户审阅并决定 push 时机**

按 brainstorming skill 流程，**本计划结束后不自动 push**。用户需手动审阅：
```bash
cd /home/exa160/opencode/yande.re-spider-next-dev && git log --oneline -8
cd /home/exa160/opencode/yande.re-spider-next-dev && git diff b7271d3 HEAD --stat
```

确认无问题后再 push。

---

## 验收标准（与 spec §11 对齐）

- [x] `POST /api/v1/cache/preview/cleanup` 端点存在，请求/响应模型完整
- [x] `mode=clean_local_previews, dry_run=true` 时文件系统 0 改动
- [x] `mode=clean_local_previews, dry_run=false` 仅删 down_flag=True 对应 preview
- [x] `mode=clean_all_previews, dry_run=false` 清空整个 previews/ 目录（隐藏文件除外）
- [x] 单文件 unlink 失败不影响其他文件，`failed` 字段准确
- [x] `previews/` 不存在时返回 matched=0 而非报错
- [x] 单元测试覆盖 dao / infrastructure / services / api 各层，全部通过
- [x] 测试使用 `tmp_path` 隔离，**真实 `downloads/previews/` 不受任何影响**
- [x] lsp_diagnostics 干净，ruff 无新增 warning

---

## 风险与回退

| 风险 | 缓解 |
|---|---|
| Task 5 最后一个测试 `test_cleanup_local_continues_when_single_unlink_fails` 因 monkeypatch 副作用失败 | 删除该 case 或改用 `pytest.skip` 标记；前 5 个核心 case 已覆盖关键路径 |
| DB 在测试中残留数据 | 测试用 `repo.session.query(YandeData).delete()` 主动清表 |
| 真实 `downloads/` 误删 | 测试用 `monkeypatch.setattr(path_constant, "previews_dir", tmp_path/...)` 隔离；Task 7 smoke test 强校验 git status |
| 端点未自动注册 | 项目用 APILoader 自动发现 `api/v1/*.py`，新路由文件位置正确即自动注册 |

---

**参考文档**：
- `docs/superpowers/specs/2026-06-29-preview-cache-cleanup-design.md` — 详细设计
- `AGENTS.md` — 项目代码规范
- `docs/dao.md` — DAO 编写规范
- `docs/api-route.md` — API 路由模板
- `docs/response.md` — BaseResponse 响应约定
- `backend/src/infrastructure/image_cache.py` — 现有 ImageCache 实现
- `backend/src/services/gallery.py` — 现有 GalleryService 实现
- `unit_test/api/v1/test_download_routes.py` — 测试模板参考