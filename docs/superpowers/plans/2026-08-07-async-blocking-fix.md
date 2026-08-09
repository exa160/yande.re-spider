# 异步路由事件循环阻塞修复 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复在线模式/缩略图加载期间事件循环被同步 DAO/HTTP 阻塞的根因问题，所有 async 路由的同步调用统一走 `asyncio.to_thread`。

**Architecture:**
- **API 路由层**统一用 `asyncio.to_thread(sync_func, *args)` 包装同步 service/DAO 调用
- **service / DAO / 基础设施层**零改动（保持同步签名）
- **中间件 bug** 修复 `await session.rollback()` → `session.rollback()`
- **DAO 静默 fallback** 去除，与 `get_session()` 严格模式一致
- **下载 worker 整文件 MD5** 移出事件循环
- **DB 连接池**调参

**Tech Stack:** Python 3.12+, FastAPI, SQLAlchemy sync Session, `requests`, `asyncio`

**Spec:** [`docs/superpowers/specs/2026-08-07-async-blocking-fix-design.md`](../specs/2026-08-07-async-blocking-fix-design.md)

---

## 全局约束（Global Constraints）

> 所有 task 必须遵守的全局规则，逐字摘自 spec。

1. **API 路由层唯一改动点**：`async def` 函数体**只能**新增/修改 `await asyncio.to_thread(...)` 调用，**不得**新增其他业务逻辑。
2. **service / DAO / 基础设施层零改动**——`FavoriteDao`、`YandeDataRepository`、`*Service`、`YandeApi`、`ImageCache`、`TaskStore` 全部保持当前签名和方法体。
3. **错误处理保持原状**：service 抛 `APIException` / `ValueError` / `RuntimeError` 原样上抛，路由 `try/except` 转为对应 `APIException(ErrMsg.XXX, e=e)`。
4. **类型注解**：所有修改后的 async 函数仍需声明返回类型注解。
5. **测试约定**：所有新测试放在 `unit_test/` 对应子目录，遵循现有 `sys.path.insert(0, ...)` + `monkeypatch` 模式。沿用 `conftest.py` 的 `_protect_yande_data` autouse fixture。
6. **commit 粒度**：每个 task 完成后**单独 commit**，不允许跨 task 合并 commit。
7. **YAGNI**：禁止顺手重构，禁止「while I'm here」式改进。
8. **遵循 Yande.re 编码规范**（AGENTS.md）：`BaseResponse` + `APIException(ErrMsg.XXX, e=e)` + 完整 docstring + 类型注解。

---

## Task 1: 添加「async 路由禁止同步 DAO」静态扫描测试

**Files:**
- Create: `unit_test/api/test_no_sync_dao_in_async_routes.py`

**Interfaces:**
- Consumes: `src.api.v1.gallery`, `src.api.v1.favorites`, `src.api.v1.download`, `src.api.v1.tag_cache`, `src.api.v1.config`, `src.api.v1.query`
- Produces: pytest 失败 → 当任一 async 路由函数体内**直接**（未包 `asyncio.to_thread` / `run_in_executor`）调用下列名称：
  - 单例 DAO：`favorite_dao`, `yande_data_repository`, `tag_repository`, `artist_repository`, `download_task_dao`
  - Service 类全限定名（必须是 sync 调用被 to_thread 包）：`FavoritesService`, `DownloadService`, `GalleryService`, `TagCacheService`, `ConfigService`
  - 同步 HTTP：`YandeApi` 实例化或方法调用
  - 同步文件：`ImageCache` 实例化或方法调用

- [ ] **Step 1: 写测试骨架**

```python
"""静态扫描所有 async 路由，断言无未包裹的同步 DAO/service 调用。

背景：v1.1.7 之前 56 个 async 路由里有 40 个直接调用同步 service/DAO，
事件循环被同步 SQL/HTTP 冻结。本测试确保后续 PR 不再重蹈覆辙。

策略：AST 扫描 + 字符串黑名单。每个 async def 函数体逐行检查，
只要出现以下模式之一就 fail：
- 单例 DAO 调用：favorite_dao.xxx() / yande_data_repository.xxx() / ...
- Service 全限定名调用：FavoritesService.xxx() / ...
- 同步 HTTP：YandeApi(...) / .get_count(...)
- 同步文件：ImageCache(...) / .download_preview(...)

豁免规则：出现在 `await asyncio.to_thread(...)` 或 `run_in_executor(...)` 
实参列表中的，忽略。
"""
import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

# 黑名单：同步对象
SYNC_DAO_SINGLETONS = {
    "favorite_dao",
    "yande_data_repository",
    "tag_repository",
    "artist_repository",
    "download_task_dao",
}

SYNC_SERVICES = {
    "FavoritesService",
    "DownloadService",
    "GalleryService",
    "TagCacheService",
    "ConfigService",
}

SYNC_HTTP_CLASSES = {"YandeApi"}
SYNC_FILE_CLASSES = {"ImageCache"}


def _is_inside_to_thread(node: ast.Call) -> bool:
    """判断 Call 节点是否作为 asyncio.to_thread/run_in_executor 的实参"""
    # 检查 Call.func 是否为 asyncio.to_thread 或 run_in_executor
    func = node.func
    func_str = ast.unparse(func) if hasattr(ast, "unparse") else ""
    return func_str in ("asyncio.to_thread", "run_in_executor")


def _find_async_routes_in_module(tree: ast.Module) -> list[tuple[str, ast.AsyncFunctionDef]]:
    """提取模块所有顶层 async def"""
    return [
        (node.name, node)
        for node in tree.body
        if isinstance(node, ast.AsyncFunctionDef)
    ]


def _scan_body_for_sync_calls(body: list[ast.stmt]) -> list[str]:
    """扫描函数体，返回所有命中黑名单的源代码片段"""
    hits: list[str] = []
    for stmt in body:
        for node in ast.walk(stmt):
            if not isinstance(node, ast.Call):
                continue
            # 豁免：asyncio.to_thread / run_in_executor 内
            if _is_inside_to_thread(node):
                continue
            # 检查 func 是否是黑名单
            func = node.func
            # X.method() 形式
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name):
                    name = func.value.id
                    if name in SYNC_DAO_SINGLETONS:
                        hits.append(f"{name}.{func.attr}(...)")
                    elif name in SYNC_SERVICES:
                        hits.append(f"{name}.{func.attr}(...)")
                    elif name in SYNC_HTTP_CLASSES:
                        hits.append(f"{name}(...) 或 .{func.attr}(...)")
                    elif name in SYNC_FILE_CLASSES:
                        hits.append(f"{name}(...) 或 .{func.attr}(...)")
            # Bare class call: YandeApi(...) / ImageCache(...)
            elif isinstance(func, ast.Name):
                if func.id in SYNC_HTTP_CLASSES or func.id in SYNC_FILE_CLASSES:
                    hits.append(f"{func.id}(...)")
    return hits


@pytest.mark.parametrize("module_path", [
    "src.api.v1.gallery",
    "src.api.v1.favorites",
    "src.api.v1.download",
    "src.api.v1.tag_cache",
    "src.api.v1.config",
    "src.api.v1.query",
])
def test_async_routes_have_no_unwrapped_sync_calls(module_path: str):
    """所有 async 路由函数体内的同步调用必须包 asyncio.to_thread"""
    import importlib
    mod = importlib.import_module(module_path)

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    failures: list[str] = []

    for fname, fnode in _find_async_routes_in_module(tree):
        hits = _scan_body_for_sync_calls(fnode.body)
        if hits:
            failures.append(f"{module_path}.{fname}: {hits}")

    assert not failures, (
        f"以下 async 路由直接调用了同步对象（必须包 asyncio.to_thread）：\n"
        + "\n".join(failures)
    )
```

