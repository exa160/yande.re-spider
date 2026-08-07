# DAO 层规范

## 目录结构

```
backend/src/dao/
├── __init__.py              # 重新导出所有 DAO
├── database.py              # 数据库连接、BaseDAO 基类、Session 管理
├── favorite_dao.py           # 收藏夹数据访问
├── yande_data_dao.py         # 图片数据访问
├── tag_dao.py                # 标签缓存访问
└── artist_dao.py             # 艺术家缓存访问
```

## BaseDAO 基类（统一 Session 管理）

```python
# backend/src/dao/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

_cached_engine = None
_cached_session_factory = None


def get_db_engine():
    global _cached_engine
    if _cached_engine is not None:
        return _cached_engine
    # ... SQLite/MariaDB 配置


def _get_session_factory():
    global _cached_session_factory
    if _cached_session_factory is not None:
        return _cached_session_factory
    engine = get_db_engine()
    _cached_session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    return _cached_session_factory


class BaseDAO:
    """DAO 基类 - 统一 Session 管理"""

    def __init__(self, session: Session = None):
        self._session = session

    def __enter__(self):
        if self._session is None:
            self._session = _get_session_factory()()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            if exc_type is None:
                self._session.commit()
            else:
                self._session.rollback()
            self._session.close()
        return False

    @property
    def session(self) -> Session:
        if self._session is None:
            try:
                from src.middleware.session import RequestSessionMiddleware
                self._session = RequestSessionMiddleware.get_session()
            except Exception:
                self._session = _get_session_factory()()
        return self._session
```

## Session 管理架构

```
请求进入
    ↓
RequestSessionMiddleware 创建 session → ContextVar 存储
    ↓
DAO.session 属性自动获取请求级 session
    ↓
业务逻辑执行（add/query/flush 等）
    ↓
请求结束
    ↓
Middleware 自动 commit + close
```

**关键特性**：
- 每个 HTTP 请求绑定一个 session
- 同一请求内的所有 DAO 操作共享同一个 session
- 请求结束时自动 commit，异常时自动 rollback

## DAO 使用方式

### 方式一：FastAPI 请求内直接使用（推荐）

```python
# Service 层 - 不需要 with，直接调用
class FavoritesService:
    @staticmethod
    def get_all_folders():
        return favorite_dao.get_all()  # 自动使用请求级 session

    @staticmethod
    def create_folder(folder: FavoriteFolderCreate):
        count = favorite_dao.count()
        new_folder = favorite_dao.create(name=folder.name, ...)
        return new_folder
```

### 方式二：with DAO() 上下文管理器

**用于需要明确事务边界、确保 commit 的场景**：

```python
with YandeDataRepository() as repo:
    repo.upsert_batch(items)
    # 退出时自动 commit（或 rollback）
```

**适用场景**：
- 批量写入需要明确成功/失败
- 需要跨 DAO 方法共享 session
- 独立脚本/非 FastAPI 环境

### 方式三：独立 session（极少使用）

```python
dao = SomeDao()  # 不推荐，session 由中间件管理时无需手动创建
```

## DAO 编写规范

```python
# backend/src/dao/favorite_dao.py
from datetime import datetime
from typing import List, Optional, Type

from src.models.database.yande import FavoriteFolder
from src.dao.database import BaseDAO


class FavoriteDao(BaseDAO):
    def create(self, name: str, tags: str = "", ...) -> FavoriteFolder:
        folder = FavoriteFolder(name=name, tags=tags, ...)
        self.session.add(folder)
        self.session.flush()  # 获取自动生成的 ID
        return folder

    def get_by_id(self, folder_id: int) -> Optional[FavoriteFolder]:
        return self.session.query(FavoriteFolder).filter_by(id=folder_id).first()

    def update(self, folder_id: int, **kwargs) -> Optional[FavoriteFolder]:
        folder = self.session.query(FavoriteFolder).filter_by(id=folder_id).first()
        if not folder:
            return None
        for key, value in kwargs.items():
            if value is not None and hasattr(folder, key):
                setattr(folder, key, value)
        folder.updated_at = datetime.now()
        self.session.flush()  # 刷新内存中的对象状态
        return folder


favorite_dao = FavoriteDao()  # 全局实例
```

## 注意事项

| 操作 | 是否需要手动 commit | 说明 |
|------|---------------------|------|
| `session.add()` | 否 | 中间件请求结束时自动 commit |
| `session.flush()` | 否 | 用于刷新自增 ID 或获取最新状态 |
| `session.execute()` | 否 | 查询语句无需 commit |
| `session.delete()` | 否 | 删除操作由中间件统一提交 |
| `with DAO() as dao:` | 自动 | 退出时根据异常状态 commit/rollback |
| `dao.session` 属性 | 共享 | 同一请求内所有 DAO 共享同一 session |

## SQLite 特殊配置

```python
# SQLite 使用 StaticPool + 长超时避免锁竞争
_cached_engine = create_engine(
    f"sqlite:///{db_path}",
    connect_args={"timeout": 30, "check_same_thread": False},
    poolclass=StaticPool,
)
```

## 禁用 autoflush 场景

对于大量循环写入操作，使用 `no_autoflush` 避免频繁 flush：

```python
def calculate_local_stats(self) -> int:
    with self.session.no_autoflush:
        # 所有变更在块内暂存，不触发数据库写入
        for tag in tags:
            self.session.add(...)
    # 退出 with 时才真正写入
    return count
```

## DAO 单例的 ContextVar 依赖（v1.1.10+）

`favorite_dao = FavoriteDao()` 等单例的 `.session` 属性依赖 `RequestSessionMiddleware` 设置的 ContextVar。

- **请求内**（HTTP 路由 → service → 单例方法）：正常，自动获取请求 session。
- **请求外**（后台调度 / CLI / 单元测试）：**必须**用 `with DAO() as dao:` 显式上下文：

```python
# ✓ 正确
with FavoriteDao() as dao:
    folder = dao.get_by_id(folder_id)

# ✗ 错误（v1.1.10 起立即抛 RuntimeError）
folder = favorite_dao.get_by_id(folder_id)
```

违反时立即抛 `RuntimeError: RequestSessionMiddleware not active`，不再静默创建未托管 Session。