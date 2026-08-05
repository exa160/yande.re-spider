# 技术设计文档

## 文档信息
- **项目名称**: yande.re-spider-next
- **功能名称**: 高级查询功能与多端界面优化
- **版本**: v1.0
- **创建日期**: 2025-03-26
- **最后更新**: 2025-03-26

## 1. 架构概览

### 1.1 系统架构图
```
┌─────────────────────────────────────────────────────────────┐
│                        表示层 (Presentation)                 │
├─────────────────────────────────────────────────────────────┤
│  Web界面 (Vue.js)  │  桌面客户端 (Electron)  │  移动端 (响应式) │
│  ├─ 图库展示组件    │  ├─ 主窗口              │  ├─ 触摸优化     │
│  ├─ 下载管理组件    │  ├─ 系统托盘            │  └─ 手势支持     │
│  ├─ 配置管理组件    │  └─ 本地API调用         │                  │
│  └─ 高级查询组件    │                         │                  │
└─────────────────────────────────────────────────────────────┘
> **架构图修订（2026-08-05）**：原"桌面客户端 (Electron)"节点已升级为
> **Windows 客户端（NSIS）**，技术栈由 Electron 改为 PyWebView + PyInstaller + NSIS。
> 详见实施文档 [docs/superpowers/specs/2026-08-05-windows-client-design.md](../superpowers/specs/2026-08-05-windows-client-design.md)。
                              ↓ HTTP/WebSocket
┌─────────────────────────────────────────────────────────────┐
│                    业务逻辑层 (Business Logic)               │
├─────────────────────────────────────────────────────────────┤
│  FastAPI 后端服务 (Python 3.12+)                             │
│  ├─ 统一查询服务 (UnifiedQueryService)                       │
│  ├─ 下载管理服务 (DownloadManagerService)                    │
│  ├─ 图库展示服务 (GalleryService)                            │
│  ├─ 配置管理服务 (ConfigService)                             │
│  └─ 任务调度服务 (TaskSchedulerService)                      │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    数据访问层 (Data Access)                  │
├─────────────────────────────────────────────────────────────┤
│  ├─ YandeAPI客户端 (现有yande_api.py增强)                    │
│  ├─ 数据库访问层 (MariaDBClient/SQLiteClient)                │
│  ├─ 文件存储访问层 (FileStorageService)                      │
│  └─ 缓存访问层 (CacheService)                                │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    基础设施层 (Infrastructure)               │
├─────────────────────────────────────────────────────────────┤
│  ├─ 下载器 (MultiDown增强)                                   │
│  ├─ 重复检测器 (DuplicateDetector)                           │
│  ├─ 日志系统 (Loguru)                                        │
│  ├─ 配置管理 (Pydantic)                                      │
│  └─ 工具库 (pathvalidate, requests等)                        │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 架构说明

本系统采用分层架构设计，主要分为四层：

1. **表示层**：负责用户界面展示和交互，支持Web、桌面、移动端三种访问方式
   - Web界面使用Vue.js框架，提供响应式设计
   - 桌面客户端使用Electron封装Web界面，提供原生体验
   - 移动端通过响应式设计适配不同屏幕尺寸

2. **业务逻辑层**：负责核心业务处理，使用FastAPI提供RESTful API
   - 统一查询服务：提供高级查询功能，界面和下载模块共同使用
   - 下载管理服务：管理下载任务、进度跟踪、重复检测
   - 图库展示服务：处理图片展示、预览、筛选
   - 配置管理服务：管理系统配置
   - 任务调度服务：调度异步任务

3. **数据访问层**：负责数据存储和检索
   - YandeAPI客户端：与yande.re API交互
   - 数据库访问层：支持MariaDB/MySQL和SQLite
   - 文件存储访问层：管理文件下载和存储
   - 缓存访问层：提供缓存机制

4. **基础设施层**：提供通用工具和基础服务
   - 增强的下载器：支持多线程下载、进度跟踪
   - 重复检测器：支持多种重复检测策略
   - 日志系统、配置管理等基础服务

### 1.3 技术选型
| 技术领域 | 技术选择 | 选择理由 |
|---------|---------|---------|
| 后端框架 | FastAPI | 高性能异步框架，自动生成API文档，支持类型提示，适合Python 3.12+ |
| 前端框架 | Vue.js 3 | 组件化开发，响应式设计，生态完善，学习曲线平缓 |
| 桌面客户端 | Electron | 跨平台支持，可复用Web界面，原生API访问能力 |
| 数据库 | MariaDB/SQLite | MariaDB用于生产环境，SQLite用于轻量级部署，兼容现有系统 |
| ORM | SQLAlchemy | 成熟的ORM框架，支持多种数据库，类型安全 |
| 异步任务 | asyncio + aiohttp | 原生异步支持，高性能IO操作 |
| 数据验证 | Pydantic v2 | 类型安全，数据验证，与FastAPI完美集成 |
| 日志系统 | Loguru | 简单易用，功能强大，已在项目中使用 |
| 前端UI库 | Element Plus | Vue 3组件库，组件丰富，文档完善 |
| 状态管理 | Pinia | Vue 3官方推荐的状态管理库 |
| HTTP客户端 | Axios | 成熟的HTTP客户端，支持拦截器 |

## 2. 模块设计

### 2.1 统一查询模块 (UnifiedQueryModule)

#### 2.1.1 模块职责
提供统一的高级查询接口，供界面展示和下载功能共同使用，确保查询逻辑一致性。

#### 2.1.2 类图
```
┌─────────────────────────────────────┐
│      UnifiedQueryService            │
├─────────────────────────────────────┤
│ - yande_api: YandeApi                │
│ - db_client: DatabaseClient          │
│ - cache: CacheService                │
├─────────────────────────────────────┤
│ + query(params: QueryParams)         │
│ + query_by_tags(tags: List[str])     │
│ + query_by_score(min: int, max: int) │
│ + query_by_resolution(...)           │
│ + build_query_string(params)         │
│ + validate_params(params)            │
└─────────────────────────────────────┘
         ↓ uses
