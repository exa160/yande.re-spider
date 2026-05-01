# Yande.re Spider 接口编写规范

> 本规范基于 `next_dev` 分支的重构经验总结构建，对比了 `next`（AI原写）和 `next_dev`（可读性重构后）的代码差异。

---

## 一、目录结构规范

### 推荐结构（next_dev 风格）

```
backend/src/
├── __init__.py              # init_app() 初始化函数
├── api/                     # API 路由层
│   ├── __init__.py          # APILoader 自动路由注册
│   └── v1/                  # API 版本控制
│       ├── __init__.py
│       ├── config.py
│       ├── download.py
│       ├── favorites.py
│       ├── gallery.py
│       ├── query.py
│       └── tag_cache.py
├── common/                  # 公共常量/配置
│   ├── __init__.py
│   ├── constant.py          # ErrMsg枚举、PathConstant、RouterMap
│   └── settings.py
├── middleware/              # 中间件层
│   ├── __init__.py
│   ├── errors.py            # APIException、ErrorHandleMiddleware
│   ├── loggers.py           # LoggerMiddleware
│   ├── downloader.py        # DownloadMiddleware
│   ├── frontend_static.py   # FrontendStaticLoader
│   └── session.py           # RequestSessionMiddleware（请求级 Session 管理）
├── models/                  # 数据模型层
│   ├── __init__.py
│   ├── database/            # 数据库模型
│   │   └── yande.py         # YandeData、YandeTag、YandeArtist 等
│   ├── download.py
│   ├── favorite.py
│   ├── yande.py
│   ├── request/             # 请求模型（Request DTO）
│   │   ├── __init__.py
│   │   └── config.py
│   └── response/            # 响应模型（Response DTO）
│       ├── __init__.py
│       ├── base_response.py # BaseResponse、ErrorResponse
│       └── config.py
├── dao/                    # 数据访问层
│   ├── __init__.py
│   ├── database.py         # BaseDAO、Session 管理
│   ├── favorite_dao.py     # 收藏夹数据访问
│   ├── yande_data_dao.py   # 图片数据访问
│   ├── tag_dao.py           # 标签缓存访问
│   └── artist_dao.py        # 艺术家缓存访问
├── infrastructure/          # 基础设施层
└── services/               # 业务逻辑层
```

### 层级职责划分

| 层级 | 职责 | 注意事项 |
|------|------|----------|
| `api/v1/` | 路由定义、参数校验、调用Service | **禁止**直接操作DAO/数据库 |
| `models/request/` | 接收前端参数的DTO | 使用 Pydantic `Field()` 定义校验规则 |
| `models/response/` | 返回给前端的DTO | 必须继承 `BaseResponse` |
| `services/` | 业务逻辑编排 | 处理复杂业务逻辑 |
| `dao/` | 数据访问封装 | **禁止**在DAO层处理业务逻辑 |
| `middleware/` | 横切关注点 | 错误处理、日志、下载中间件 |
| `common/` | 常量定义、枚举、路径配置 | **禁止**业务逻辑 |

---

## 二、API 路由编写规范

### 2.1 路由文件模板

```python
"""
[模块名称] API路由
"""

from typing import Optional, List

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from backend.src.models.response.base_response import BaseResponse
from backend.src.models.response.[模块] import [模块]Response
from backend.src.common.constant import ErrMsg
from backend.src.middleware.errors import APIException
from backend.src.services.[模块] import [模块]Service

router = APIRouter()

# ============================================
# Request Models（使用 Pydantic + Field 校验）
# ============================================

class CreateItemRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    tags: List[str] = Field(default_factory=list)
    enabled: bool = Field(default=True)


class UpdateItemRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)


# ============================================
# Response Models（放在 models/response/）
# ============================================

class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    tags: List[str]
    enabled: bool


# ============================================
# API Endpoints
# ============================================

@router.get("", response_model=BaseResponse)
async def get_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = None,
) -> BaseResponse:
    """获取列表（分页）"""
    try:
        items, total = [模块]Service.get_items(page, page_size, keyword)
        return BaseResponse(
            message=ErrMsg.OK.msg,
            data={"items": items, "total": total, "page": page, "page_size": page_size}
        )
    except Exception as e:
        raise APIException(ErrMsg.QUERY_ERROR, e=e)


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int) -> ItemResponse:
    """获取单个详情"""
    item = [模块]Service.get_by_id(item_id)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return ItemResponse(**item)


@router.post("", response_model=BaseResponse, status_code=status.HTTP_201_CREATED)
async def create_item(request: CreateItemRequest) -> BaseResponse:
    """创建"""
    try:
        item_id = [模块]Service.create(request)
        return BaseResponse(message="创建成功", data={"id": item_id})
    except Exception as e:
        raise APIException(ErrMsg.CREATE_ERROR, e=e)


@router.put("/{item_id}", response_model=BaseResponse)
async def update_item(item_id: int, request: UpdateItemRequest) -> BaseResponse:
    """更新"""
    try:
        [模块]Service.update(item_id, request)
        return BaseResponse(message="更新成功")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise APIException(ErrMsg.UPDATE_ERROR, e=e)


@router.delete("/{item_id}", response_model=BaseResponse)
async def delete_item(item_id: int) -> BaseResponse:
    """删除"""
    try:
        [模块]Service.delete(item_id)
        return BaseResponse(message="删除成功")
    except Exception as e:
        raise APIException(ErrMsg.DELETE_ERROR, e=e)
```

