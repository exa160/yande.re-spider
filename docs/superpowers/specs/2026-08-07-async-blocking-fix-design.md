# 异步路由事件循环阻塞修复 — 设计文档

**状态**：Draft
**日期**：2026-08-07
**分支**：`feature-segments-responsive`（当前分支）
**类型**：Bug 修复 + 性能优化
**影响**：API 路由层、中间件、配置容量

---

## 1. 目标

修复在线模式（yande.re API 调用）和缩略图加载时事件循环被冻结、进而阻塞所有其他 API 的问题。

修复完成后：
- 任意慢操作（在线模式 HTTP、缩略图下载、整文件 MD5）不再冻结事件循环
- 其他 API 在慢操作进行时仍可正常响应
- 缩略图 fetch 永不无限挂起（统一应用 `config.yande_api.timeout`）
- DB 连接池在并发场景下更快失败而非长时等待

---

## 2. 背景：阻塞根因

> 完整诊断见 brainstorm 阶段产出（不在本 spec 重复）。简述如下：

| 层 | 问题 | 严重度 |
|---|---|---|
| **API 路由** | 56 个 async 路由中 40 个直接调用同步 service/DAO（favorites/download/tag_cache/config 全军覆没） | 🔴 HIGH |
| **API 路由** | `favorites.refresh_online_count` 在事件循环里同步 HTTP 到 yande.re（5-30s） | 🔴 HIGH |
| **API 路由** | `gallery.get_gallery_statistics` 同步拉 10000 条记录 | 🔴 HIGH |
| **中间件** | `RequestSessionMiddleware` 的 `await session.rollback()` 是 bug（`Session.rollback()` 同步返回 `None`，`await None` 抛 TypeError） | 🔴 HIGH |
| **下载 worker** | `run_download_async` 在事件循环里做整文件 MD5 读取 | 🔴 HIGH |
| **缩略图** | `ImageCache._with_retry_write` 调用 `self._session.get(url)` **不传** `timeout=`（设了 `session.timeout` 但 requests 不读这个属性） | 🟠 MEDIUM |
| **DB** | 连接池 `pool_size=5 / max_overflow=10 / pool_timeout=30` 在并发 15+ 时新请求等满 30s | 🟠 MEDIUM |
| **DAO 单例** | `BaseDAO.session` 在请求外时走 `except Exception → _get_session_factory()()` 静默 fallback，造未托管 Session、连接泄漏 | 🟠 MEDIUM |
| **调度回调** | `scheduler._on_folder_trigger` 在 AsyncIOScheduler 回调里同步 `favorite_dao.get_by_id` | 🟠 MEDIUM |

---

## 3. 目标 / 非目标

### 3.1 目标（必做）

1. 所有 async 路由的同步 service/DAO 调用 → 用 `asyncio.to_thread` 包裹
2. 缩略图 fetch 显式 `timeout=config.yande_api.timeout`
3. `RequestSessionMiddleware` 的 `await session.rollback()` bug 修复
4. 下载 worker 整文件 MD5 → `to_thread`
5. 调度回调 `_on_folder_trigger` 的同步 DAO → `to_thread`
6. DB 连接池参数调优：`pool_size=10 / max_overflow=20 / pool_timeout=10`
7. BaseDAO 静默 fallback：去掉 `except Exception` 兜底，缺请求上下文时显式报错（与中间件 `get_session()` 严格模式一致）

### 3.2 非目标（明确不做）

- **不**迁移到 `AsyncSession` / `httpx` / `aiosqlite`（架构级，按用户决策留在 Phase 2）
- **不**重写 BaseDAO
- **不**改动 DAO 方法签名
- **不**改动 service 公共接口（业务逻辑保持一致）
- **不**改动前端

---

## 4. 设计

### 4.1 全局约定

**约定 A**：`async def` 路由内**禁止**直接调用以下对象的方法：
- `favorite_dao.*`、`yande_data_repository.*`、`tag_repository.*`、`artist_repository.*`、`download_task_dao.*`
- `*Service.*`（service 方法都是同步的，必须 `to_thread`）
- `YandeApi.*`、`ImageCache.*`（含 `requests.Session` + 文件 IO）