┌─────────────────────────────────────┐
│         QueryParams                  │
├─────────────────────────────────────┤
│ + tags: List[TagFilter]              │
│ + score_range: Optional[Range]       │
│ + resolution: Optional[Resolution]   │
│ + file_types: List[FileType]         │
│ + ratings: List[Rating]              │
│ + page: int                          │
│ + limit: int                         │
└─────────────────────────────────────┘
```

#### 2.1.3 接口定义
```python
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from enum import Enum

class LogicOperator(str, Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"

class TagFilter(BaseModel):
    tag: str
    operator: LogicOperator = LogicOperator.AND

class ResolutionFilter(BaseModel):
    min_width: Optional[int] = None
    max_width: Optional[int] = None
    min_height: Optional[int] = None
    max_height: Optional[int] = None

class FileType(str, Enum):
    JPG = "jpg"
    PNG = "png"
    GIF = "gif"
    WEBP = "webp"

class Rating(str, Enum):
    SAFE = "s"
    QUESTIONABLE = "q"
    EXPLICIT = "e"

class QueryParams(BaseModel):
    """统一查询参数模型"""
    tags: List[TagFilter] = Field(default_factory=list)
    score_min: Optional[int] = None
    score_max: Optional[int] = None
    resolution: Optional[ResolutionFilter] = None
    file_types: List[FileType] = Field(default_factory=list)
    ratings: List[Rating] = Field(default_factory=list)
    author: Optional[str] = None
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=20, ge=1, le=100)

class QueryResult(BaseModel):
    """查询结果模型"""
    items: List[YandePostItem]
    total: int
    page: int
    has_more: bool

class UnifiedQueryService:
    """统一查询服务"""
    
    async def query(self, params: QueryParams) -> QueryResult:
        """执行统一查询"""
        pass
    
    def build_query_string(self, params: QueryParams) -> str:
        """构建yande.re API查询字符串"""
        pass
    
    def validate_params(self, params: QueryParams) -> bool:
        """验证查询参数"""
        pass
```

#### 2.1.4 关键流程
```
用户输入查询条件
    ↓
构建QueryParams对象
    ↓
验证参数有效性
    ↓
构建yande.re API查询字符串
    ↓
调用YandeAPI获取数据
    ↓
应用客户端过滤（评分、分辨率等）
    ↓