### 2.2 关键规则

1. **Request Model** 放在 `models/request/` 目录，使用 `Field()` 定义校验
2. **Response Model** 放在 `models/response/` 目录，**必须**继承 `BaseResponse`
3. **API 函数** 必须声明返回类型注解
4. **异常处理** 统一使用 `APIException(ErrMsg.XXX, e=e)` 模式
5. **HTTP状态码**：201 创建、400 参数错误、404 不存在、500 服务器错误

---

## 三、响应模型规范

### 3.1 BaseResponse（必须继承）

```python
from http import HTTPStatus
from typing import TypeVar, Generic, Optional, Any
from pydantic import BaseModel, model_validator
from backend.src.common.constant import ErrMsg

T = TypeVar('T')


class BaseResponse(BaseModel, Generic[T]):
    """
    统一响应类
    响应格式: {"code": "0000", "message": "OK.", "data": null}
    """
    code: str = '0000'
    message: Optional[str | ErrMsg] = ErrMsg.OK.msg
    data: Optional[T] = None

    @model_validator(mode='before')
    def extract_enum(self):
        """自动从 ErrMsg 枚举提取 code 和 message"""
        msg = self.get('message')
        if isinstance(msg, ErrMsg):
            self['code'] = msg.code
            self['message'] = msg.msg
        return self


class ErrorResponse(BaseResponse):
    """错误响应（code 固定为 9999）"""
    code: str = '9999'
```

### 3.2 响应格式约定

| 场景 | code | message | data |
|------|------|---------|------|
| 成功 | `0000` | `ErrMsg.OK.msg` | 业务数据 |
| 错误 | 非`0000` | 错误描述 | 可选附加数据 |

### 3.3 响应示例

```python
# 标准成功响应
BaseResponse(message=ErrMsg.OK.msg, data={"id": 1, "name": "test"})

# 带错误码的成功响应
BaseResponse(message=ErrMsg.CONFIG_UPDATE_SUCCESS)

# 错误响应（通过 APIException）
raise APIException(ErrMsg.CONFIG_UPDATE_ERROR, e=e)
```

---

## 四、异常处理规范

### 4.1 ErrMsg 枚举定义

```python
from enum import Enum
from http import HTTPStatus


class BaseMsgEnum(Enum):
    def __new__(cls, code: str, msg: str, http_status: HTTPStatus = None):
        obj = object.__new__(cls)
        obj.code = code
        obj.msg = msg
        obj.http_status = HTTPStatus.OK if http_status is None else http_status
        return obj


class ErrMsg(BaseMsgEnum):
    # 系统级
    OK = ("0000", "OK.")
    
    # 通用错误
    QUERY_ERROR = ("0001", "Query error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    CREATE_ERROR = ("0002", "Create error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    UPDATE_ERROR = ("0003", "Update error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    DELETE_ERROR = ("0004", "Delete error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    NOT_FOUND = ("0005", "Resource not found.", HTTPStatus.NOT_FOUND)
    PARAM_ERROR = ("0006", "Invalid parameter.", HTTPStatus.BAD_REQUEST)
    
    # 业务特定错误
    CONFIG_UPDATE_SUCCESS = ("0000", "配置更新成功")
    CONFIG_UPDATE_ERROR = ("1001", "Config update error.", HTTPStatus.INTERNAL_SERVER_ERROR)
    CONFIG_RESET_ERROR = ("1002", "Config reset error.", HTTPStatus.INTERNAL_SERVER_ERROR)
```