**例外**：
- `await asyncio.to_thread(...)` 包装后 ✓
- `run_in_executor(None, ...)` 包装后 ✓
- 已用 `@property` 暴露的纯内存访问 ✓

**约定 B**：所有 service 方法仍保持同步签名。修改**只发生在 API 路由层**，service/DAO/基础设施层零改动。

**约定 C**：现有 `gallery.py` 已正确使用 `to_thread` 的位置（`load_gallery`、`get_image_detail`、`generate_preview_from_original`、`get_preview_for_local`、`fetch_and_cache_preview`、`cleanup_previews`）保持不变，只补 `get_gallery_statistics` 一处遗漏。

---

### 4.2 改动 1：API 路由统一包 `asyncio.to_thread`

#### 4.2.1 `backend/src/api/v1/favorites.py`

15 个 async 路由全部需要包 `to_thread`。按改动大小分两类：

**类型 A：纯调用 service，wrap 整段调用**
```python
@router.get("", response_model=FavoriteFoldersResponse, summary="获取所有收藏夹")
async def get_all_folders() -> FavoriteFoldersResponse:
    """获取所有收藏夹，按排序权重排列"""
    try:
        folders = await asyncio.to_thread(FavoritesService.get_all_folders)
        return FavoriteFoldersResponse(data=folders)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

**类型 B：路由内同时含 DAO 调用和服务调用（如 schedule trigger）**
```python
@router.post("/{folder_id}/schedule/trigger", response_model=ScheduleTriggerResponse, summary="手动触发收藏夹调度")
async def trigger_folder_schedule(folder_id: int) -> ScheduleTriggerResponse:
    """..."""
    from src.services.favorite_scheduler import run_folder_schedule

    # 同步 DAO 调用包 to_thread
    folder = await asyncio.to_thread(favorite_dao.get_by_id, folder_id)
    if not folder:
        raise APIException(ErrMsg.FAVORITE_FOLDER_NOT_FOUND)
    asyncio.create_task(run_folder_schedule(folder_id))
    return ScheduleTriggerResponse(
        message="已触发，请通过 /schedule/status 查询进度",
        data=ScheduleTriggerStatsData(status="queued"),
    )
```

#### 4.2.2 `backend/src/api/v1/download.py`

12 个 async 路由。最危险的点：`create_batch_download_tasks` 对每个 image_id 同步 SELECT。需包 `to_thread`。

`DownloadService` 中 `get_tasks` 内部取了全局 `threading.Lock`，仍需 `to_thread`，避免锁竞争冻结事件循环。

```python
@router.post("/task/batch", ...)
async def create_batch_download_tasks(tasks: List[DownloadTaskCreate]) -> BatchTaskCreatedResponse:
    try:
        image_ids = [task.image_id for task in tasks]
        task_ids = await asyncio.to_thread(
            DownloadService.create_batch_tasks, image_ids
        )
        ...
```

#### 4.2.3 `backend/src/api/v1/tag_cache.py`

7 个统计/搜索路由。`refresh_tags` / `refresh_artists` 已用 `to_thread`/`run_in_executor`，**保留不动**。

```python
@router.get("/tags/stats", response_model=BaseResponse, summary="获取标签缓存统计")
async def get_tags_stats() -> BaseResponse:
    try:
        stats = await asyncio.to_thread(TagCacheService.get_tags_stats)
        return BaseResponse(message=ErrMsg.OK.msg, data=stats)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

#### 4.2.4 `backend/src/api/v1/config.py`

6 个路由。`update_api_config` / `update_downloader_config` / `update_database_config` / `reset_config` 都是同步 YAML 写。`test_database_connection` 是同步 `engine.connect()`（MariaDB 分支可能阻塞数秒）。

```python
@router.put("/database", response_model=BaseResponse, summary="更新数据库配置")
async def update_database_config(database_config: DatabaseConfig) -> BaseResponse:
    try:
        success = await asyncio.to_thread(
            ConfigService.update_database_config, database_config
        )
        if not success:
            raise APIException(ErrMsg.CONFIG_UPDATE_ERROR)
        return BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)
    except Exception as e:
        raise APIException(ErrMsg.CONFIG_UPDATE_ERROR, e=e)
```