返回QueryResult
```

### 2.2 下载管理模块 (DownloadManagerModule)

#### 2.2.1 模块职责
管理下载任务生命周期，支持重复检测、进度跟踪、数据持久化。

#### 2.2.2 接口定义
```python
from pydantic import BaseModel
from typing import List, Optional
from enum import Enum
from datetime import datetime

class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class DownloadTask(BaseModel):
    """下载任务模型"""
    task_id: str
    query_params: QueryParams  # 关联的查询条件
    save_path: str
    status: DownloadStatus = DownloadStatus.PENDING
    total_count: int = 0
    completed_count: int = 0
    skipped_count: int = 0  # 重复跳过的数量
    failed_count: int = 0
    created_at: datetime
    updated_at: datetime

class DownloadProgress(BaseModel):
    """下载进度模型"""
    task_id: str
    file_name: str
    file_size: int
    downloaded_size: int
    speed: float  # MB/s
    progress: float  # 0-100
    remaining_time: Optional[int]  # seconds

class DuplicateCheckStrategy(str, Enum):
    ID = "id"  # 通过ID检查
    FILE_PATH = "file_path"  # 通过文件路径检查
    MD5 = "md5"  # 通过MD5检查

class DownloadManagerService:
    """下载管理服务"""
    
    async def create_task(
        self, 
        query_params: QueryParams, 
        save_path: str,
        duplicate_check: bool = True,
        proxy_config: Optional[ProxyConfig] = None
    ) -> DownloadTask:
        """创建下载任务"""
        pass
    
    async def start_task(self, task_id: str) -> None:
        """启动下载任务"""
        pass
    
    async def pause_task(self, task_id: str) -> None:
        """暂停下载任务"""
        pass
    
    async def resume_task(self, task_id: str) -> None:
        """恢复下载任务"""
        pass
    
    async def cancel_task(self, task_id: str) -> None:
        """取消下载任务"""
        pass
    
    async def get_progress(self, task_id: str) -> List[DownloadProgress]:
        """获取下载进度"""
        pass

class ProxyConfig(BaseModel):
    """代理配置模型"""
    enabled: bool = False
    http: Optional[str] = None
    https: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    
    def to_proxies_dict(self) -> Optional[dict]:
        """转换为requests库使用的proxies字典"""
        if not self.enabled:
            return None
        
        proxies = {}
        if self.http:
            proxies['http'] = self.http
        if self.https:
            proxies['https'] = self.https
        return proxies if proxies else None

class DuplicateDetector:
    """重复检测器"""
    
    def check_by_id(self, image_id: int, db_client) -> bool:
        """通过ID检查是否已存在"""
        pass
    
    def check_by_path(self, file_path: str) -> bool:
        """通过文件路径检查是否已存在"""
        pass
    
    def check_by_md5(self, md5: str, file_path: str) -> bool:
        """通过MD5校验文件完整性"""
        pass
    
    def scan_existing_ids(self, directory: str) -> set[int]:
        """扫描目录中已存在的图片ID"""
        pass
```

### 2.3 数据持久化模块 (DataPersistenceModule)

#### 2.3.1 模块职责
负责下载成功后的数据持久化，将图片信息记录到数据库。复用现有的YandeData模型和MariaDBClient。

#### 2.3.2 接口定义
```python
from datetime import datetime
from typing import Optional
from utils.database import MariaDBClient
from utils.items import YandePostItem

class DataPersistenceService:
    """数据持久化服务"""
    
    def __init__(self, db_client: MariaDBClient = None):
        """初始化服务，可选传入现有的MariaDBClient实例"""
        self.db_client = db_client or MariaDBClient()
    
    async def save_image_record(
        self, 
        image_data: YandePostItem, 
        local_path: str
    ) -> bool:
        """
        保存图片记录到数据库
        复用现有的MariaDBClient.YandeData模型
        """
        try:
            # 使用现有的YandeData模型和insert_by_id方法
            yande_data = MariaDBClient.YandeData(**image_data.model_dump())
            self.db_client.insert_by_id(image_data.id, yande_data)
            return True
        except Exception as e:
            logger.error(f"保存图片记录失败: {e}")
            return False
    
    async def batch_save(
        self, 
        images: List[tuple[YandePostItem, str]]
    ) -> int:
        """批量保存图片记录"""
        success_count = 0
        for image_data, local_path in images:
            if await self.save_image_record(image_data, local_path):
                success_count += 1
        return success_count
    
    async def check_exists(self, image_id: int) -> bool:
        """
        检查图片是否已存在数据库
        复用现有的insert_check_by_id方法
        """
        return not self.db_client.insert_check_by_id(image_id)