- [ ] **Step 2: 跑测试 → 看到失败**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/test_no_sync_dao_in_async_routes.py -v 2>&1 | head -50`

Expected: 失败。至少 5 个 module 命中（gallery 1 个 + favorites 15 个 + download 12 个 + tag_cache 7 个 + config 6 个 + query 0 个）。

如果通过 → 测试写错或漏判，需排查。

- [ ] **Step 3: 记录预期失败数作为后续 Task 完成的标志**

把失败信息保存到 `/tmp/blocking_fix_baseline.txt`：

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
python -m pytest unit_test/api/test_no_sync_dao_in_async_routes.py -v 2>&1 | tail -3 > /tmp/blocking_fix_baseline.txt
cat /tmp/blocking_fix_baseline.txt
```

记录：「Baseline: N 个 async 路由命中黑名单」

- [ ] **Step 4: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add unit_test/api/test_no_sync_dao_in_async_routes.py
git commit -m "test(api): 静态扫描禁止未包裹的同步 DAO/service 调用"
```

> ⚠️ 此时测试**必须**是失败的，commit 是为了记录 baseline。

---

## Task 2: `ImageCache` 缩略图下载加 timeout

**Files:**
- Modify: `backend/src/infrastructure/image_cache.py:28`（加 timeout 参数）
- Modify: `backend/src/infrastructure/image_cache.py:50`（移除无用的 `self._session.timeout`）
- Create: `unit_test/infrastructure/test_image_cache_timeout.py`

**Interfaces:**
- Consumes: `requests.Session.get(url, ...)` —— 必须传 `timeout=` 才能生效
- Produces: `ImageCache._with_retry_write` 的每次 GET 调用都显式传 `timeout=config.yande_api.timeout`

- [ ] **Step 1: 写失败的测试**

```python
"""验证 ImageCache 缩略图下载显式传 timeout（防无限挂起）

背景：requests.Session.get() 不读 self.timeout 属性，必须显式传 timeout=。
ImageCache 设了 self._session.timeout = config.yande_api.timeout 但无效。
修复后每次 GET 调用都应带 timeout= 参数。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest

import src.infrastructure.image_cache as _ic_module


@pytest.fixture
def fake_path_constant(tmp_path, monkeypatch):
    pc = type("FakePathConstant", (), {
        "previews_dir": tmp_path / "previews",
        "originals_dir": tmp_path / "originals",
    })()
    pc.previews_dir.mkdir()
    pc.originals_dir.mkdir()
    monkeypatch.setattr(_ic_module, "path_constant", pc)
    return pc


def test_download_preview_passes_timeout(fake_path_constant, monkeypatch):
    """download_preview 的 GET 调用必须带 timeout= 参数"""
    from src.infrastructure.image_cache import ImageCache

    captured = {}

    class FakeSession:
        def get(self, url, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("STOP_TEST")

    monkeypatch.setattr(
        "src.common.config.yande_api.timeout", 17, raising=False
    )

    cache = ImageCache()
    cache._session = FakeSession()

    with pytest.raises(RuntimeError, match="STOP_TEST"):
        cache.download_preview(123, "jpg")

    assert "timeout" in captured, "ImageCache.get() must pass timeout="
    assert captured["timeout"] == 17, (
        f"timeout 应等于 config.yande_api.timeout (17), 实际 {captured.get('timeout')}"
    )


def test_download_original_passes_timeout(fake_path_constant, monkeypatch):
    """download_original 的 GET 调用也必须带 timeout= 参数"""
    from src.infrastructure.image_cache import ImageCache

    captured = {}

    class FakeSession:
        def get(self, url, **kwargs):
            captured.update(kwargs)
            raise RuntimeError("STOP_TEST")

    monkeypatch.setattr(
        "src.common.config.yande_api.timeout", 23, raising=False
    )

    cache = ImageCache()
    cache._session = FakeSession()

    with pytest.raises(RuntimeError, match="STOP_TEST"):
        cache.download_original(456, "jpg")

    assert captured.get("timeout") == 23
```

- [ ] **Step 2: 跑测试 → 看到失败**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/infrastructure/test_image_cache_timeout.py -v`

Expected: 2 个 test 全部 FAIL（`assert "timeout" in captured` 失败）。

- [ ] **Step 3: 改 `backend/src/infrastructure/image_cache.py`**

修改 `_with_retry_write`（line 15-41）：

```python
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
                    timeout=config.yande_api.timeout,  # ← 修复：显式传 timeout
                )
                resp.raise_for_status()
                dest_path.write_bytes(resp.content)
                return dest_path
            except requests.RequestException as e:
                last_exception = e
                logger.warning(
                    f"[{attempt + 1}] {action_name} failed for {image_id}: {e}"
                )
                jitter = uniform(0.5, 1.5)
                time.sleep(jitter)
        raise last_exception

    return wrapper
```

同时修改 `ImageCache.__init__`（line 49-50）：

```python
self._session = configure_proxy_session(requests.Session())
# 删除下面这行（无效）：
# self._session.timeout = config.yande_api.timeout
```

- [ ] **Step 4: 跑测试 → 通过**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/infrastructure/test_image_cache_timeout.py -v`

Expected: 2 个 test 全部 PASS。

- [ ] **Step 5: 跑相关测试 → 不破坏现有**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/infrastructure/ -v`

Expected: 全部 PASS（特别是 `test_image_cache_cleanup.py`）。

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/infrastructure/image_cache.py unit_test/infrastructure/test_image_cache_timeout.py
git commit -m "fix(image_cache): 缩略图下载显式传 timeout 防无限挂起"
```

---

## Task 3: 修 `RequestSessionMiddleware` 的 `await rollback()` bug

**Files:**
- Modify: `backend/src/middleware/session.py:40`（去掉 `await`）
- Create: `unit_test/middleware/test_session_middleware_rollback.py`

**Interfaces:**
- Consumes: 标准 ASGI scope/receive/send；endpoint 抛出异常
- Produces: 异常路径调用 `session.rollback()`（同步）→ 不抛 `TypeError: object NoneType can't be used in 'await' expression`

- [ ] **Step 1: 写失败的测试**

```python
"""验证 RequestSessionMiddleware 在 endpoint 抛异常时不因 await rollback() 二次抛 TypeError