#### 4.2.5 `backend/src/api/v1/gallery.py`

只补 `get_gallery_statistics` 一处。

```python
@router.get("/statistics", response_model=BaseResponse, summary="获取图库统计")
async def get_gallery_statistics(
    source: str = Query("local", description="数据源"),
) -> BaseResponse:
    """获取图库统计信息"""
    try:
        stats = await asyncio.to_thread(GalleryService.get_statistics, source)
        return BaseResponse(message=ErrMsg.OK.msg, data=stats)
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)
```

#### 4.2.6 `backend/src/api/v1/query.py`

无 DAO 调用，纯内存占位。**不动**。

---

### 4.3 改动 2：`ImageCache` 缩略图下载加 timeout

**问题**：`self._session.timeout = config.yande_api.timeout` 设了但 `requests.Session.get()` 不读这个属性（`requests` 库只读 `timeout=` 参数）。

```python
# backend/src/infrastructure/image_cache.py
def _with_retry_write(method):
    @wraps(method)
    def wrapper(self, url: str, image_id: int, file_ext: str = "jpg") -> Path:
        dest_path = method(self, image_id, file_ext)
        if dest_path.exists():
            return dest_path

        self._ensure_dirs()
        last_exception = None
        action_name = method.__name__.replace("_", " ")

        for attempt in range(config.yande_api.retry):
            try:
                resp = self._session.get(
                    url,
                    timeout=config.yande_api.timeout,  # ← 新增：显式传 timeout
                )
                resp.raise_for_status()
                dest_path.write_bytes(resp.content)
                return dest_path
            except requests.RequestException as e:
                ...
```

同时移除无用的 `self._session.timeout = config.yande_api.timeout`（line 50）。

---

### 4.4 改动 3：`RequestSessionMiddleware` bug 修复

**问题 1（bug）**：`Session.rollback()` 同步方法，`await session.rollback()` 等于 `await None` → TypeError。

```python
# backend/src/middleware/session.py
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
        session.rollback()  # ← 改：去掉 await
        raise
    finally:
        _request_session.reset(token)
        session.close()
```

**问题 2（延迟提交冻结）**：`session.commit()` 在事件循环里执行，但发生在响应已发送给客户端之后（`await self.app()` 已返回），不影响用户感知延迟。**保持同步，不动**。

---

### 4.5 改动 4：下载 worker 整文件 MD5 移出事件循环

**问题**：`run_download_async` 在 `original_path.exists() and expected_md5` 分支，整文件读 + MD5 在事件循环跑。100MB 文件 = 几秒到几十秒冻结。

```python
# backend/src/infrastructure/download_queue.py
if original_path.exists() and expected_md5:
    def _compute_md5():
        md5_hasher = hashlib.md5()
        with original_path.open("rb") as existing_file:
            for chunk in iter(lambda: existing_file.read(1024*1024), b""):
                md5_hasher.update(chunk)
        return md5_hasher.hexdigest()

    file_md5 = await asyncio.to_thread(_compute_md5)
    if file_md5 == expected_md5:
        logger.info(
            f"Original exists and MD5 matches ({file_md5}), skipping download"
        )
        need_download = False
    else:
        logger.info(f"Original exists but MD5 mismatch, re-downloading")
        await asyncio.to_thread(original_path.unlink)
```

---

### 4.6 改动 5：调度回调的同步 DAO 包 `to_thread`

```python
# backend/src/infrastructure/scheduler.py
async def _on_folder_trigger(folder_id: int) -> None:
    """定时触发入口"""
    from src.services.favorite_scheduler import run_folder_schedule
    from src.dao.favorite_dao import favorite_dao

    folder = await asyncio.to_thread(favorite_dao.get_by_id, folder_id)
    if not folder:
        ...
    asyncio.create_task(run_folder_schedule(folder_id))
```

---

### 4.7 改动 6：DB 连接池调参

