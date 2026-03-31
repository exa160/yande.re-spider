# YandeData 处理说明

## 概述
本文档说明如何在新的系统设计中重构 `YandeData` 数据库模型。

**核心原则**：
1. **保持数据结构一致**：YandeData 的字段定义保持不变，确保存储完整的 API 数据
2. **重构实现方式**：可以重新设计实现方式，优化代码结构
3. **确保数据完整**：必须完整保存 yande.re API 返回的所有数据（30+字段）

## 重构策略

### 方案选择：重构而非复用

**原因**：
- 新系统使用 FastAPI + SQLAlchemy，架构更清晰
- 可以优化数据库连接管理
- 支持异步操作
- 更好的依赖注入和测试支持

**保持不变的部分**：
- YandeData 的字段定义（30+个字段完全一致）
- 数据库表结构（确保现有数据兼容）
- 数据完整性要求（所有字段必须保存）

**重构的部分**：
- 数据库连接管理（使用SQLAlchemy统一管理）
- 数据访问层（重新设计，支持异步）
- 服务层（使用依赖注入）

## 现有 YandeData 模型

### 位置
- 文件路径：`utils/database.py`
- 类名：`MariaDBClient.YandeData`

### 数据来源
- **来源**：yande.re API 的 `/post.json` 接口查询结果
- **内容**：完整的图片元数据，包含30+个字段
- **重要性**：这些数据是图片的完整信息记录，一旦丢失无法恢复

### 新的模型定义（重构后）
```python
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum, JSON
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime
from typing import Optional, List
from enum import Enum as PyEnum

class Base(DeclarativeBase):
    """SQLAlchemy基类"""
    pass

class Rating(PyEnum):
    """内容评级枚举"""
    SAFE = 's'
    QUESTIONABLE = 'q'
    EXPLICIT = 'e'

class YandeData(Base):
    """
    yande.re API post 数据的完整存储模型（重构版）

    数据结构：与原模型完全一致
    实现方式：使用SQLAlchemy统一管理
    """
    __tablename__ = 'yande_re'

    # ========== 基础标识信息 ==========
    id = Column(Integer, unique=True, primary_key=True, comment='yande图片ID')
    down_flag = Column(Boolean, default=True, primary_key=True, comment='下载状态')

    # ========== 图片元数据（来自API） ==========
    tags = Column(String(918), nullable=True, comment='所有标签')
    created_at = Column(DateTime, primary_key=True, comment='图片创建时间')
    updated_at = Column(DateTime, primary_key=True, comment='图片更新时间')
    creator_id = Column(Integer, nullable=True, comment='创建者ID')
    author = Column(String(32), nullable=True, comment='作者名称')
    change = Column(Integer, nullable=True, comment='变更ID')
    source = Column(String(918), comment='来源URL')
    score = Column(Integer, nullable=True, comment='评分')

    # ========== 文件信息 ==========
    md5 = Column(String(32), comment='文件MD5校验值')
    file_size = Column(Integer, comment='文件大小（字节）')
    file_ext = Column(String(6), primary_key=True, comment='文件扩展名')
    file_url = Column(String(918), comment='文件下载URL')

    # ========== 预览图信息 ==========
    is_shown_in_index = Column(Boolean, comment='是否在索引中显示')
    preview_url = Column(String(918), comment='预览图URL')
    preview_width = Column(Integer, comment='预览图宽度')
    preview_height = Column(Integer, comment='预览图高度')
    actual_preview_width = Column(Integer, comment='实际预览宽度')
    actual_preview_height = Column(Integer, comment='实际预览高度')

    # ========== 样本图信息 ==========
    sample_url = Column(String(918), comment='样本图URL')
    sample_width = Column(Integer, comment='样本图宽度')
    sample_height = Column(Integer, comment='样本图高度')
    sample_file_size = Column(Integer, comment='样本图大小')

    # ========== JPEG信息 ==========
    jpeg_url = Column(String(918), comment='JPEG版本URL')
    jpeg_width = Column(Integer, comment='JPEG宽度')
    jpeg_height = Column(Integer, comment='JPEG高度')
    jpeg_file_size = Column(Integer, comment='JPEG大小')

    # ========== 评级和状态 ==========
    rating = Column(Enum(Rating, values_callable=lambda x: [e.value for e in x]),
                   primary_key=True, comment='内容评级')
    is_rating_locked = Column(Boolean, comment='评级是否锁定')
    has_children = Column(Boolean, comment='是否有子图')
    parent_id = Column(Integer, nullable=True, comment='父图ID')
    status = Column(String(16), comment='状态')
    is_pending = Column(Boolean, comment='是否待处理')

    # ========== 尺寸信息 ==========
    width = Column(Integer, primary_key=True, comment='原图宽度')
    height = Column(Integer, primary_key=True, comment='原图高度')

    # ========== 其他信息 ==========
    is_held = Column(Boolean, comment='是否保留')
    frames_pending_string = Column(String(918), nullable=True, comment='待处理帧字符串')
    frames_pending = Column(JSON, comment='待处理帧')
    frames_string = Column(String(918), nullable=True, comment='帧字符串')
    frames = Column(JSON, comment='帧信息')
    is_note_locked = Column(Boolean, comment='注释是否锁定')
    last_noted_at = Column(Integer, comment='最后注释时间')
    last_commented_at = Column(Integer, comment='最后评论时间')

    def __repr__(self):
        return f"<YandeData(id={self.id}, author='{self.author}', score={self.score})>"
```