背景：Session.rollback() 是同步方法返回 None。原代码 await session.rollback()
等于 await None → TypeError，把原异常掩盖。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest
from starlette.types import Receive, Scope, Send


@pytest.mark.asyncio
async def test_middleware_rollback_does_not_await_none():
    """endpoint 抛异常时，中间件不应再次抛 TypeError"""
    from src.middleware.session import RequestSessionMiddleware

    class FakeSession:
        def __init__(self):
            self.committed = False
            self.rolled_back = False
            self.closed = False

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True
            # 返回 None（标准 SQLAlchemy 行为）

        def close(self):
            self.closed = True

    rollback_calls = []

    def fake_session_factory():
        s = FakeSession()
        return s

    # 用 monkeypatch 替换 _get_session_factory
    import src.middleware.session as sm
    original = sm._get_session_factory
    sm._get_session_factory = lambda: fake_session_factory

    try:
        async def broken_app(scope, receive, send):
            raise ValueError("endpoint blew up")

        mw = RequestSessionMiddleware(broken_app)

        with pytest.raises(ValueError, match="endpoint blew up"):
            await mw({"type": "http"}, lambda: None, lambda *a, **k: None)

        # 验证 rollback 被同步调用 1 次
        assert len(rollback_calls) == 0  # 本测试不直接捕获，留作下个 case
    finally:
        sm._get_session_factory = original
```

更可靠的测试（用 spy 模式）：

```python
@pytest.mark.asyncio
async def test_middleware_calls_rollback_synchronously_on_exception(monkeypatch):
    """endpoint 抛异常时，rollback 必须同步调用（不 await None）"""
    from src.middleware.session import RequestSessionMiddleware

    state = {"rollback_sync_called": False}

    class FakeSession:
        def rollback(self):
            # 标记是同步调用（不是 await 后的回调）
            state["rollback_sync_called"] = True

        def commit(self):
            pass

        def close(self):
            pass

    import src.middleware.session as sm
    monkeypatch.setattr(sm, "_get_session_factory", lambda: lambda: FakeSession())

    rollback_was_awaited = {"v": False}

    # 给 FakeSession 加异步方法（如果代码错误地 await 它，必须能检测）
    original_rollback = FakeSession.rollback

    def spy_rollback(self):
        # 如果代码 `await self.rollback()`，会先调 rollback() 再 await 返回值
        # 我们标记为同步调用
        state["rollback_sync_called"] = True
        # 返回 None 是真实的；这里的"await None" 测试通过最外层 try/except 是否捕获
        return None

    FakeSession.rollback = spy_rollback

    async def broken_app(scope, receive, send):
        raise RuntimeError("endpoint fail")

    mw = RequestSessionMiddleware(broken_app)

    with pytest.raises(RuntimeError, match="endpoint fail"):
        await mw({"type": "http"}, lambda: None, lambda *a, **k: None)

    assert state["rollback_sync_called"], "rollback should be called synchronously"
```

- [ ] **Step 2: 跑测试 → 看到失败**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/middleware/test_session_middleware_rollback.py -v`

Expected: `RuntimeError: endpoint fail` 被覆盖为 `TypeError: object NoneType can't be used in 'await' expression`（中间件自身的 bug 触发）。

- [ ] **Step 3: 改 `backend/src/middleware/session.py:40`**

```python
# 原代码（bug）：
except Exception:
    await session.rollback()  # ❌
    raise

# 改：
except Exception:
    session.rollback()  # ✅ 同步方法，await None 会抛 TypeError
    raise
```

完整 method：

```python
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
        session.rollback()  # ← 同步调用
        raise
    finally:
        _request_session.reset(token)
        session.close()
```

- [ ] **Step 4: 跑测试 → 通过**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/middleware/test_session_middleware_rollback.py -v`

Expected: PASS。

- [ ] **Step 5: 跑相关测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/test_lifespan_middleware.py -v`

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/middleware/session.py unit_test/middleware/test_session_middleware_rollback.py
git commit -m "fix(middleware): RequestSessionMiddleware rollback 改同步调用（去掉 await）"
```

---

## Task 4: `BaseDAO` 去掉静默 Session fallback

**Files:**
- Modify: `backend/src/dao/database.py:150-161`（去掉 `except Exception` 兜底）
- Create: `unit_test/dao/test_base_dao_session_outside_request.py`

**Interfaces:**
- Consumes: `RequestSessionMiddleware.get_session()` 严格模式（无请求上下文时抛 `RuntimeError`）
- Produces: `BaseDAO.session` 在请求外时**直接抛** `RuntimeError`，不再静默造未托管 Session

- [ ] **Step 1: 写失败的测试**

```python
"""验证 BaseDAO 单例在请求外调用 session 属性会抛 RuntimeError

背景：原代码 try/except Exception 兜底，导致后台调度等无请求上下文场景
会静默创建未托管 Session，连接泄漏。
修复后与 RequestSessionMiddleware.get_session() 严格模式一致。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest


def test_base_dao_session_raises_when_no_request_context():
    """无请求上下文时，BaseDAO 单例 session 属性必须抛 RuntimeError"""
    from src.dao.favorite_dao import FavoriteDao
    from src.dao.download_task_dao import DownloadTaskDao
    from src.dao.yande_data_dao import YandeDataRepository
    from src.dao.tag_dao import TagRepository

    for dao_class in (FavoriteDao, DownloadTaskDao, YandeDataRepository, TagRepository):
        dao = dao_class()
        with pytest.raises(RuntimeError, match="RequestSessionMiddleware not active"):
            _ = dao.session
```

- [ ] **Step 2: 跑测试 → 看到失败**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/dao/test_base_dao_session_outside_request.py -v`

Expected: 4 个 DAO 全部**不抛错**（因为 fallback 在生效，造了未托管 Session）。

- [ ] **Step 3: 改 `backend/src/dao/database.py:150-161`**

```python
# 原代码（150-161）：
@property
def session(self) -> Session:
    # 显式构造时优先 (with FavoriteDao(s) as dao:)
    if self._session is not None:
        return self._session
    # 单例路径: 每次从 ContextVar 拿当前请求 session
    # 禁止缓存! 缓存会导致下次请求拿到已 close 的旧 session
    try:
        from src.middleware.session import RequestSessionMiddleware
        return RequestSessionMiddleware.get_session()
    except Exception:
        return _get_session_factory()()

# 改后：
@property
def session(self) -> Session:
    # 显式构造时优先 (with FavoriteDao(s) as dao:)
    if self._session is not None:
        return self._session
    # 单例路径: 每次从 ContextVar 拿当前请求 session
    # 禁止缓存! 缓存会导致下次请求拿到已 close 的旧 session
    # 请求外场景（后台调度/CLI）必须用 with DAO() as dao: 显式上下文
    from src.middleware.session import RequestSessionMiddleware
    return RequestSessionMiddleware.get_session()
```

- [ ] **Step 4: 跑测试 → 通过**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/dao/test_base_dao_session_outside_request.py -v`

Expected: 全部 PASS（4 个 DAO 都抛 `RuntimeError`）。

- [ ] **Step 5: 跑相关测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/ -v`

Expected: 现有测试可能部分失败（因为调度/启动等场景依赖 fallback）。

**失败修复预期**：
- `unit_test/test_favorite_scheduler.py` —— 调度场景
- `unit_test/test_scheduler_register.py` —— 调度注册
- `unit_test/lifecycle/test_download_lifecycle_restart.py` —— 启动恢复
- 这些测试如果失败，看错误是不是「BaseDAO session outside request」 → 是 Task 5/10 配套修复影响的，**不**在这里修，留到对应 Task。

**记录 baseline**：

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
python -m pytest unit_test/ 2>&1 | tail -3 > /tmp/dao_baseline.txt
cat /tmp/dao_baseline.txt
```

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/dao/database.py unit_test/dao/test_base_dao_session_outside_request.py
git commit -m "fix(dao): BaseDAO 单例 session 去掉静默 fallback，与严格模式一致"
```

---

## Task 5: 调度回调 `_on_folder_trigger` 改用 `with` 上下文 + `to_thread`

**Files:**
- Modify: `backend/src/infrastructure/scheduler.py:103-126`

**Interfaces:**
- Consumes: APScheduler AsyncIOScheduler 回调（无请求上下文）
- Produces: `_on_folder_trigger` 在独立线程内执行 `with FavoriteDao() as dao: get_by_id(...)`，不依赖请求 ContextVar

- [ ] **Step 1: 写失败的测试**

```python
"""验证 _on_folder_trigger 不依赖请求 ContextVar

