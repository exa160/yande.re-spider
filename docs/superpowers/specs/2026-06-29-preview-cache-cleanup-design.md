# Preview 缩略图清理功能 — 设计

**日期**：2026-06-29
**状态**：待批准
**作者**：Sisyphus
**范围**：后端（API/Service/DAO/Infrastructure）+ 单元测试（仅后端，前端后续按需）
**相关背景**：`downloads/previews/` 是浏览图库时下载/生成的缩略图缓存；本地图库模式下，用户希望只保留由大图本地生成的高质量缩略图，清理在线下载的低质量副本以释放磁盘空间。

---

## 1. 背景

### 1.1 现状

`previews/` 目录缩略图来源混杂：

| 来源 | 调用路径 | 文件名 | 质量 |
|---|---|---|---|
| 在线下载 | `ImageCache.download_preview` / `GalleryService.fetch_and_cache_preview` | `{id}.jpg` | yande.re 服务端下采样图，分辨率较小 |
| 本地生成 | `GalleryService.generate_preview` / `get_preview_for_local` | `{id}.jpg` | 从 `originals/{id}.{ext}` 缩放到 600×600 内的 JPEG，质量更高 |

两类来源**物理上落在同一个目录、同一套文件名**，文件层面无法区分。

### 1.2 触发问题

用户在浏览本地图库时，preview 优先由本地大图生成（高质量），但早期缓存的在线 preview（低质量）若仍残留，会在切到非本地模式或首次访问时优先返回（`if preview_path.exists()` 短路）。同时，`previews/` 长期累积占磁盘。

### 1.3 目标

- **核心**：提供一个后端 API，能按"清理策略"删除 `previews/` 下的缩略图。
- **核心**：内置 **dry_run 评估模式**（默认开启），删除前必先看到将删多少、释放多少字节。
- **次要**：策略可扩展（未来可加"按日期范围"、"按大小阈值"等），本次只实现两种基础策略。

### 1.4 非目标

- 不清理 `originals/`（原图目录用户资产，不动）
- 不清理数据库（只清理磁盘缓存）
- 不做前端按钮（仅后端 API，后续按需）
- 不做定时清理（手动触发）
- 不做并发清理协调（当前项目无并发写 preview，足够简单）
- 不实现按文件大小阈值/按日期清理（YAGNI；留扩展点）

---

## 2. 命名澄清

用户原命名"本地清理 / 在线清理"易混淆（既可指来源，也可指作用域），改为**按作用域**命名：

| 用户原命名 | 准确含义 | 新命名（API mode 值） | 中文标签 |
|---|---|---|---|
| 本地清理 | 清"对应原图已下载"的 preview（可由大图再生） | `clean_local_previews` | **局部清理** |
| 在线清理 | 清 `previews/` 目录下所有 preview | `clean_all_previews` | **全量清理** |

---

## 3. 架构概览

```
┌─────────────────────────────────────────────────────┐
│  Client                                             │
│  POST /api/v1/cache/preview/cleanup                 │
│  Body: { mode: 'clean_local_previews' |             │
│          'clean_all_previews',                      │
│         dry_run: true }                             │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│  API: src/api/v1/gallery.py                         │
│  POST /cache/preview/cleanup                        │
│    Request: CleanupPreviewsRequest                  │
│    Response: CleanupPreviewsResponse                │
│    → GalleryService.cleanup_previews(mode, dry_run) │
└────────────────────┬────────────────────────────────┘
                     ▼
┌─────────────────────────────────────────────────────┐
│  Service: src/services/gallery.py                   │
│  GalleryService.cleanup_previews(mode, dry_run)     │
│    ├─ cache.list_preview_files()                    │
│    ├─ (clean_local_previews)                        │
│    │    YandeDataRepository.get_downloaded_ids()    │
│    │    → 过滤命中集合的文件                         │
│    └─ cache.safe_unlink() × N                       │
└────────────┬─────────────────┬───────────────────────┘
             ▼                 ▼
┌────────────────────┐  ┌────────────────────────────────┐
│ DAO: yande_data_   │  │ ImageCache: list + safe_unlink │
│      dao.py        │  │      (src/infrastructure/      │
│ get_downloaded_ids │  │       image_cache.py)          │
│  (SELECT id WHERE  │  │  os.scandir / Path.unlink      │
│   down_flag=True)  │  │                                │
└────────────────────┘  └────────────────────────────────┘
```