**说明**：
- 字段定义与原模型完全一致（30+个字段）
- 表名保持 `yande_re`，确保现有数据兼容
- 使用SQLAlchemy的DeclarativeBase
- 添加了详细的注释说明每个字段的含义

### 现有方法
```python
class MariaDBClient:
    def insert_check_by_id(self, _id):
        """检查图片ID是否已存在"""
        q = self.session.query(self.YandeData).filter_by(id=_id).one_or_none()
        return q is None
    
    def insert_by_id(self, _id, sql_data: YandeData):
        """插入图片数据（自动去重）"""
        if self.insert_check_by_id(_id):
            self.insert_data(sql_data)
```

## 重构实现

### 1. 数据库连接管理（重构）

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator

class DatabaseManager:
    """
    数据库管理器（重构版）

    支持：
    - MariaDB/MySQL
    - SQLite
    - 连接池管理
    - 会话管理
    """

    def __init__(self, database_url: str):
        """
        初始化数据库管理器

        Args:
            database_url: 数据库连接URL
                - MariaDB: mariadb+mariadbconnector://user:pass@host:port/db
                - SQLite: sqlite:///path/to/database.db
        """
        self.engine = create_engine(
            database_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )

        # 创建所有表
        Base.metadata.create_all(bind=self.engine)

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """
        获取数据库会话（上下文管理器）

        使用方式：
        with db_manager.get_session() as session:
            # 数据库操作
            pass
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    async def get_async_session(self):
        """获取异步会话（用于FastAPI）"""
        # 使用SQLAlchemy 2.0的异步支持
        pass
```

### 2. 数据访问层（重构）

```python
from typing import Optional, List
from loguru import logger

class YandeDataRepository:
    """
    YandeData数据访问层（重构版）

    职责：
    - 图片数据的CRUD操作
    - 重复检测
    - 数据查询
    """

    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def save(self, yande_data: YandeData) -> bool:
        """
        保存图片数据（完整保存所有字段）

        Args:
            yande_data: YandeData实例，包含完整的API数据

        Returns:
            bool: 保存成功返回True
        """
        with self.db_manager.get_session() as session:
            try:
                # 检查是否已存在
                existing = session.query(YandeData).filter_by(
                    id=yande_data.id,
                    file_ext=yande_data.file_ext,
                    rating=yande_data.rating
                ).first()

                if existing:
                    logger.info(f"图片已存在，跳过保存: ID={yande_data.id}")
                    return True

                # 保存新数据
                session.add(yande_data)
                logger.success(
                    f"保存图片数据成功: "
                    f"ID={yande_data.id}, "
                    f"作者={yande_data.author}, "
                    f"评分={yande_data.score}"
                )
                return True

            except Exception as e:
                logger.error(f"保存图片数据失败: {e}")
                return False

    def exists(self, image_id: int) -> bool:
        """
        检查图片是否已存在

        Args:
            image_id: 图片ID

        Returns:
            bool: 存在返回True
        """
        with self.db_manager.get_session() as session:
            count = session.query(YandeData).filter_by(id=image_id).count()
            return count > 0

    def get_by_id(self, image_id: int) -> Optional[YandeData]:
        """
        根据ID获取图片数据

        Args:
            image_id: 图片ID

        Returns:
            Optional[YandeData]: 图片数据或None
        """
        with self.db_manager.get_session() as session:
            return session.query(YandeData).filter_by(id=image_id).first()

    def get_by_tags(self, tags: str, limit: int = 100) -> List[YandeData]:
        """
        根据标签查询图片

        Args:
            tags: 标签字符串
            limit: 返回数量限制

        Returns:
            List[YandeData]: 图片列表
        """
        with self.db_manager.get_session() as session:
            return session.query(YandeData).filter(
                YandeData.tags.contains(tags)
            ).limit(limit).all()

    def count(self) -> int:
        """获取图片总数"""
        with self.db_manager.get_session() as session:
            return session.query(YandeData).count()
```

### 3. 数据持久化服务（重构）

```python
from utils.items import YandePostItem

class DataPersistenceService:
    """
    数据持久化服务（重构版）

    核心职责：确保yande.re API返回的完整数据被妥善保存到数据库
    """

    def __init__(self, repository: YandeDataRepository):
        self.repository = repository

    async def save_image_record(
        self,
        image_data: YandePostItem,
        local_path: str
    ) -> bool:
        """
        保存图片记录到数据库

        重要说明：
        1. image_data包含yande.re API返回的完整数据（30+字段）
        2. 必须确保所有字段都被保存，不丢失任何信息
        3. 自动去重，避免重复存储

        Args:
            image_data: YandePostItem，包含API返回的完整数据
            local_path: str，本地文件保存路径

        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            # 1. 数据完整性验证
            if not self._validate_data(image_data):
                logger.error(f"数据完整性验证失败: ID={image_data.id}")
                return False

            # 2. 将Pydantic模型转换为字典（确保所有字段都包含）
            data_dict = image_data.model_dump()

            # 3. 创建YandeData实例，包含所有API返回的字段
            yande_data = YandeData(**data_dict)

            # 4. 保存到数据库（自动去重）
            success = self.repository.save(yande_data)

            if success:
                logger.success(
                    f"保存图片数据成功: "
                    f"ID={image_data.id}, "
                    f"作者={image_data.author}, "
                    f"评分={image_data.score}, "
                    f"尺寸={image_data.width}x{image_data.height}, "
                    f"大小={image_data.file_size/1024/1024:.2f}MB"
                )

            return success

        except Exception as e:
            logger.error(f"保存图片记录失败: {e}")
            logger.error(f"图片ID: {image_data.id}")
            logger.error(f"图片数据: {image_data.model_dump_json(indent=2)}")
            return False

    def _validate_data(self, image_data: YandePostItem) -> bool:
        """
        验证图片数据完整性

        确保API返回的关键字段都存在且有效
        """
        required_fields = [
            'id', 'file_url', 'md5', 'file_size',
            'width', 'height', 'file_ext', 'tags',
            'score', 'author', 'rating'
        ]

        for field in required_fields:
            value = getattr(image_data, field, None)
            if value is None:
                logger.warning(f"图片数据缺少必要字段: {field}, ID={image_data.id}")
                return False

        # 验证数值字段的有效性
        if image_data.file_size <= 0:
            logger.warning(f"文件大小无效: {image_data.file_size}, ID={image_data.id}")
            return False

        if image_data.width <= 0 or image_data.height <= 0:
            logger.warning(f"图片尺寸无效: {image_data.width}x{image_data.height}, ID={image_data.id}")
            return False

        return True

    async def check_exists(self, image_id: int) -> bool:
        """检查图片是否已存在数据库"""
        return self.repository.exists(image_id)

    async def get_image_by_id(self, image_id: int) -> Optional[YandeData]:
        """从数据库获取图片完整信息"""
        return self.repository.get_by_id(image_id)
