"""
扩展数据库模型
支持下载任务管理、查询预设、下载历史记录等功能
"""
from datetime import datetime
from enum import Enum
from typing import Optional, List
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Float, Text, JSON, Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase
from utils.items import Rating


class Base(DeclarativeBase):
    """SQLAlchemy 基类"""
    pass


class TaskStatus(str, Enum):
    """下载任务状态枚举"""
    PENDING = "pending"  # 等待中
    DOWNLOADING = "downloading"  # 下载中
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"  # 失败
    CANCELLED = "cancelled"  # 已取消


class DownloadTask(Base):
    """下载任务表"""
    __tablename__ = "download_tasks"

    task_id = Column(String(36), primary_key=True, comment='任务唯一标识UUID')
    image_id = Column(Integer, nullable=False, comment='图片ID')
    file_url = Column(String(918), nullable=False, comment='下载URL')
    save_path = Column(String(512), nullable=False, comment='保存路径')
    file_name = Column(String(256), nullable=False, comment='文件名')
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING, comment='任务状态')
    progress = Column(Float, default=0.0, comment='下载进度0.0-1.0')
    downloaded_size = Column(Integer, default=0, comment='已下载大小(KB)')
    total_size = Column(Integer, nullable=True, comment='总大小(KB)')
    thread_num = Column(Integer, default=4, comment='线程数')
    retry_count = Column(Integer, default=0, comment='重试次数')
    error_message = Column(Text, nullable=True, comment='错误信息')
    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    started_at = Column(DateTime, nullable=True, comment='开始时间')
    completed_at = Column(DateTime, nullable=True, comment='完成时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')

    # 图片元数据
    tags = Column(String(918), nullable=True, comment='标签')
    width = Column(Integer, nullable=True, comment='宽度')
    height = Column(Integer, nullable=True, comment='高度')
    rating = Column(SQLEnum(Rating), nullable=True, comment='评分')
    author = Column(String(32), nullable=True, comment='作者')
    md5 = Column(String(32), nullable=True, comment='MD5')


class DownloadHistory(Base):
    """下载历史记录表"""
    __tablename__ = "download_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, nullable=False, comment='图片ID')
    file_path = Column(String(512), nullable=False, comment='文件路径')
    file_name = Column(String(256), nullable=False, comment='文件名')
    file_size = Column(Integer, nullable=True, comment='文件大小(KB)')
    download_time = Column(Integer, nullable=True, comment='下载耗时(秒)')
    success = Column(Boolean, default=True, comment='是否成功')
    error_message = Column(Text, nullable=True, comment='错误信息')
    created_at = Column(DateTime, default=datetime.now, comment='下载时间')

    # 图片元数据
    tags = Column(String(918), nullable=True, comment='标签')
    width = Column(Integer, nullable=True, comment='宽度')
    height = Column(Integer, nullable=True, comment='高度')
    rating = Column(SQLEnum(Rating), nullable=True, comment='评分')
    author = Column(String(32), nullable=True, comment='作者')
    md5 = Column(String(32), nullable=True, comment='MD5')


class QueryPreset(Base):
    """查询条件预设表"""
    __tablename__ = "query_presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(128), nullable=False, comment='预设名称')
    description = Column(Text, nullable=True, comment='预设描述')

    # 查询条件（JSON格式存储）
    tags = Column(String(918), nullable=True, comment='标签表达式')
    min_width = Column(Integer, nullable=True, comment='最小宽度')
    max_width = Column(Integer, nullable=True, comment='最大宽度')
    min_height = Column(Integer, nullable=True, comment='最小高度')
    max_height = Column(Integer, nullable=True, comment='最大高度')
    rating = Column(String(32), nullable=True, comment='评分过滤')
    min_file_size = Column(Integer, nullable=True, comment='最小文件大小(KB)')
    max_file_size = Column(Integer, nullable=True, comment='最大文件大小(KB)')
    file_type = Column(String(16), nullable=True, comment='文件类型')
    author = Column(String(128), nullable=True, comment='作者')
    sort_by = Column(String(32), nullable=True, comment='排序字段')
    sort_order = Column(String(8), nullable=True, comment='排序方向')

    created_at = Column(DateTime, default=datetime.now, comment='创建时间')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
    is_favorite = Column(Boolean, default=False, comment='是否收藏')


class SystemConfig(Base):
    """系统配置表（用于存储动态配置）"""
    __tablename__ = "system_config"

    key = Column(String(128), primary_key=True, comment='配置键')
    value = Column(Text, nullable=True, comment='配置值(JSON格式)')
    description = Column(String(512), nullable=True, comment='配置描述')
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment='更新时间')