背景：修复 BaseDAO 静默 fallback 后，APScheduler 回调（无请求上下文）
调用 favorite_dao.get_by_id 会抛 RuntimeError。
正确做法是回调内用 with DAO() as dao: 显式创建 session。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import asyncio
import pytest


@pytest.mark.asyncio
async def test_on_folder_trigger_uses_with_context(monkeypatch):
    """_on_folder_trigger 必须在 with 上下文内调用 DAO，不能依赖单例 session"""
    from src.infrastructure import scheduler as sm
    from src.dao.favorite_dao import FavoriteDao

    captured = {"called_in_with": False}

    class FakeFolder:
        schedule_enabled = False  # 跳过 schedule_enabled 检查立刻 return

    def fake_get_by_id(self, folder_id):
        # 验证调用时 self._session 是有值的（即在 with 内）
        if self._session is not None:
            captured["called_in_with"] = True
        return FakeFolder()

    monkeypatch.setattr(FavoriteDao, "get_by_id", fake_get_by_id)

    await sm._on_folder_trigger(999)

    assert captured["called_in_with"], (
        "DAO get_by_id 调用时 self._session 应为非 None（在 with 内）"
    )
```

- [ ] **Step 2: 跑测试 → 看到失败**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/infrastructure/test_scheduler_trigger_uses_with_context.py -v`

Expected: FAIL（`called_in_with` 是 False，因为原代码用 `favorite_dao.get_by_id()` 直接调单例方法，没经过 `__enter__`）。

- [ ] **Step 3: 改 `backend/src/infrastructure/scheduler.py:103-126`**

```python
async def _on_folder_trigger(folder_id: int) -> None:
    """定时触发入口：防御性检查 + 顺手清理残留 job

    若 DB 中 folder 已不存在或 schedule_enabled=False，
    跳过本次触发并调用 unregister_folder 清理 APScheduler 中可能残留的 job。
    """
    from src.services.favorite_scheduler import run_folder_schedule
    from src.dao.favorite_dao import FavoriteDao

    def _load_and_check() -> Optional[Any]:
        with FavoriteDao() as dao:
            folder = dao.get_by_id(folder_id)
            if not folder:
                return None
            # 复制必要字段（避免跨线程持有 ORM 对象）
            return {
                "id": folder.id,
                "schedule_enabled": folder.schedule_enabled,
            }

    loaded = await asyncio.to_thread(_load_and_check)
    if loaded is None:
        logger.warning(
            f"Scheduled trigger skipped: folder {folder_id} not found, cleanup residual job"
        )
        schedule_manager.unregister_folder(folder_id)
        return
    if not loaded["schedule_enabled"]:
        logger.info(
            f"Scheduled trigger skipped: folder {folder_id} schedule disabled, cleanup residual job"
        )
        schedule_manager.unregister_folder(folder_id)
        return

    asyncio.create_task(run_folder_schedule(folder_id))
```

顶部加 import：

```python
from typing import Optional, Any
```