```

### 3. 扩展新功能
在保持现有模型的基础上，添加新的模型和功能：

#### 新增模型
```python
# 下载任务模型
class DownloadTask(Base):
    __tablename__ = 'download_tasks'
    task_id = Column(String(36), primary_key=True)
    query_params = Column(JSON)
    # ...

# 下载历史模型
class DownloadHistory(Base):
    __tablename__ = 'download_history'
    id = Column(Integer, primary_key=True)
    task_id = Column(String(36))
    image_id = Column(Integer)  # 关联到YandeData.id
    # ...

# 查询预设模型
class QueryPreset(Base):
    __tablename__ = 'query_presets'
    id = Column(Integer, primary_key=True)
    name = Column(String(128))
    params = Column(JSON)
    # ...
```

#### 数据关系
```
YandeData (现有)
    ↑
    │ (通过image_id关联)
    │
DownloadHistory (新增)
    ↓
DownloadTask (新增)
```

## 实现指南

### 1. 数据持久化服务
```python
class DataPersistenceService:
    """
    数据持久化服务
    
    核心职责：确保yande.re API返回的完整数据被妥善保存到数据库
    """
    
    def __init__(self, db_client: MariaDBClient = None):
        """初始化服务，复用现有的MariaDBClient"""
        self.db_client = db_client or MariaDBClient()
    
    async def save_image_record(
        self, 
        image_data: YandePostItem, 
        local_path: str
    ) -> bool:
        """
        保存图片记录到数据库
        
        重要说明：
        1. image_data包含yande.re API返回的完整数据（30+字段）
        2. 必须确保所有字段都被保存，不丢失任何信息
        3. 使用现有的YandeData模型和insert_by_id方法
        4. 自动去重，避免重复存储
        
        参数：
        - image_data: YandePostItem，包含API返回的完整数据
        - local_path: str，本地文件保存路径
        
        返回：
        - bool: 保存成功返回True，失败返回False
        """
        try:
            # 1. 数据完整性验证
            if not self._validate_data(image_data):
                logger.error(f"数据完整性验证失败: ID={image_data.id}")
                return False
            
            # 2. 将Pydantic模型转换为字典（确保所有字段都包含）
            data_dict = image_data.model_dump()
            
            # 3. 创建YandeData实例，包含所有API返回的字段
            yande_data = MariaDBClient.YandeData(**data_dict)
            
            # 4. 使用现有的insert_by_id方法保存（自动去重）
            self.db_client.insert_by_id(image_data.id, yande_data)
            
            # 5. 记录成功日志
            logger.success(
                f"保存图片数据成功: "
                f"ID={image_data.id}, "
                f"作者={image_data.author}, "
                f"评分={image_data.score}, "
                f"尺寸={image_data.width}x{image_data.height}, "
                f"大小={image_data.file_size/1024/1024:.2f}MB"
            )
            return True
            
        except Exception as e:
            logger.error(f"保存图片记录失败: {e}")
            logger.error(f"图片ID: {image_data.id}")
            logger.error(f"图片数据: {image_data.model_dump_json(indent=2)}")
            return False
    
    def _validate_data(self, image_data: YandePostItem) -> bool:
        """
        验证图片数据完整性
        
        确保API返回的关键字段都存在且有效
        """
        # 必须存在的字段列表
        required_fields = [
            'id',           # 图片唯一标识
            'file_url',     # 下载地址
            'md5',          # 文件校验值
            'file_size',    # 文件大小
            'width',        # 图片宽度
            'height',       # 图片高度
            'file_ext',     # 文件扩展名
            'tags',         # 标签信息
            'score',        # 评分
            'author',       # 作者
            'rating',       # 评级
        ]
        
        for field in required_fields:
            value = getattr(image_data, field, None)
            if value is None:
                logger.warning(f"图片数据缺少必要字段: {field}, ID={image_data.id}")
                return False
        
        # 验证数值字段的有效性
        if image_data.file_size <= 0:
            logger.warning(f"文件大小无效: {image_data.file_size}, ID={image_data.id}")
            return False
        
        if image_data.width <= 0 or image_data.height <= 0:
            logger.warning(f"图片尺寸无效: {image_data.width}x{image_data.height}, ID={image_data.id}")
            return False
        
        return True
    
    async def check_exists(self, image_id: int) -> bool:
        """
        检查图片是否已存在数据库
        复用现有的insert_check_by_id方法
        """
        return not self.db_client.insert_check_by_id(image_id)
    
    async def get_image_by_id(self, image_id: int) -> Optional[YandeData]:
        """
        从数据库获取图片完整信息
        用于查询已保存的图片元数据
        """
        try:
            return self.db_client.session.query(
                MariaDBClient.YandeData
            ).filter_by(id=image_id).one_or_none()
        except Exception as e:
            logger.error(f"查询图片数据失败: ID={image_id}, 错误={e}")
            return None