```

### 2.4 图库展示模块 (GalleryModule)

#### 2.4.1 模块职责
提供图库展示功能，支持瀑布流布局、图片预览、筛选。

#### 2.4.2 接口定义
```python
class GalleryService:
    """图库展示服务"""
    
    async def load_gallery(
        self, 
        query_params: QueryParams,
        page: int = 1
    ) -> QueryResult:
        """加载图库数据"""
        pass
    
    async def get_image_detail(self, image_id: int) -> YandePostItem:
        """获取图片详情"""
        pass
    
    async def convert_to_download_task(
        self, 
        query_params: QueryParams,
        save_path: str
    ) -> DownloadTask:
        """将当前查询条件转换为下载任务"""
        pass
```

## 3. 数据设计

### 3.1 数据模型
```python
# 复用现有的YandeData模型，扩展新的模型

# 现有的YandeData模型（utils/database.py）保持不变
# 该模型已经包含完整的图片元数据字段，直接复用

class YandeData(Base):
    """现有的yande.re图片数据模型（保持不变）"""
    __tablename__ = 'yande_re'
    id = Column(Integer, unique=True, primary_key=True)
    down_flag = Column(Boolean, default=True, primary_key=True)
    tags = Column(String(918), nullable=True)
    created_at = Column(DateTime, primary_key=True)
    updated_at = Column(DateTime, primary_key=True)
    # ... 其他字段保持不变（见utils/database.py）

# YandeData处理策略：
# 1. 保持现有模型完全不变，确保向后兼容
# 2. 复用现有的MariaDBClient方法：
#    - insert_check_by_id(id): 检查图片是否已存在
#    - insert_by_id(id, data): 插入图片数据（自动去重）
# 3. 在新系统中继续使用YandeData存储图片元数据
# 4. 支持双数据库配置（MariaDB/SQLite）

# 新增的扩展模型

class DownloadTask(Base):
    """下载任务模型"""
    __tablename__ = 'download_tasks'
    task_id = Column(String(36), primary_key=True)  # UUID
    query_params = Column(JSON)  # 存储QueryParams的JSON
    save_path = Column(String(512))
    status = Column(Enum(DownloadStatus))
    total_count = Column(Integer, default=0)
    completed_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

class DownloadHistory(Base):
    """下载历史记录模型"""
    __tablename__ = 'download_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(36), ForeignKey('download_tasks.task_id'))
    image_id = Column(Integer, ForeignKey('yande_re.id'))
    file_name = Column(String(256))
    file_path = Column(String(512))
    file_size = Column(Integer)
    status = Column(Enum(DownloadStatus))
    downloaded_at = Column(DateTime)
    error_message = Column(Text, nullable=True)

class QueryPreset(Base):
    """查询条件预设模型"""
    __tablename__ = 'query_presets'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), unique=True)
    params = Column(JSON)  # 存储QueryParams的JSON
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
```

### 3.2 数据关系图
```
┌──────────────┐
│  YandeData   │ (现有模型，保持不变)
├──────────────┤
│ id (PK)      │
│ tags         │
│ author       │
│ score        │
│ ...          │
└──────────────┘
       ↑
       │ (外键关联)
       │
┌──────────────┐
│DownloadHistory│
├──────────────┤
│ id (PK)      │
│ task_id (FK) │───→ DownloadTask
│ image_id (FK)│───→ YandeData
└──────────────┘

┌──────────────┐
│ DownloadTask │
├──────────────┤
│ task_id (PK) │
│ query_params │──────┐
└──────────────┘      │
                      │