---

## 4. API 设计

### 4.1 端点

| 项目 | 值 |
|---|---|
| 方法 | `POST` |
| 路径 | `/api/v1/cache/preview/cleanup` |
| 请求模型 | `CleanupPreviewsRequest` |
| 响应模型 | `CleanupPreviewsResponse` |

### 4.2 请求模型

```python
# backend/src/models/request/gallery.py
from src.common.constant import CleanupMode


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

### 4.3 响应模型

```python
# backend/src/models/response/gallery.py
from src.models.response.base_response import BaseResponse


class CleanupResult(BaseModel):
    """清理结果"""

    mode: str = Field(..., description="实际执行的清理模式")
    dry_run: bool = Field(..., description="是否为评估模式")
    matched: int = Field(..., description="命中文件数（dry_run 时也是这个数）")
    deleted: int = Field(..., description="实际删除文件数（dry_run 时为 0）")
    failed: int = Field(..., description="删除失败文件数（权限/占用）")
    total_bytes: int = Field(..., description="命中文件总字节数")
    duration_ms: int = Field(..., description="处理耗时（毫秒）")


class CleanupPreviewsResponse(BaseResponse[CleanupResult]):
    """预览图清理响应"""

    ...
```

### 4.4 响应示例

```json
{
  "message": "OK.",
  "data": {
    "mode": "clean_local_previews",
    "dry_run": true,
    "matched": 1234,
    "deleted": 0,
    "failed": 0,
    "total_bytes": 52428800,
    "duration_ms": 142
  }
}
```

---

## 5. 业务逻辑

### 5.1 核心算法（Service 层）

```python
# backend/src/services/gallery.py
import time
from typing import Optional

from src.common.constant import CleanupMode, ErrMsg, path_constant
from src.dao.yande_data_dao import YandeDataRepository
from src.infrastructure.image_cache import ImageCache
from src.middleware.errors import APIException


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

    # 1) 目录不存在 → 返回空结果（首次启动友好）
    if not previews_dir.exists():
        return _empty_result(mode, dry_run)

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
            image_id = _parse_image_id(p.name)
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


def _empty_result(mode: CleanupMode, dry_run: bool) -> dict:
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


def _parse_image_id(filename: str) -> Optional[int]:
    """从 preview 文件名解析 image_id。文件名约定：{id}.{ext}，跳过隐藏文件"""
    if filename.startswith("."):
        return None
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    try:
        return int(stem)
    except ValueError:
        return None
```

### 5.2 ImageCache 扩展

```python
# backend/src/infrastructure/image_cache.py
import os
from pathlib import Path
from loguru import logger


class ImageCache:
    # ... 既有代码 ...

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

### 5.3 DAO 扩展

```python
# backend/src/dao/yande_data_dao.py
from sqlalchemy import select


class YandeDataRepository(BaseDAO):
    # ... 既有代码 ...

    def get_downloaded_ids(self) -> set[int]:
        """查询所有已下载原图的 image_id（单次 SQL，仅取 id 字段）

        Returns:
            set[int]: down_flag=True 的 image_id 集合
        """
        stmt = select(YandeData.id).where(YandeData.down_flag.is_(True))
        rows = self.session.execute(stmt).scalars().all()
        return set(rows)
```

### 5.4 常量与枚举

```python
# backend/src/common/constant.py
class CleanupMode(str, Enum):
    """预览图清理模式"""
    CLEAN_LOCAL_PREVIEWS = "clean_local_previews"  # 局部清理
    CLEAN_ALL_PREVIEWS = "clean_all_previews"      # 全量清理


class ErrMsg(BaseMsgEnum):
    # ... 既有代码 ...
    CLEANUP_PREVIEW_ERROR = ("0013", "Failed to cleanup preview cache.", HTTPStatus.INTERNAL_SERVER_ERROR)
```

### 5.5 API 路由