```python
# backend/src/dao/database.py
_cached_engine = create_engine(url,
    pool_recycle=1800,
    pool_pre_ping=True,
    pool_use_lifo=True,
    pool_reset_on_return="rollback",
    connect_args={"connect_timeout": 10},
    echo=False,
    pool_size=10,          # 原 5：双倍基础连接
    max_overflow=20,       # 原 10：双倍溢出
    pool_timeout=10,       # 原 30：失败更快，避免长时等连接
)
```

理由：
- `pool_size=10` 与 `max_concurrent_tasks=3`（下载）+ 缩略图并发 + 在线 API 共享池，规模匹配
- `max_overflow=20` 总 30 连接容纳突发
- `pool_timeout=10` 配合 `connect_timeout=10`，避免单连接卡 30s

---

### 4.8 改动 7：BaseDAO 静默 fallback 去除

```python
# backend/src/dao/database.py
@property
def session(self) -> Session:
    if self._session is not None:
        return self._session
    # 单例路径: 每次从 ContextVar 拿当前请求 session
    from src.middleware.session import RequestSessionMiddleware
    return RequestSessionMiddleware.get_session()  # ← 改：去掉 try/except 静默 fallback
```

理由：`get_session()` 已改为严格模式（request 缺上下文时抛 `RuntimeError`），与中间件语义一致。请求外的 DAO 调用（如调度）必须用 `with FavoriteDao() as dao:` 显式创建 session。

**影响**：
- 所有 inline 调用（路由 → service → `dao.xxx()`）在请求中是安全的
- `run_folder_schedule` / `_update_image_database` / `_load_folder_for_schedule` 等已在 `with FavoriteDao() / YandeDataRepository() as ...:` 上下文内 ✓
- `scheduler._on_folder_trigger` 改为 `to_thread(favorite_dao.get_by_id, ...)`，但**单例路径仍走 `RequestSessionMiddleware.get_session()`**，此时 ContextVar 必然 None → 抛错

**配套修复**：调度回调也走 `with` 上下文：

```python
# scheduler.py
async def _on_folder_trigger(folder_id: int) -> None:
    from src.services.favorite_scheduler import run_folder_schedule
    from src.dao.favorite_dao import FavoriteDao

    def _load_and_check() -> Optional[FavoriteFolder]:
        with FavoriteDao() as dao:
            folder = dao.get_by_id(folder_id)
            return folder

    folder = await asyncio.to_thread(_load_and_check)
    ...
```

---

## 5. 错误处理

- `asyncio.to_thread` 包装后，原 service 抛出的 `APIException` 会被原样上抛 → 中间件 `ErrorHandleMiddleware` 正常处理 ✓
- 原 service 抛出的 `ValueError` / `RuntimeError` 等同样上抛，由路由 `try/except` 转 `APIException` ✓
- 不改变任何错误响应格式

---

## 6. 测试策略

### 6.1 单元测试

**位置**：`backend/tests/` 和 `unit_test/`（沿用现有约定）

#### 测试 6.1.1：所有 async 路由不直接同步调 DAO
**目的**：防止 PR 重蹈覆辙。
**方法**：编写一个 fixture，monkey-patch 所有 DAO 单例，断言其方法**从未在事件循环线程同步调用**。
**具体**：用 `asyncio.get_running_loop().run_in_executor` 包装器记录每次 DAO 调用所在线程；所有调用必须不在主事件循环线程。

> 简化版：写一个 `test_no_sync_dao_in_async_routes.py`，import 所有路由模块的 `async def`，对每个函数做静态扫描，确认函数体内**没有**以下未包裹的同步调用：
> - `favorite_dao.*`、`tag_repository.*`、`artist_repository.*`、`download_task_dao.*`、`yande_data_repository.*`
> - `*Service.*`（service 方法都是同步的）
> - `YandeApi(`、`ImageCache(` 实例化和方法调用
>
> 排除项：`asyncio.to_thread(...)`、`run_in_executor(...)`、纯内存属性访问。

#### 测试 6.1.2：`ImageCache.download_preview` 显式 timeout
```python
def test_image_cache_uses_configured_timeout(monkeypatch):
    captured = {}
    class FakeSession:
        def get(self, url, **kwargs):
            captured.update(kwargs)
            raise requests.exceptions.Timeout()
    monkeypatch.setattr("src.infrastructure.image_cache.config.yande_api.timeout", 17)
    cache = ImageCache()
    cache._session = FakeSession()
    with pytest.raises(requests.exceptions.Timeout):
        cache.download_preview(123, "jpg")
    assert captured["timeout"] == 17
```