```

### 2. 重复检测器
```python
class DuplicateDetector:
    """重复检测器"""
    
    def __init__(self, db_client: MariaDBClient = None):
        self.db_client = db_client or MariaDBClient()
    
    def check_by_id(self, image_id: int) -> bool:
        """
        通过ID检查是否已存在
        复用现有的insert_check_by_id方法
        """
        return not self.db_client.insert_check_by_id(image_id)
    
    def check_by_path(self, file_path: str) -> bool:
        """通过文件路径检查是否已存在"""
        return os.path.exists(file_path)
    
    def check_by_md5(self, md5: str, file_path: str) -> bool:
        """通过MD5校验文件完整性"""
        if not os.path.exists(file_path):
            return False
        with open(file_path, 'rb') as f:
            file_md5 = hashlib.md5(f.read()).hexdigest()
        return file_md5 == md5
```

### 3. 下载管理服务
```python
class DownloadManagerService:
    """下载管理服务"""
    
    def __init__(self):
        self.db_client = MariaDBClient()  # 复用现有客户端
        self.detector = DuplicateDetector(self.db_client)
        self.persistence = DataPersistenceService(self.db_client)
    
    async def download_image(self, image_data: YandePostItem, save_path: str):
        """下载单张图片"""
        # 1. 重复检测
        if self.detector.check_by_id(image_data.id):
            logger.info(f"图片已存在，跳过: {image_data.id}")
            return "skipped"
        
        # 2. 执行下载
        # ... 下载逻辑
        
        # 3. 数据持久化（使用现有的YandeData模型）
        await self.persistence.save_image_record(image_data, save_path)
        
        return "success"