### 4.2 APIException 使用

```python
from fastapi import HTTPException
from backend.src.middleware.errors import APIException

# 基本用法
raise APIException(ErrMsg.NOT_FOUND)

# 带附加数据
raise APIException(ErrMsg.PARAM_ERROR, data={"field": "name", "reason": "too long"})

# 捕获异常并传递
try:
    result = service.do_something()
except Exception as e:
    raise APIException(ErrMsg.QUERY_ERROR, e=e)

# 不使用 APIException 的情况（FastAPI 自动处理）
raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
```

### 4.3 错误中间件（ErrorHandleMiddleware）

```python
class ErrorHandleMiddleware:
    @staticmethod
    def init_app(app: FastAPI):
        @app.exception_handler(APIException)
        async def global_exception_handler(request, exc):
            logger.error(f"Exception: {exc}")
            return JSONResponse(
                status_code=exc.http_status.value,
                content=ErrorResponse(
                    code=exc.err_code,
                    message=exc.err_msg,
                    data=exc.data
                ).model_dump(mode="json")
            )

        @app.exception_handler(Exception)
        async def global_exception_handler(request, exc):
            logger.error(f"Exception: {exc}")
            return JSONResponse(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR.value,
                content=ErrorResponse(
                    message=f"{HTTPStatus.INTERNAL_SERVER_ERROR.description}: {str(exc)}"
                ).model_dump(mode="json")
            )
```

---

## 四、DAO 层规范

### 4.1 目录结构

```
backend/src/dao/
├── __init__.py              # 重新导出所有 DAO
├── database.py              # 数据库连接、BaseDAO 基类、Session 管理
├── favorite_dao.py           # 收藏夹数据访问
├── yande_data_dao.py         # 图片数据访问
├── tag_dao.py                # 标签缓存访问
└── artist_dao.py             # 艺术家缓存访问
```

### 4.2 BaseDAO 基类（统一 Session 管理）

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

### 4.3 Session 管理架构

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

### 4.4 DAO 使用方式

#### 方式一：FastAPI 请求内直接使用（推荐）

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

#### 方式二：with DAO() 上下文管理器

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

#### 方式三：独立 session（极少使用）

```python
dao = SomeDao()  # 不推荐，session 由中间件管理时无需手动创建
```

### 4.5 DAO 编写规范

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

### 4.6 注意事项

| 操作 | 是否需要手动 commit | 说明 |
|------|---------------------|------|
| `session.add()` | 否 | 中间件请求结束时自动 commit |
| `session.flush()` | 否 | 用于刷新自增 ID 或获取最新状态 |
| `session.execute()` | 否 | 查询语句无需 commit |
| `session.delete()` | 否 | 删除操作由中间件统一提交 |
| `with DAO() as dao:` | 自动 | 退出时根据异常状态 commit/rollback |
| `dao.session` 属性 | 共享 | 同一请求内所有 DAO 共享同一 session |

### 4.7 SQLite 特殊配置

```python
# SQLite 使用 StaticPool + 长超时避免锁竞争
_cached_engine = create_engine(
    f"sqlite:///{db_path}",
    connect_args={"timeout": 30, "check_same_thread": False},
    poolclass=StaticPool,
)
```

### 4.8 禁用 autoflush 场景

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

---

## 五、中间件规范

### 5.1 中间件注册顺序

在 `backend/src/__init__.py` 的 `init_app()` 中按顺序注册：

```python
def init_app(app: FastAPI) -> FastAPI:
    # 1. CORS（FastAPI 内置）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 2. 自定义中间件（按依赖顺序）
    DownloadMiddleware.init_app(app)    # 下载相关
    APILoader.init_app(app)             # 路由加载
    LoggerMiddleware.init_app(app)       # 日志记录
    ErrorHandleMiddleware.init_app(app)  # 错误处理（最后注册）
    
    # ...
```

### 5.2 自定义中间件模板

```python
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware


class MyCustomMiddleware(BaseHTTPMiddleware):
    @staticmethod
    async def dispatch(request: Request, call_next):
        # 前置处理
        response = await call_next(request)
        # 后置处理
        return response
    
    @classmethod
    def init_app(cls, app: FastAPI):
        app.add_middleware(cls)
```

## 六、中间件规范

### 6.1 中间件注册顺序

在 `backend/src/__init__.py` 的 `init_app()` 中按顺序注册：