#### 测试 6.1.3：`RequestSessionMiddleware` 不再 `await None`
**方法**：mock 一个会抛异常的 endpoint，断言 `rollback()` 被调用 1 次且没抛 TypeError。

#### 测试 6.1.4：BaseDAO 单例在请求外抛错
```python
def test_base_dao_session_outside_request_raises():
    with pytest.raises(RuntimeError, match="RequestSessionMiddleware not active"):
        FavoriteDao().session
```

### 6.2 手动集成验证

修复完成后人工跑：
1. 浏览器在线模式加载（10+ 张缩略图）→ 同时点开收藏夹 / 任务列表 / 配置页 → 都正常响应
2. 触发 `POST /favorites/{id}/refresh-online` → 同时其他 API 仍响应
3. 故意把 yande.re timeout 调到 1 秒 → 缩略图 fetch 1 秒后失败而非无限挂起

---

## 7. 兼容性 & 风险

### 7.1 向后兼容

- API 响应格式 0 变化
- 行为 0 变化（仅增加并发能力）
- DB schema 0 变化
- 配置项 0 变化（连接池参数是代码常量，不是配置项）

### 7.2 风险

| 风险 | 缓解 |
|---|---|
| `to_thread` 在 DB session 跨线程导致 SQLAlchemy 报错 | `RequestSessionMiddleware.get_session()` 在 `to_thread` 内仍能拿到 ContextVar 吗？**能**：ContextVar 跨 `to_thread` 自动传播。已用 `5df7399` 验证 |
| 调度回调 `to_thread` 后 `get_session()` 抛错 | 配套改成 `with FavoriteDao() as dao:` 显式上下文 |
| 连接池调参导致 idle 连接数变多 | MariaDB 默认 `wait_timeout=28800`，30 个 idle 连接没问题 |
| 单元测试 `test_no_sync_dao_in_async_routes` 太严会误报 | 用白名单豁免（如 `path_constant.xxx` 属性访问） |

---

## 8. 实施计划（总览）

| Phase | 内容 | 估时 |
|---|---|---|
| 1 | 单元测试先行（6.1.1 + 6.1.2 + 6.1.4） | 0.5d |
| 2 | `ImageCache` 加 timeout + 移除 `session.timeout` | 0.1d |
| 3 | `RequestSessionMiddleware` 修 `await rollback()` | 0.1d |
| 4 | favorites / download / tag_cache / config / gallery 路由包 `to_thread` | 0.5d |
| 5 | 调度回调 `_on_folder_trigger` 改 `to_thread` + `with` 上下文 | 0.2d |
| 6 | 下载 worker 整文件 MD5 → `to_thread` | 0.2d |
| 7 | DB 连接池参数调整 | 0.1d |
| 8 | BaseDAO 去掉静默 fallback + 单元测试验证 | 0.2d |
| 9 | 全量跑测试 + 手动集成验证 | 0.3d |

总计约 2 天。

---

## 9. 文档更新

- `docs/middleware.md`：注释更新 `await session.rollback()` 已修
- `docs/dao.md`：增加「DAO 单例 session 在请求外必须用 `with` 上下文」章节
- `docs/design.md` 第 8 节「性能设计」增加 to_thread 规则说明
- `CHANGELOG.md`（如有）记录性能改进

---

## 10. 自审

- [x] Placeholder 扫描：无 TBD/TODO
- [x] 一致性：所有改动都用 `asyncio.to_thread`，无混入 `run_in_executor`（除已有 `gallery.py`）
- [x] Scope：单一可执行 plan，不需拆分
- [x] 模糊点：
  - 「不再用 `run_in_executor`」已明确（统一 `to_thread`）
  - 「连接池调参是否走配置项」已明确：代码常量，不进 config
  - 「`to_thread` 跨线程 + ContextVar」已说明 SQLAlchemy 兼容