```

## 数据库兼容性

### MariaDB 配置
```python
# 现有配置（保持不变）
engine = create_engine(
    'mariadb+mariadbconnector://'
    f'{config.database.user}:{config.database.password}@'
    f'{config.database.host}:{config.database.port}/'
    f'{config.database.schema_name}?charset=utf8'
)
```

### SQLite 配置（新增）
```python
# 新增SQLite支持（用于轻量级部署）
engine = create_engine(f'sqlite:///{config.database.path}')
```

### 数据库初始化
```python
def init_database():
    """初始化数据库"""
    # 创建现有表（YandeData）
    MariaDBClient.Base.metadata.create_all(bind=engine)
    
    # 创建新表（DownloadTask、DownloadHistory等）
    NewBase.metadata.create_all(bind=engine)
```

## 迁移注意事项

### 1. 数据迁移
- 现有的 `YandeData` 表和数据无需迁移
- 新表（DownloadTask等）将自动创建
- 确保新表的外键约束正确关联到 `YandeData.id`

### 2. 代码兼容性
- 保持 `utils/database.py` 不变
- 新代码通过依赖注入使用 `MariaDBClient`
- 避免直接修改现有代码

### 3. 测试策略
- 编写兼容性测试，确保新功能不影响现有功能
- 测试重复检测功能
- 测试数据持久化功能
- 测试数据库连接和查询性能

## 总结

**核心原则**：
1. **保持现有模型不变**：`YandeData` 模型和 `MariaDBClient` 方法完全复用
2. **向后兼容**：确保新系统不影响现有功能
3. **扩展而非修改**：通过添加新模型和功能来扩展系统
4. **依赖注入**：通过依赖注入使用现有的数据库客户端

**优势**：
- 降低迁移风险
- 保持系统稳定性
- 减少开发工作量
- 确保数据一致性