```python
# backend/src/api/v1/gallery.py
from src.common.constant import CleanupMode, ErrMsg
from src.models.request.gallery import CleanupPreviewsRequest
from src.models.response.gallery import CleanupPreviewsResponse, CleanupResult


@router.post(
    "/cache/preview/cleanup",
    response_model=CleanupPreviewsResponse,
    summary="清理 preview 缩略图缓存",
)
async def cleanup_previews(request: CleanupPreviewsRequest) -> CleanupPreviewsResponse:
    """清理 preview 缩略图（支持评估模式 dry_run）"""
    try:
        result = GalleryService.cleanup_previews(
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

---

## 6. 错误处理

| 场景 | 行为 |
|---|---|
| `previews/` 目录不存在 | 返回 matched=0，不抛错（首次启动友好） |
| 文件名为隐藏文件（`.DS_Store`、`.gitkeep` 等） | 解析 image_id 失败 → 跳过；CLEAN_ALL_PREVIEWS 模式下也不删隐藏文件 |
| 文件名格式非法（无法解析为 int） | 跳过该文件，不计入 matched |
| 单个文件 unlink 失败（权限/占用） | 计入 `failed`，继续处理其他文件；不抛错 |
| 文件 stat 失败（扫描中被外部删除） | 跳过，不计入 total_bytes |
| 数据库连接/查询失败 | 抛 `APIException(ErrMsg.QUERY_ERROR, e=e)` |
| `mode` 枚举值非法 | Pydantic 校验自动返回 422 |
| `dry_run` 字段缺失 | Pydantic 默认值为 True（安全默认） |

---

## 7. 性能考虑

- `list_preview_files()` 用 `os.scandir` 而非 `listdir` + 多次 `stat`，单次系统调用返回 DirEntry
- `get_downloaded_ids()` 单次 SQL，仅查 `id` 字段（轻量级；万级数据毫秒级返回）
- `total_bytes` 计算在已过滤后的 `targets` 列表上，O(matched)；matched 太大时（>10万）考虑异步或加进度回调（本期不做）
- 不删除整个目录树（保留目录本身），逐个 `unlink` 便于错误隔离

---

## 8. 测试计划

### 8.1 单元测试（`unit_test/api/v1/test_preview_cleanup.py` + `unit_test/services/test_gallery_cleanup.py`）

| # | 测试 | 关注点 |
|---|---|---|
| T1 | `cleanup_previews(mode=CLEAN_LOCAL_PREVIEWS, dry_run=True)` | 文件系统**完全不动**（md5 比对） |
| T2 | `cleanup_previews(mode=CLEAN_LOCAL_PREVIEWS, dry_run=False)` | 仅删 `down_flag=True` 对应的 preview |
| T3 | `cleanup_previews(mode=CLEAN_ALL_PREVIEWS, dry_run=False)` | 清空整个 previews/ 目录 |
| T4 | `cleanup_previews(mode=CLEAN_LOCAL_PREVIEWS)` 包含隐藏文件 | 隐藏文件跳过不删 |
| T5 | `cleanup_previews` 单个文件 unlink 失败（mock） | 其他文件继续删，`failed` 计数正确 |
| T6 | `previews/` 不存在 | 返回 matched=0，不抛错 |
| T7 | `get_downloaded_ids()` 返回正确集合 | 仅 down_flag=True 的 ID |
| T8 | `_parse_image_id()` 各种文件名 | 隐藏文件/非法格式返回 None |
| T9 | API `POST /cache/preview/cleanup` dry_run=true | 响应结构正确，文件未删 |
| T10 | API `POST /cache/preview/cleanup` dry_run=false | 真实删除，响应正确 |
| T11 | API 非法 mode | 422 Pydantic 校验 |
| T12 | API dry_run 默认值 | 缺省字段时为 True（安全默认） |

### 8.2 测试隔离

- 用 `tmp_path` + `monkeypatch.setattr(path_constant, "previews_dir", tmp_path / "previews")`，**完全不污染真实 `downloads/`**
- DAO 测试用 SQLite 内存库 + 临时 fixture
- 真实集成测试由用户手工触发：开发期所有真删请求都先 `dry_run=true` 看响应再决定

### 8.3 手工验证脚本（建议加入 Makefile 或 docs）

```bash
# 评估模式（推荐每次清理前先跑）
curl -X POST http://localhost:8000/api/v1/cache/preview/cleanup \
  -H "Content-Type: application/json" \
  -d '{"mode": "clean_local_previews", "dry_run": true}'