┌──────────────┐      │
│QueryPreset   │      │
├──────────────┤      │
│ id (PK)      │      │
│ params       │←─────┘
└──────────────┘
```

**数据模型处理策略**：
1. **YandeData模型**：完全复用现有的`MariaDBClient.YandeData`模型，不做任何修改
2. **MariaDBClient类**：保留现有的数据库操作方法（insert_by_id、insert_check_by_id等）
3. **新增模型**：创建新的SQLAlchemy模型（DownloadTask、DownloadHistory、QueryPreset）
4. **数据库兼容**：确保新模型与现有YandeData模型兼容，使用相同的基础配置

### 3.3 数据存储
- **主数据库**：MariaDB/MySQL，存储图片元数据、下载历史、查询预设
- **轻量级数据库**：SQLite，用于单机部署场景
- **文件存储**：本地文件系统，存储下载的图片文件
- **缓存**：内存缓存（可选Redis），缓存查询结果和图片预览

## 4. API设计

### 4.1 外部API

#### 4.1.1 统一查询API
- **请求方法**: POST
- **请求路径**: /api/v1/query
- **请求参数**: QueryParams (JSON)
- **响应格式**: QueryResult (JSON)
- **错误处理**: 400参数错误，500服务器错误

#### 4.1.2 下载任务API
- **创建任务**: POST /api/v1/download/task
- **启动任务**: POST /api/v1/download/task/{task_id}/start
- **暂停任务**: POST /api/v1/download/task/{task_id}/pause
- **取消任务**: DELETE /api/v1/download/task/{task_id}
- **查询进度**: GET /api/v1/download/task/{task_id}/progress

#### 4.1.3 图库API
- **加载图库**: POST /api/v1/gallery/load
- **图片详情**: GET /api/v1/gallery/image/{image_id}

### 4.2 内部API

#### 4.2.1 重复检测API
- **功能**: 检查图片是否已存在
- **输入**: image_id, file_path, md5
- **输出**: exists: bool
- **异常**: DatabaseError

#### 4.2.2 数据持久化API
- **功能**: 保存图片记录到数据库
- **输入**: YandePostItem, local_path
- **输出**: success: bool
- **异常**: DatabaseError, ValidationError

## 5. 界面设计

### 5.1 界面结构
```
┌─────────────────────────────────────────────────────┐
│ 顶部导航栏                                          │
│ [Logo] [搜索框] [高级查询] [设置] [主题切换]        │
└─────────────────────────────────────────────────────┘
┌──────────┬──────────────────────────────────────────┐
│ 侧边栏   │ 主内容区                                  │
│          │                                           │
│ [图库]   │ ┌────────────────────────────────────┐  │
│ [下载]   │ │ 高级查询面板                        │  │
│ [配置]   │ │ [标签] [评分] [分辨率] [文件类型]   │  │
│ [历史]   │ └────────────────────────────────────┘  │
│          │                                           │
│          │ ┌────────────────────────────────────┐  │
│          │ │ 瀑布流图库展示                      │  │
│          │ │ [图片] [图片] [图片] [图片]         │  │
│          │ │ [图片] [图片] [图片] [图片]         │  │
│          │ └────────────────────────────────────┘  │
└──────────┴──────────────────────────────────────────┘
┌─────────────────────────────────────────────────────┐
│ 状态栏: [下载状态] [网络状态] [任务数量]            │
└─────────────────────────────────────────────────────┘
```

### 5.2 界面组件

#### 5.2.1 高级查询组件 (AdvancedQueryComponent)
- **功能**: 提供高级查询界面，支持多条件组合
- **属性**: queryParams, presetList
- **状态**: loading, validationErrors
- **事件**: querySubmit, presetSave, presetLoad

#### 5.2.2 瀑布流图库组件 (WaterfallGalleryComponent)
- **功能**: 瀑布流展示图片，支持无限滚动
- **属性**: images, columns, loading
- **状态**: scrollPosition, loadedPages
- **事件**: imageClick, scrollEnd, retry

#### 5.2.3 下载管理组件 (DownloadManagerComponent)
- **功能**: 显示下载任务列表和进度
- **属性**: tasks, selectedTask
- **状态**: refreshing, sorting
- **事件**: taskPause, taskResume, taskCancel

#### 5.2.4 配置管理组件 (ConfigManagerComponent)
- **功能**: 可视化编辑配置
- **属性**: config, validationRules
- **状态**: editing, hasChanges
- **事件**: configSave, configReset, configExport

### 5.3 界面流程
```
用户进入图库页面
    ↓
显示默认查询结果（最新图片）
    ↓
用户设置高级查询条件
    ↓
提交查询请求
    ↓