```python
def init_app(app: FastAPI) -> FastAPI:
    # 1. CORS（FastAPI 内置）
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # 2. 自定义中间件（按依赖顺序）
    app.add_middleware(RequestSessionMiddleware)  # Session 管理
    DownloadMiddleware.init_app(app)             # 下载相关
    APILoader.init_app(app)                       # 路由加载
    LoggerMiddleware.init_app(app, path_constant.log_dir)
    ErrorHandleMiddleware.init_app(app)          # 错误处理（最后注册）
    
    # ...
```

### 6.2 自定义中间件模板

```python
from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware


class MyCustomMiddleware(BaseHTTPMiddleware):
    @staticmethod
    async def dispatch(request: Request, call_next):
        # 前置处理
        response = await call_next(request)
        # 后置处理
        return response
    
    @classmethod
    def init_app(cls, app: FastAPI):
        app.add_middleware(cls)
```

### 6.3 RequestSessionMiddleware（Session 管理）

```python
# src/middleware/session.py
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from contextvars import ContextVar
from sqlalchemy.orm import Session
from typing import Optional

from src.dao.database import get_db_engine, _get_session_factory

_request_session: ContextVar[Optional[Session]] = ContextVar("request_session", default=None)


class RequestSessionMiddleware(BaseHTTPMiddleware):
    @staticmethod
    def get_session() -> Session:
        session = _request_session.get()
        if session is None:
            session = _get_session_factory()()
            _request_session.set(session)
        return session

    async def dispatch(self, request: Request, call_next):
        session = _get_session_factory()()
        _request_session.set(session)

        try:
            response = await call_next(request)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
            _request_session.set(None)

        return response
```

---

## 七、自动路由注册规范

### 6.1 APILoader（自动路由发现）

```python
# backend/src/api/__init__.py
import inspect
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Optional

from fastapi import FastAPI, APIRouter
from loguru import logger
from backend.src.common.constant import RouterMap


class APILoader:
    def __init__(self):
        self.base_path = Path(__file__).resolve().parent

    @staticmethod
    def init_app(app: FastAPI) -> FastAPI:
        api_loader = APILoader()
        api_loader.init_api(app)
        return app

    def registry_router_from_file(self, app: FastAPI, file_path: Path) -> ModuleType:
        module_name = file_path.stem
        prefix = file_path.relative_to(self.base_path.parent).with_suffix('')
        
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Load API failed: {file_path}")
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        for router_name, obj in inspect.getmembers(module):
            if isinstance(obj, APIRouter):
                app.include_router(
                    obj,
                    prefix=f"/{str(prefix.as_posix())}",
                    tags=RouterMap.get_tags(module_name)
                )
        return module

    def init_api(self, app: FastAPI) -> None:
        logger.info("API registry start.")
        for file_path in self.base_path.rglob("*.py"):
            if file_path.name.startswith("_"):
                continue
            try:
                self.registry_router_from_file(app, file_path)
            except Exception as e:
                logger.warning(f"Load router failed: {e}")
        logger.info("API registry finish.")
```

### 6.2 RouterMap（路由标签枚举）

```python
class RouterMap(Enum):
    config = ["配置"]
    download = ["下载"]
    favorites = ["收藏夹"]
    gallery = ["图库"]
    query = ["查询"]
    tag_cache = ["标签缓存"]

    @classmethod
    def get_tags(cls, name: str):
        member = cls.__members__.get(name)
        return member.value if member else None
```

---

## 七、配置常量规范

### 7.1 PathConstant（路径常量）

```python
from pathlib import Path
from pydantic import BaseModel, ConfigDict


class ConstantModel(BaseModel):
    model_config = ConfigDict(frozen=True)  # 不可变配置


class PathConstant(ConstantModel):
    base_dir: Path = Path(__file__).parent.parent.parent
    
    download_dir: Path = base_dir / "downloads"
    previews_dir: Path = download_dir / "previews"
    originals_dir: Path = download_dir / "originals"
    config_dir: Path = base_dir / "config"
    config_file: Path = config_dir / "config.yaml"
    data_dir: Path = base_dir / "data"
    sqlite_file: Path = data_dir / "yande_data.db"
    log_dir: Path = base_dir / "log"
    frontend_dist: Path = base_dir / "frontend-dist"


path_constant = PathConstant()
```

### 7.2 TaskStatus（任务状态枚举）