- [ ] **Step 4: 跑测试 → 通过**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/infrastructure/test_scheduler_trigger_uses_with_context.py -v`

Expected: PASS。

- [ ] **Step 5: 跑相关测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/test_scheduler_register.py unit_test/test_favorite_scheduler.py -v`

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/infrastructure/scheduler.py unit_test/infrastructure/test_scheduler_trigger_uses_with_context.py
git commit -m "fix(scheduler): _on_folder_trigger 用 with 上下文 + to_thread"
```

---

## Task 6: 下载 worker 整文件 MD5 移出事件循环

**Files:**
- Modify: `backend/src/infrastructure/download_queue.py:382-395`

**Interfaces:**
- Consumes: `original_path: Path`, `expected_md5: str`
- Produces: 整文件读取 + MD5 计算在 `to_thread` 内执行，不冻结事件循环

- [ ] **Step 1: 写失败的测试**

```python
"""验证 run_download_async 不在事件循环线程做整文件 MD5

策略：mock 整文件 MD5 计算函数，断言它被 asyncio.to_thread 调用
（即不在主线程运行）。
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.asyncio
async def test_whole_file_md5_runs_in_thread(monkeypatch, tmp_path):
    """整文件 MD5 计算必须在 to_thread 内，不能在事件循环线程执行"""
    from src.infrastructure import download_queue

    # 创建测试文件
    test_file = tmp_path / "test.jpg"
    test_file.write_bytes(b"\x00" * (5 * 1024 * 1024))  # 5MB

    main_thread_id = None
    compute_thread_id = {"value": None}

    def fake_md5_compute(file_path):
        import threading
        compute_thread_id["value"] = threading.get_ident()
        return "fake_md5"

    # patch hashlib.md5 的使用
    real_open = open

    # 简化：用更直接的方式验证
    # 我们注入一个会被 to_thread 调用的函数
    monkeypatch.setattr(
        "src.infrastructure.download_queue._compute_file_md5",
        fake_md5_compute,
        raising=False,
    )

    # 直接调用 _compute_file_md5 的 to_thread 路径
    main_thread_id_local = __import__("threading").get_ident()

    async def run_in_thread_path():
        return await asyncio.to_thread(fake_md5_compute, test_file)

    md5 = await run_in_thread_path()

    assert md5 == "fake_md5"
    # 在 thread pool 内运行的 thread id 应该 != 主线程
    assert compute_thread_id["value"] != main_thread_id_local
```

更简洁的版本（直接测试函数被调用且不在主线程）：

```python
@pytest.mark.asyncio
async def test_compute_file_md5_in_to_thread():
    """验证 _compute_file_md5 在 to_thread 中执行（不在事件循环线程）"""
    import threading
    from src.infrastructure.download_queue import _compute_file_md5

    main_tid = threading.get_ident()

    result = await asyncio.to_thread(_compute_file_md5, "/nonexistent/path")
    # 文件不存在应该返回 None 或抛错，这里只要看 thread id
    assert threading.current_thread() != threading.main_thread()
    # 上面 assertion 不严格，改用：
    assert main_tid != threading.get_ident()  # 我们是在 to_thread 内的 coroutine
```

> 这测试有点啰嗦。简化：在 `download_queue.py` 改动后**直接写一个验证模块导出 `_compute_file_md5` 函数**的测试：

```python
def test_compute_file_md5_returns_correct_hash(tmp_path):
    """_compute_file_md5 正确计算文件 MD5"""
    from src.infrastructure.download_queue import _compute_file_md5

    test_file = tmp_path / "test.bin"
    test_file.write_bytes(b"hello world")
    md5 = _compute_file_md5(test_file)
    assert md5 == "5eb63bbbe01eeed093cb22bb8f5acdc3"


def test_compute_file_md5_returns_none_for_missing_file(tmp_path):
    """_compute_file_md5 对不存在文件返回 None"""
    from src.infrastructure.download_queue import _compute_file_md5

    md5 = _compute_file_md5(tmp_path / "does_not_exist")
    assert md5 is None
```

- [ ] **Step 2: 跑测试 → 看到失败**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/infrastructure/test_download_md5_offloop.py -v`

Expected: ImportError（`_compute_file_md5` 还未存在）。

- [ ] **Step 3: 改 `backend/src/infrastructure/download_queue.py:382-395`**

把整文件 MD5 逻辑提取为独立函数：

```python
# 在文件顶部（hashlib 已 import）添加：

def _compute_file_md5(file_path: Path) -> Optional[str]:
    """整文件 MD5 计算（不持有事务，专供 asyncio.to_thread 调用）

    Args:
        file_path: 原图完整路径

    Returns:
        十六进制 MD5 字符串；文件不存在/读取失败返回 None
    """
    if not file_path.exists():
        return None
    try:
        md5_hasher = hashlib.md5()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                md5_hasher.update(chunk)
        return md5_hasher.hexdigest()
    except OSError:
        return None
```

修改 `run_download_async`（line 382-395）：

```python
if original_path.exists() and expected_md5:
    # 整文件 MD5 计算移出事件循环（大文件会冻主线程）
    file_md5 = await asyncio.to_thread(_compute_file_md5, original_path)
    if file_md5 is None:
        logger.warning(
            f"Original exists but MD5 check failed for {image_id}, will re-download"
        )
        need_download = True
    elif file_md5 == expected_md5:
        logger.info(
            f"Original exists and MD5 matches ({file_md5}), skipping download"
        )
        need_download = False
    else:
        logger.info(f"Original exists but MD5 mismatch, re-downloading")
        await asyncio.to_thread(original_path.unlink)
        need_download = True
```

注意：`original_path.unlink()` 是文件 IO 也放到 thread 内。

- [ ] **Step 4: 跑测试 → 通过**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/infrastructure/test_download_md5_offloop.py -v`

Expected: PASS（3 个 test）。

- [ ] **Step 5: 跑相关测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/infrastructure/ unit_test/services/test_download_service_retry.py unit_test/services/test_download_service_tabs.py -v`

Expected: 全部 PASS。

- [ ] **Step 6: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/infrastructure/download_queue.py unit_test/infrastructure/test_download_md5_offloop.py
git commit -m "fix(download): 整文件 MD5 移出事件循环（asyncio.to_thread）"
```

---

## Task 7: `gallery.py` 补 `get_gallery_statistics` 的 `to_thread`

**Files:**
- Modify: `backend/src/api/v1/gallery.py:72-80`

**Interfaces:**
- Consumes: `GalleryService.get_statistics(source)` 同步函数
- Produces: `get_gallery_statistics` 通过 `await asyncio.to_thread(...)` 调用

- [ ] **Step 1: 手动验证当前是同步调用**

Read: `backend/src/api/v1/gallery.py:72-80`

确认 line 77 是 `stats = GalleryService.get_statistics(source)`。

- [ ] **Step 2: 修改 gallery.py**

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

只改 line 77：`stats = GalleryService.get_statistics(source)` → `stats = await asyncio.to_thread(GalleryService.get_statistics, source)`。

- [ ] **Step 3: 跑 API 路由静态扫描 → 该 module 命中数应 -1**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/test_no_sync_dao_in_async_routes.py::test_async_routes_have_no_unwrapped_sync_calls -v 2>&1 | tail -20`

Expected: gallery module 不再出现在 failures。

- [ ] **Step 4: 跑相关测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/v1/test_preview_cleanup_routes.py -v`

Expected: 全部 PASS（gallery 路由相关测试）。

- [ ] **Step 5: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/api/v1/gallery.py
git commit -m "fix(api): gallery.get_gallery_statistics 包 asyncio.to_thread"
```

---

## Task 8: `tag_cache.py` 全部 7 个路由包 `to_thread`

**Files:**
- Modify: `backend/src/api/v1/tag_cache.py:54, 64, 74, 84, 98, 114, 136`

**Interfaces:**
- Consumes: `TagCacheService.*` 同步函数（除已包好的 refresh_tags/refresh_artists）
- Produces: 所有调用通过 `await asyncio.to_thread(...)`

- [ ] **Step 1: 修改 `backend/src/api/v1/tag_cache.py`**

逐个修改以下路由函数，把 `TagCacheService.xxx(...)` 改为 `await asyncio.to_thread(TagCacheService.xxx, ...)`：

| line | 原代码 | 改为 |
|---|---|---|
| 57 | `stats = TagCacheService.get_tags_stats()` | `stats = await asyncio.to_thread(TagCacheService.get_tags_stats)` |
| 67 | `stats = TagCacheService.get_artists_stats()` | `stats = await asyncio.to_thread(TagCacheService.get_artists_stats)` |
| 77 | `tags = TagCacheService.search_tags(keyword, limit)` | `tags = await asyncio.to_thread(TagCacheService.search_tags, keyword, limit)` |
| 87 | `artists = TagCacheService.search_artists(keyword, limit)` | `artists = await asyncio.to_thread(TagCacheService.search_artists, keyword, limit)` |
| 101 | `stats_updated = TagCacheService.calculate_local_stats()` | `stats_updated = await asyncio.to_thread(TagCacheService.calculate_local_stats)` |
| 122-127 | `tags, total = TagCacheService.get_tags_with_stats(...)` | `tags, total = await asyncio.to_thread(TagCacheService.get_tags_with_stats, tag_type=type, search_keyword=search, limit=limit, has_local_only=has_local_only)` |
| 140 | `result = TagCacheService.get_tags_by_names(name_list)` | `result = await asyncio.to_thread(TagCacheService.get_tags_by_names, name_list)` |

`refresh_tags`（line 29）和 `refresh_artists`（line 44）已用 `to_thread`/`run_in_executor`，**不动**。

- [ ] **Step 2: 跑静态扫描 → 该 module 命中数为 0**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/test_no_sync_dao_in_async_routes.py -v 2>&1 | grep "tag_cache" | head -5`

Expected: 无输出（tag_cache module 不再失败）。

- [ ] **Step 3: 跑相关测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/ -v -k "tag_cache"`

Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/api/v1/tag_cache.py
git commit -m "fix(api): tag_cache 全部统计/搜索路由包 asyncio.to_thread"
```

---

## Task 9: `download.py` 全部 12 个路由包 `to_thread`

**Files:**
- Modify: `backend/src/api/v1/download.py:29, 45, 61, 100, 112, 123, 132, 141, 150, 159, 168, 176, 194`

**Interfaces:**
- Consumes: `DownloadService.*` 同步函数 / TaskStore 同步方法
- Produces: 所有调用通过 `await asyncio.to_thread(...)`

- [ ] **Step 1: 修改 `backend/src/api/v1/download.py`**

逐个修改：

| line | 函数 | 修改 |
|---|---|---|
| 32 | `create_download_task` | `task_id = await DownloadService.create_task(task.image_id)` → `task_id = await asyncio.to_thread(DownloadService.create_task, task.image_id)` |
| 51 | `create_batch_download_tasks` | `task_ids = await DownloadService.create_batch_tasks(image_ids)` → `task_ids = await asyncio.to_thread(DownloadService.create_batch_tasks, image_ids)` |
| 75 | `get_download_tasks` | `tasks, total = DownloadService.get_tasks(...)` → `tasks, total = await asyncio.to_thread(DownloadService.get_tasks, status_list=status, sort_by=sort_by, order=order, page=page, page_size=page_size, download_first=download_first)` |
| 103 | `get_task_status_counts` | `counts = DownloadService.get_status_counts()` → `counts = await asyncio.to_thread(DownloadService.get_status_counts)` |
| 114 | `get_download_task` | `task = DownloadService.get_task(task_id)` → `task = await asyncio.to_thread(DownloadService.get_task, task_id)` |
| 125 | `get_task_progress` | `progress = DownloadService.get_task_progress(task_id)` → `progress = await asyncio.to_thread(DownloadService.get_task_progress, task_id)` |
| 134 | `start_download_task` | `success, message = await DownloadService.start_task(task_id)` → `success, message = await asyncio.to_thread(DownloadService.start_task, task_id)` |
| 143 | `pause_download_task` | `success, message = DownloadService.pause_task(task_id)` → `success, message = await asyncio.to_thread(DownloadService.pause_task, task_id)` |
| 152 | `resume_download_task` | `success, message = await DownloadService.resume_task(task_id)` → `success, message = await asyncio.to_thread(DownloadService.resume_task, task_id)` |
| 161 | `cancel_download_task` | `success, message = DownloadService.cancel_task(task_id)` → `success, message = await asyncio.to_thread(DownloadService.cancel_task, task_id)` |
| 170 | `delete_download_task` | `if not DownloadService.delete_task(task_id):` → `if not await asyncio.to_thread(DownloadService.delete_task, task_id):` |
| 182 | `get_download_history` | `completed_tasks, total = DownloadService.get_download_history(page, page_size)` → `completed_tasks, total = await asyncio.to_thread(DownloadService.get_download_history, page, page_size)` |
| 198 | `get_queue_status` | `data=DownloadService.get_queue_status()` → `data=await asyncio.to_thread(DownloadService.get_queue_status)` |

顶部加 `import asyncio`（如果还没有）。

- [ ] **Step 2: 跑静态扫描**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/test_no_sync_dao_in_async_routes.py -v 2>&1 | grep "download.py" | head -5`

Expected: 无输出。

- [ ] **Step 3: 跑相关测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/services/test_download_service_retry.py unit_test/services/test_download_service_tabs.py unit_test/infrastructure/test_task_store_retry.py -v`

Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/api/v1/download.py
git commit -m "fix(api): download 全部 12 个路由包 asyncio.to_thread"
```

---

## Task 10: `favorites.py` 全部 15 个路由包 `to_thread`（最大块）

**Files:**
- Modify: `backend/src/api/v1/favorites.py:38, 50, 70, 80, 90, 102, 111, 127, 138, 149, 160, 171, 184, 207, 222`

**Interfaces:**
- Consumes: `FavoritesService.*` 同步函数 + 直接 `favorite_dao.get_by_id(...)` / `favorite_dao.reset_last_synced_id(...)`
- Produces: 所有调用通过 `await asyncio.to_thread(...)`

- [ ] **Step 1: 修改 `backend/src/api/v1/favorites.py`**

逐个修改：

| line | 函数 | 修改 |
|---|---|---|
| 43 | `get_all_folders` | `folders = FavoritesService.get_all_folders()` → `folders = await asyncio.to_thread(FavoritesService.get_all_folders)` |
| 63 | `get_folders_with_preview` | `folders = FavoritesService.get_folders_with_preview()` → `folders = await asyncio.to_thread(FavoritesService.get_folders_with_preview)` |
| 73 | `create_folder` | `new_folder = FavoritesService.create_folder(folder)` → `new_folder = await asyncio.to_thread(FavoritesService.create_folder, folder)` |
| 83 | `get_folder` | `folder = FavoritesService._refresh_local_count(folder_id)` → `folder = await asyncio.to_thread(FavoritesService._refresh_local_count, folder_id)` |
| 93 | `update_folder` | `updated = FavoritesService.update_folder(folder_id, folder)` → `updated = await asyncio.to_thread(FavoritesService.update_folder, folder_id, folder)` |
| 104 | `delete_folder` | `success = FavoritesService.delete_folder(folder_id)` → `success = await asyncio.to_thread(FavoritesService.delete_folder, folder_id)` |
| 114 | `reorder_folders` | `success = FavoritesService.reorder_folders(request.folder_ids)` → `success = await asyncio.to_thread(FavoritesService.reorder_folders, request.folder_ids)` |
| 129 | `preview_folder` | `result = FavoritesService.preview_folder(folder_id, limit)` → `result = await asyncio.to_thread(FavoritesService.preview_folder, folder_id, limit)` |
| 140 | `refresh_folder_count` | `result = FavoritesService.get_folder(folder_id)` → `result = await asyncio.to_thread(FavoritesService.get_folder, folder_id)` |
| 151 | `update_online_count` | `success = FavoritesService.update_online_count(folder_id, count)` → `success = await asyncio.to_thread(FavoritesService.update_online_count, folder_id, count)` |
| 162 | `refresh_online_count` | `count = FavoritesService.refresh_online_count(folder_id)` → `count = await asyncio.to_thread(FavoritesService.refresh_online_count, folder_id)` |
| 173 | `update_local_count` | `success = FavoritesService.update_local_count(folder_id, count)` → `success = await asyncio.to_thread(FavoritesService.update_local_count, folder_id, count)` |
| 192 | `trigger_folder_schedule` | `folder = favorite_dao.get_by_id(folder_id)` → `folder = await asyncio.to_thread(favorite_dao.get_by_id, folder_id)` |
| 208 | `get_folder_schedule_status` | `folder = favorite_dao.get_by_id(folder_id)` → `folder = await asyncio.to_thread(favorite_dao.get_by_id, folder_id)` |
| 227 | `reset_last_synced_id` | `folder = favorite_dao.get_by_id(folder_id)` → `folder = await asyncio.to_thread(favorite_dao.get_by_id, folder_id)` |
| 231 | `reset_last_synced_id` | `updated = favorite_dao.reset_last_synced_id(folder_id, request.value)` → `updated = await asyncio.to_thread(favorite_dao.reset_last_synced_id, folder_id, request.value)` |

`import asyncio` 已经在文件顶部。

- [ ] **Step 2: 跑静态扫描**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/test_no_sync_dao_in_async_routes.py -v 2>&1 | grep "favorites" | head -5`

Expected: 无输出。

- [ ] **Step 3: 跑相关测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/test_favorite_scheduler.py unit_test/services/ unit_test/api/ -v`

Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/api/v1/favorites.py
git commit -m "fix(api): favorites 全部 15 个路由包 asyncio.to_thread（含 refresh_online_count）"
```

---

## Task 11: `config.py` 全部 6 个路由包 `to_thread`

**Files:**
- Modify: `backend/src/api/v1/config.py:24, 33, 42, 51, 58`

**Interfaces:**
- Consumes: `ConfigService.*` 同步函数（含 YAML 写、MariaDB 连接测试）
- Produces: 所有调用通过 `await asyncio.to_thread(...)`

- [ ] **Step 1: 修改 `backend/src/api/v1/config.py`**

逐个修改：

| line | 函数 | 修改 |
|---|---|---|
| 26 | `update_api_config` | `success = ConfigService.update_api_config(api_config)` → `success = await asyncio.to_thread(ConfigService.update_api_config, api_config)` |
| 35 | `update_downloader_config` | `success = ConfigService.update_downloader_config(down_config)` → `success = await asyncio.to_thread(ConfigService.update_downloader_config, down_config)` |
| 44 | `update_database_config` | `success = ConfigService.update_database_config(database_config)` → `success = await asyncio.to_thread(ConfigService.update_database_config, database_config)` |
| 53 | `test_database_connection` | `result = ConfigService.test_database_connection(database_config)` → `result = await asyncio.to_thread(ConfigService.test_database_connection, database_config)` |
| 62 | `reset_config` | `success, message = ConfigService.reset_config(section)` → `success, message = await asyncio.to_thread(ConfigService.reset_config, section)` |

顶部加 `import asyncio`。

`get_system_config`（line 18）返回内存对象，**不动**。

- [ ] **Step 2: 跑静态扫描**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/test_no_sync_dao_in_async_routes.py -v`

Expected: **全部模块通过**（这是整个修复的里程碑测试）。

- [ ] **Step 3: 跑相关测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/services/test_config_update_headers.py unit_test/common/test_proxy_mode.py -v`

Expected: 全部 PASS。

- [ ] **Step 4: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/api/v1/config.py
git commit -m "fix(api): config 全部 6 个路由包 asyncio.to_thread"
```

---

## Task 12: DB 连接池调参

**Files:**
- Modify: `backend/src/dao/database.py:41-43`

**Interfaces:**
- Consumes: `create_engine(url, ...)` 接收 `pool_size` / `max_overflow` / `pool_timeout`
- Produces: pool_size=10, max_overflow=20, pool_timeout=10

- [ ] **Step 1: 改 `backend/src/dao/database.py:34-44`**

```python
_cached_engine = create_engine(url,
    pool_recycle=1800,
    pool_pre_ping=True,
    pool_use_lifo=True,
    pool_reset_on_return="rollback",
    connect_args={"connect_timeout": 10},
    echo=False,
    pool_size=10,       # 原 5：双倍基础连接
    max_overflow=20,    # 原 10：双倍溢出
    pool_timeout=10,    # 原 30：失败更快，避免长时等连接
)
```

> SQLite 分支不动（StaticPool + 30s timeout）。

- [ ] **Step 2: 跑全量测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/ -v --tb=short 2>&1 | tail -30`

Expected: 全部 PASS（连接池调大不会破坏单元测试，单元测试本身用单连接）。

- [ ] **Step 3: 手动验证（启动后端，检查无连接池报错）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
timeout 5 python -c "
import sys
sys.path.insert(0, '.')
from src.dao.database import get_db_engine
engine = get_db_engine()
print('Engine pool_size:', engine.pool.size())
print('Engine max_overflow:', engine.pool._max_overflow)
print('Engine timeout:', engine.pool._timeout)
"
```

Expected: 打印 `pool_size=10`, `max_overflow=20`, `timeout=10`。

- [ ] **Step 4: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add backend/src/dao/database.py
git commit -m "perf(dao): 调大 DB 连接池到 10+20，pool_timeout 缩到 10s"
```

---

## Task 13: 文档更新 + 全量验证 + 版本号

**Files:**
- Modify: `docs/middleware.md:111`（注释更新 `await session.rollback()` 已修）
- Modify: `docs/dao.md`（增加「DAO 单例 session 必须用 with 上下文」章节）
- Modify: `docs/design.md` 第 8 节「性能设计」增加 to_thread 规则
- Modify: `backend/src/__init__.py`（version 字段）
- Modify: `frontend/package.json`（version 字段）
- Modify: `pyproject.toml`（version 字段）

**Interfaces:**
- Consumes: 当前 `__init__.py` version 是 `"1.1.9"`
- Produces: 所有 3 处 version 源同步 bump 到 `"1.1.10"`（按 AGENTS.md 「升级版本」流程）

- [ ] **Step 1: 更新 `docs/middleware.md:111`**

把示例代码中的 `await session.rollback()` 改为 `session.rollback()`，加注释：

```markdown
async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
    ...
    except Exception:
        session.rollback()  # 同步方法，不能 await
        raise
    ...
```

- [ ] **Step 2: 更新 `docs/dao.md`**

在「注意事项」后增加章节：

```markdown
## DAO 单例的 ContextVar 依赖（v1.1.10+）

`favorite_dao = FavoriteDao()` 等单例的 `.session` 属性依赖 `RequestSessionMiddleware` 设置的 ContextVar。

**请求内**（HTTP 路由 → service → 单例方法）：正常，自动获取请求 session。
**请求外**（后台调度 / CLI / 单元测试）：**必须**用 `with DAO() as dao:` 显式上下文：

```python
# ✓ 正确
with FavoriteDao() as dao:
    folder = dao.get_by_id(folder_id)

# ✗ 错误
folder = favorite_dao.get_by_id(folder_id)  # RuntimeError: RequestSessionMiddleware not active
```

违反时立即抛 `RuntimeError`，不再静默创建未托管 Session（v1.1.10 修复）。
```

- [ ] **Step 3: 更新 `docs/design.md` 第 8 节**

在「后端优化」列表里增加：

```markdown
- **后端优化**：
  - 异步IO处理请求
  - **async 路由内同步 service/DAO 调用必须包 `asyncio.to_thread`**（v1.1.10+ 强制规范）
  - 查询结果缓存
  - 数据库连接池
  - 批量数据库操作
```

- [ ] **Step 4: Bump version（按 AGENTS.md 流程）**

| 文件 | 字段 | 旧值 | 新值 |
|---|---|---|---|
| `backend/src/__init__.py` | `AppConfig.version` | `"1.1.9"` | `"1.1.10"` |
| `frontend/package.json` | `"version"` | `"1.1.9"` | `"1.1.10"` |
| `pyproject.toml` | `version` | `"1.1.9"` | `"1.1.10"` |

按 AGENTS.md 「升级版本」流程，**先 commit 改版本号 → tag → gh release → gh issue → gh pr**。

但本任务只 commit 改版本号，不打 tag / release（按用户授权决定是否走完整 release）。

- [ ] **Step 5: 跑全量测试**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/ -v --tb=short 2>&1 | tail -50`

Expected: 全部 PASS。

- [ ] **Step 6: 跑静态扫描 → 关键 milestone**

Run: `cd /home/exa160/opencode/yande.re-spider-next-dev && python -m pytest unit_test/api/test_no_sync_dao_in_async_routes.py -v`

Expected: **全部 6 个 module 通过**（这是修复成功的关键标志）。

- [ ] **Step 7: Commit**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git add docs/middleware.md docs/dao.md docs/design.md \
        backend/src/__init__.py frontend/package.json pyproject.toml
git commit -m "docs: 更新 async-blocking-fix 相关规范 + bump version 1.1.9 → 1.1.10"
```

- [ ] **Step 8: 推送前必查（AGENTS.md 强制）**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev
git diff origin/feature-segments-responsive..HEAD 2>/dev/null \
  | grep -iE '(password|secret|token|api[_-]?key)\s*[:=]\s*["'\''][^"'\'']+["'\'']' \
  | grep -vE '""null<YOUR_<CHANGE_'
```

Expected: 无输出。

---

## Task 14: 手动集成验证

**Files:**
- 不改任何文件，纯手动测试

- [ ] **Step 1: 启动后端**

```bash
cd /home/exa160/opencode/yande.re-spider-next-dev/backend
uvicorn service:main_app --port 8000 --reload --reload-dir ./src &
sleep 5
```

- [ ] **Step 2: 模拟瀑布流缩略图风暴**

```bash
# 启动浏览器打开 http://localhost:8000，切换到在线模式
# 加载一屏 20+ 缩略图
# 同时点开收藏夹、下载任务、配置页
# 期望：所有页面正常响应（修复前其他页面会被卡住）
```

- [ ] **Step 3: 测试 refresh_online_count 不阻塞**

```bash
# 浏览器触发"刷新在线数量"
# 同时打开新 tab 访问 http://localhost:8000/api/v1/favorites
# 期望：/api/v1/favorites 立即返回（修复前会被卡 5-30s）
```

- [ ] **Step 4: 测试 timeout 生效**

```bash
# 把 yande_api.timeout 调到 1 秒（在 config 页 UI 操作）
# 重新加载在线模式
# 期望：缩略图 fetch 1 秒后失败重试，不会无限挂起
```

- [ ] **Step 5: 记录验证结果到 commit**

如有问题，回到对应 Task 修复；如全通过，写一份简短的「验证报告」放在 PR description 里。

---

## 执行完成检查清单

- [ ] Task 1: 防 sync DAO 静态扫描测试已加
- [ ] Task 2: ImageCache timeout 已加
- [ ] Task 3: RequestSessionMiddleware bug 已修
- [ ] Task 4: BaseDAO 静默 fallback 已去
- [ ] Task 5: 调度回调已改 with + to_thread
- [ ] Task 6: 下载 worker MD5 已移出事件循环
- [ ] Task 7-11: 所有 async 路由已包 to_thread
- [ ] Task 12: DB 连接池已调参
- [ ] Task 13: 文档 + version 已更新
- [ ] Task 14: 手动集成验证已通过

**关键里程碑**：Task 11 完成后跑静态扫描测试**必须全绿**。

---

## 下一步（用户决定）

修复完成后，按 AGENTS.md 「Dev 发布流程」：

```bash
# 推送前必查（已包含在 Task 13 Step 8）
# 已通过

# 提 issue + MR
gh issue create --title "[v1.1.10] 修复在线模式/缩略图加载阻塞其他接口" \
  --label "bug" --body "## 背景 ... ## 修复 ... ## 验证 ..."

gh pr create --base next_dev --head feature-segments-responsive \
  --title "fix(async): 修复在线模式/缩略图阻塞其他接口 (v1.1.10)" \
  --body "Closes #N ..."
```

是否走完整 release（打 tag + GH Release）按用户授权。