显示查询结果（瀑布流）
    ↓
用户点击图片预览
    ↓
显示图片详情和操作按钮
    ↓
用户选择下载
    ↓
创建下载任务（使用相同查询条件）
    ↓
跳转到下载管理页面
    ↓
显示下载进度
```

## 6. 配置设计

### 6.1 配置项
| 配置名称 | 类型 | 默认值 | 说明 |
|---------|------|--------|------|
| server.host | string | "127.0.0.1" | 服务器监听地址 |
| server.port | int | 8000 | 服务器监听端口 |
| database.type | string | "sqlite" | 数据库类型（sqlite/mariadb） |
| database.path | string | "data.db" | SQLite数据库路径 |
| download.thread_num | int | 4 | 下载线程数 |
| download.chunk_size | int | 10240 | 下载分块大小 |
| download.duplicate_check | bool | true | 启用重复检测 |
| download.save_to_db | bool | true | 下载成功后保存到数据库 |
| download.proxy.enabled | bool | false | 启用下载代理 |
| download.proxy.http | string | "" | HTTP代理地址 |
| download.proxy.https | string | "" | HTTPS代理地址 |
| download.proxy.username | string | "" | 代理认证用户名 |
| download.proxy.password | string | "" | 代理认证密码 |
| gallery.columns | int | 4 | 图库默认列数 |
| gallery.page_size | int | 20 | 每页图片数量 |
| query.timeout | int | 30 | 查询超时时间（秒） |

### 6.2 配置文件格式
```json
{
  "server": {
    "host": "127.0.0.1",
    "port": 8000
  },
  "database": {
    "type": "sqlite",
    "path": "data.db",
    "mariadb": {
      "host": "127.0.0.1",
      "port": 3306,
      "user": "",
      "password": "",
      "database": "yande_spider"
    }
  },
  "download": {
    "thread_num": 4,
    "chunk_size": 10240,
    "split_size": 5242880,
    "duplicate_check": true,
    "save_to_db": true,
    "default_save_path": "./downloads",
    "proxy": {
      "enabled": false,
      "http": "",
      "https": "",
      "username": "",
      "password": ""
    }
  },
  "gallery": {
    "columns": 4,
    "page_size": 20,
    "lazy_load": true
  },
  "query": {
    "timeout": 30,
    "retry": 3,
    "cache_enabled": true
  }
}
```

## 7. 安全设计

### 7.1 认证授权
- 本地服务无需认证，仅监听localhost
- 未来可扩展支持API Token认证

### 7.2 数据安全
- 敏感配置（数据库密码）加密存储
- 下载文件进行MD5校验
- SQL注入防护（使用ORM）

### 7.3 接口安全
- 参数验证（Pydantic）
- 请求频率限制
- CORS配置（仅允许localhost）

## 8. 性能设计

### 8.1 性能指标
| 指标名称 | 目标值 | 测量方法 |
|---------|--------|---------|
| 界面首次加载时间 | < 3秒 | 浏览器Performance API |
| 图片缩略图加载时间 | < 1秒 | 网络请求时间 |
| 查询响应时间 | < 2秒 | API响应时间 |
| 并发下载任务数 | >= 100 | 压力测试 |
| 内存占用 | < 500MB | 进程监控 |
| 图库展示图片数 | >= 10000 | 滚动性能测试 |

### 8.2 优化策略
- **前端优化**：
  - 图片懒加载和虚拟滚动
  - 组件按需加载
  - 图片缩略图使用WebP格式
  - 使用CDN缓存静态资源

- **后端优化**：
  - 异步IO处理请求
  - 查询结果缓存
  - 数据库连接池
  - 批量数据库操作

- **下载优化**：
  - 多线程分块下载
  - 断点续传支持
  - 并发下载控制

## 9. 异常处理

### 9.1 异常分类
| 异常类型 | 处理策略 | 用户提示 |
|---------|---------|---------|
| 网络连接失败 | 重试3次，指数退避 | "网络连接失败，正在重试..." |
| API请求超时 | 重试3次 | "请求超时，请检查网络连接" |
| 数据库连接失败 | 降级到SQLite | "数据库连接失败，使用本地存储" |
| 文件写入失败 | 记录错误，继续下载 | "文件保存失败，请检查磁盘空间" |
| 参数验证失败 | 返回错误详情 | "查询参数无效：{具体错误}" |
| 重复图片检测 | 跳过下载 | "检测到重复图片，已跳过" |

### 9.2 错误码定义
| 错误码 | 含义 | 处理建议 |
|-------|------|---------|
| 1001 | 查询参数无效 | 检查参数格式和范围 |
| 1002 | API请求失败 | 检查网络连接和API状态 |
| 2001 | 下载任务不存在 | 检查任务ID是否正确 |
| 2002 | 下载任务已存在 | 使用不同查询条件创建任务 |
| 3001 | 数据库连接失败 | 检查数据库配置 |
| 3002 | 数据写入失败 | 检查磁盘空间和权限 |
| 4001 | 文件已存在 | 启用重复检测跳过 |
| 4002 | MD5校验失败 | 重新下载文件 |

## 10. 部署设计

### 10.1 部署架构
```
┌─────────────────────────────────────┐
│         用户环境                     │
├─────────────────────────────────────┤
│  ┌───────────────────────────────┐  │
│  │  Electron桌面客户端            │  │
│  │  (打包的Web界面 + Python后端)  │  │
│  └───────────────────────────────┘  │
│                或                    │
│  ┌───────────────────────────────┐  │
│  │  浏览器访问                    │  │
│  │  (Web界面)                     │  │
│  └───────────────────────────────┘  │
│           ↓ HTTP                    │
│  ┌───────────────────────────────┐  │
│  │  FastAPI后端服务               │  │
│  │  (Python 3.12+)               │  │
│  └───────────────────────────────┘  │
│           ↓                         │
│  ┌───────────────────────────────┐  │
│  │  数据库 (SQLite/MariaDB)       │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### 10.2 环境要求
- **Python环境**：Python 3.12及以上版本
- **Node.js环境**：Node.js 16及以上版本（用于前端构建）
- **操作系统**：Windows 10+、macOS 10.15+、Linux
- **数据库**：MariaDB 10.5+ 或 SQLite 3.35+
- **磁盘空间**：至少1GB可用空间