# 确认无误后真删
curl -X POST http://localhost:8000/api/v1/cache/preview/cleanup \
  -H "Content-Type: application/json" \
  -d '{"mode": "clean_local_previews", "dry_run": false}'
```

---

## 9. 文件改动清单

| 文件 | 改动 | 行数估算 |
|---|---|---|
| `backend/src/common/constant.py` | 新增 `CleanupMode` 枚举 + `ErrMsg.CLEANUP_PREVIEW_ERROR` | +6 / -0 |
| `backend/src/models/request/gallery.py` | 新增 `CleanupPreviewsRequest` | +20 |
| `backend/src/models/response/gallery.py` | 新增 `CleanupResult` + `CleanupPreviewsResponse` | +25 |
| `backend/src/dao/yande_data_dao.py` | 新增 `get_downloaded_ids()` 方法 | +10 / -0 |
| `backend/src/services/gallery.py` | 新增 `cleanup_previews()` + `_parse_image_id()` 辅助 | +60 / -0 |
| `backend/src/infrastructure/image_cache.py` | 新增 `list_preview_files()` + `safe_unlink()` | +20 / -0 |
| `backend/src/api/v1/gallery.py` | 新增 `POST /cache/preview/cleanup` 路由 | +20 / -0 |
| `unit_test/api/v1/test_preview_cleanup.py` | 新增 API 集成测试 | +120 |
| `unit_test/services/test_gallery_cleanup.py` | 新增 Service 单元测试 | +150 |

总计：约 +430 行，0 删除。

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解 |
|---|---|---|
| 误删在线缓存导致用户再次访问时变慢 | 用户感知 | dry_run 默认 True；前端调用方需明示 `dry_run=false` |
| 大目录遍历慢（>10万文件） | API 响应延迟 | 本期不优化；后续可加 `max_files` 参数或异步任务 |
| 数据库 `down_flag=True` 与实际 `originals/` 文件不一致 | 误判 | `get_downloaded_ids` 用 DB 真实状态为权威；不一致属于历史遗留问题 |
| 与同时进行中的下载任务冲突 | 极小概率 unlink 失败 | `safe_unlink` 吞 OSError 计入 `failed`，不中断 |
| 用户期望"清预览但不影响浏览体验" | 重新生成需要时间 | `get_preview_for_local` 会自动从原图再生，体验可接受 |

---

## 11. 验收标准

- [ ] `POST /api/v1/cache/preview/cleanup` 端点存在，请求/响应模型定义完整
- [ ] `mode=clean_local_previews, dry_run=true` 时文件系统 0 改动
- [ ] `mode=clean_local_previews, dry_run=false` 仅删 down_flag=True 对应 preview
- [ ] `mode=clean_all_previews, dry_run=false` 清空整个 previews/ 目录（隐藏文件除外）
- [ ] 单文件 unlink 失败不影响其他文件，`failed` 字段准确
- [ ] `previews/` 不存在时返回 matched=0 而非报错
- [ ] 单元测试覆盖 T1-T12 全部场景，全部通过
- [ ] 测试使用 `tmp_path` 隔离，**真实 downloads/ 不受任何影响**
- [ ] `lsp_diagnostics` 干净，ruff 无 warning

---

## 12. 后续优化（本次不实现）

- [ ] 前端"清理预览"按钮（按 mode 选择 + 确认弹窗 + 释放空间显示）
- [ ] 按文件大小阈值清理（保留最近/最大 N 个）
- [ ] 按日期范围清理（超过 N 天的自动清）
- [ ] 异步清理 + WebSocket 进度推送（针对超大规模目录）
- [ ] 定时清理任务（cron 触发）
- [ ] 与 `download_history` 表联动（清理已下载 N 次的图片的 preview）

---

**参考文档**：
- `AGENTS.md` — 项目代码规范
- `docs/dao.md` — DAO 编写规范
- `docs/api-route.md` — API 路由模板
- `docs/response.md` — BaseResponse 响应约定
- `docs/error-handling.md` — ErrMsg 与 APIException 约定
- `backend/src/infrastructure/image_cache.py` — 现有 ImageCache 实现
- `backend/src/services/gallery.py` — 现有 GalleryService 实现