```python
class TaskStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

---

## 八、对比：重构前 vs 重构后

### 8.1 目录结构对比

| 方面 | 重构前（next） | 重构后（next_dev） |
|------|--------------|------------------|
| API入口 | `api/main.py`（手动注册） | `backend/src/__init__.py`（自动发现） |
| 路由定义 | `backend/api/routers/*.py` | `backend/src/api/v1/*.py` |
| 响应模型 | 散落在各处 | `models/response/base_response.py` |
| 错误处理 | 分散的 HTTPException | 统一的 APIException + ErrMsg |
| 常量管理 | `backend/config/constant.py` | `backend/src/common/constant.py` |
| 中间件 | 无专门的 middleware 层 | `middleware/` 目录独立 |

### 8.2 关键代码对比

**错误响应（before）：**
```python
raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"更新失败: {str(e)}")
return {"success": False, "message": f"连接失败: {str(e)}"}
```

**错误响应（after）：**
```python
raise APIException(ErrMsg.CONFIG_UPDATE_ERROR, e=e)
return BaseResponse(message="数据库连接成功", data={"success": True})
```

**路由注册（before）：**
```python
from backend.api.routers import config, download
app.include_router(config.router, prefix="/api/v1/config", tags=["配置"])
app.include_router(download.router, prefix="/api/v1/download", tags=["下载"])
```

**路由注册（after）：**
```python
# 只需调用 APILoader.init_app(app)，自动发现所有路由
```

**响应格式（before）：**
```python
{"code": 500, "message": "服务器内部错误"}
{"success": True, "message": "SQLite数据库文件存在"}
```

**响应格式（after）：**
```python
{"code": "0000", "message": "OK.", "data": {...}}
{"code": "9999", "message": "Config update error.", "data": null}
```

---

## 九、代码风格要点

1. **类型注解**：所有函数必须声明返回类型
2. **Pydantic Field**：请求模型使用 `Field()` 定义校验规则
3. **docstring**：每个 API 路由添加 `"""描述"""` 文档字符串
4. **日志记录**：在 `middleware/loggers.py` 统一日志格式
5. **枚举优先**：状态码、错误码使用枚举而非硬编码字符串
6. **frozen 配置**：PathConstant 等配置类使用 `frozen=True` 防止意外修改

---

## 十、提交规范

重构相关的 commit message 格式：
```
对AI写的代码进行可读性重构

- 规范化错误码枚举（ErrMsg）
- 统一响应格式（BaseResponse）
- 添加自动路由发现（APILoader）
- 拆分中间件层（middleware/）
```

---

## 十一、重构状态追踪

### 11.1 已完成的重构（next_dev 分支）

| 重构项 | 状态 | 提交记录 |
|--------|------|----------|
| 目录结构重组（backend/src/） | ✅ 完成 | 738beef, d4a01e4 |
| 自动路由注册（APILoader） | ✅ 完成 | b8afae8 |
| 统一响应格式（BaseResponse） | ✅ 完成 | 1489e01 |
| 统一错误处理（APIException + ErrMsg） | ✅ 完成 | 1489e01 |
| 中间件层拆分（middleware/） | ✅ 完成 | 6ef8596 |
| 常量管理统一（PathConstant） | ✅ 完成 | 8a05889 |
| 导入路径标准化（src.xxx） | ✅ 完成 | 8a05889 |
| DAO 层重构 | ✅ 完成 | bea5017 |
| API 路由系统重构 | ✅ 完成 | 3331539 |
| 数据库模型模块化 | ✅ 完成 | 8ce9224 |

### 11.2 待完成的重构

| 重构项 | 优先级 | 说明 |
|--------|--------|------|
| 修复 __init__.py 日志消息 | 中 | "Flask" 应改为 "FastAPI" |
| 补全 ErrMsg 枚举 | 中 | 缺少 QUERY_ERROR, CREATE_ERROR 等通用错误码 |

### 11.3 代码规范检查清单

**API 路由文件检查**：
- [ ] 是否使用 `APIException(ErrMsg.XXX, e=e)` 模式
- [ ] 是否返回 `BaseResponse` 或继承类
- [ ] 是否声明返回类型注解
- [ ] 是否添加 docstring
- [ ] Request Model 是否使用 `Field()` 校验

**响应格式检查**：
- [ ] 成功响应：`BaseResponse(message=ErrMsg.OK.msg, data={...})`
- [ ] 错误响应：`raise APIException(ErrMsg.XXX, e=e)`
- [ ] 避免返回原始字典

---

*最后更新：基于 next_dev 分支 fd42787 提交记录总结*