### 10.3 部署步骤
1. **安装Python依赖**：
   ```bash
   pip install -r requirements.txt
   ```

2. **安装前端依赖并构建**：
   ```bash
   cd frontend
   npm install
   npm run build
   ```

3. **配置数据库**：
   - 编辑config/data.cfg，设置数据库连接信息
   - 运行数据库初始化脚本

4. **启动后端服务**：
   ```bash
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

5. **访问界面**：
   - Web界面：http://localhost:8000
   - 桌面客户端：运行Electron应用

## 11. 测试设计

### 11.1 测试策略
- **单元测试**：覆盖核心业务逻辑（查询、下载、重复检测）
- **集成测试**：测试模块间交互（API调用、数据库操作）
- **端到端测试**：测试完整用户流程（查询→下载→持久化）
- **性能测试**：测试并发下载、大量图片展示性能

### 11.2 测试用例
| 用例编号 | 测试场景 | 预期结果 |
|---------|---------|---------|
| TC001 | 创建查询条件并执行查询 | 返回符合条件的结果 |
| TC002 | 使用相同查询条件创建下载任务 | 任务查询条件与界面一致 |
| TC003 | 下载已存在的图片（重复检测开启） | 跳过下载，记录跳过数量 |
| TC004 | 下载成功后检查数据库记录 | 图片信息完整保存到数据库 |
| TC005 | 暂停并恢复下载任务 | 任务状态正确切换，进度保持 |
| TC006 | 批量下载100张图片 | 所有图片下载成功，无重复 |
| TC007 | 图库瀑布流滚动加载1000张图片 | 流畅滚动，无卡顿 |
| TC008 | 配置修改并保存 | 配置立即生效或提示重启 |

## 12. 扩展性设计

### 12.1 扩展点
- **查询条件扩展**：支持添加新的查询条件类型
- **存储后端扩展**：支持添加新的存储后端（如S3）
- **界面主题扩展**：支持自定义主题和样式
- **下载策略扩展**：支持自定义下载策略

### 12.2 插件机制
- 使用Python的插件架构（如pluggy）
- 定义标准插件接口
- 支持动态加载和卸载插件
- 提供插件配置界面
