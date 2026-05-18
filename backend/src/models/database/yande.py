from datetime import datetime

from sqlalchemy import Column, Integer, Boolean, Text, DateTime, String, JSON
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import Enum

from src.common.constant import Rating, TaskStatus, table_constant


class Base(DeclarativeBase):
    pass


class YandeData(Base):
    __tablename__ = table_constant.yande_data
    """Yande.re 图片数据表"""
    id = Column(Integer, primary_key=True, comment="yande picture ID")
    down_flag = Column(Boolean, index=True, default=False, comment="yande picture down status")
    tags = Column(Text, comment="picture tag", nullable=True)
    source = Column(Text, comment="source url")
    created_at = Column(DateTime, comment="yande picture create time")
    updated_at = Column(DateTime, comment="yande picture update time")
    creator_id = Column(Integer, comment="yande picture update author ID")
    author = Column(String(32), nullable=True, comment="yande picture update author name")
    change = Column(Integer, nullable=True, comment='yande picture update author ID')
    score = Column(Integer, nullable=True, comment="yande picture score")
    md5 = Column(String(32), comment="yande picture md5")
    file_size = Column(Integer, comment="yande picture file size")
    file_ext = Column(String(6), comment="picture type")
    file_url = Column(Text, comment="down url")
    is_shown_in_index = Column(Boolean, comment="")
    preview_url = Column(Text, comment="preview url")
    preview_width = Column(Integer)
    preview_height = Column(Integer)
    actual_preview_width = Column(Integer)
    actual_preview_height = Column(Integer)
    sample_url = Column(Text, comment="sample url")
    sample_width = Column(Integer)
    sample_height = Column(Integer)
    sample_file_size = Column(Integer)
    jpeg_url = Column(Text, comment="jpeg url")
    jpeg_width = Column(Integer)
    jpeg_height = Column(Integer)
    jpeg_file_size = Column(Integer)
    rating = Column(Enum(Rating, values_callable=lambda x: [e.value for e in x]), index=True, comment="图片评级")
    is_rating_locked = Column(Boolean)
    has_children = Column(Boolean)
    parent_id = Column(Integer, nullable=True)
    status = Column(String(16))
    is_pending = Column(Boolean)
    width = Column(Integer)
    height = Column(Integer)
    is_held = Column(Boolean)
    frames_pending_string = Column(Text, nullable=True)
    frames_pending = Column(JSON)
    frames_string = Column(Text, nullable=True)
    frames = Column(JSON)
    is_note_locked = Column(Boolean)
    last_noted_at = Column(Integer)
    last_commented_at = Column(Integer)


class YandeTag(Base):
    """Yande.re 标签缓存表"""

    __tablename__ = table_constant.yande_tag

    id = Column(Integer, primary_key=True, comment="标签ID")
    name = Column(String(512), unique=True, nullable=False, comment="标签名称")
    count = Column(Integer, default=0, comment="使用数量")
    type = Column(
        Integer,
        default=0,
        comment="类型: 0=general, 1=artist, 3=copyright, 4=character",
    )
    ambiguous = Column(Boolean, default=False, comment="有争议")
    updated_at = Column(DateTime, nullable=True, comment="最后更新时间")


class YandeArtist(Base):
    """Yande.re 艺术家缓存表"""

    __tablename__ = table_constant.yande_artist

    id = Column(Integer, primary_key=True, comment="艺术家ID", autoincrement=False)
    name = Column(String(512), index=True, nullable=False, comment="艺术家名称")
    alias_id = Column(Integer, nullable=True, comment="别名ID")
    group_id = Column(Integer, nullable=True, comment="组ID")
    urls = Column(Text, nullable=True, comment="相关链接 (JSON)")
    updated_at = Column(DateTime, nullable=True, comment="最后更新时间")


class TagLocalStats(Base):
    """本地标签统计表 - 记录每个标签在本地图片中的使用次数"""

    __tablename__ = table_constant.tag_local_stats

    tag_id = Column(Integer, primary_key=True, comment="标签ID")
    local_count = Column(Integer, default=0, comment="本地使用次数")
    last_calculated = Column(DateTime, nullable=True, comment="最后计算时间")


class FavoriteFolder(Base):
    """收藏夹数据库模型"""

    __tablename__ = table_constant.favorite_folder

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, comment="收藏夹名称")
    tags = Column(Text, default="", comment="查询标签字符串")
    color = Column(String(10), default="#409EFF", comment="展示颜色")
    icon = Column(String(32), default="folder", comment="图标标识")
    sort_order = Column(Integer, default=0, comment="排序权重")
    local_count = Column(Integer, default=0, comment="本地图片数量")
    online_count = Column(Integer, default=0, comment="在线图片数量(缓存)")
    last_refresh = Column(DateTime, nullable=True, comment="最后刷新时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
    updated_at = Column(
        DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间"
    )


class DownloadTaskModel(Base):
    """下载任务持久化表"""

    __tablename__ = table_constant.download_task

    task_id = Column(String(36), primary_key=True, comment="任务ID")
    image_id = Column(Integer, index=True, comment="图片ID")
    file_name = Column(String(256), nullable=True, comment="文件名")
    file_size = Column(Integer, nullable=True, comment="总大小")
    status = Column(
        Enum(TaskStatus, values_callable=lambda x: [e.value for e in x]),
        index=True, default=TaskStatus.PENDING, comment="任务状态"
    )
    progress = Column(Integer, default=0, comment="进度(0-100)")
    downloaded_size = Column(Integer, default=0, comment="已下载大小")
    speed = Column(Integer, default=0, comment="下载速度")
    error_message = Column(Text, nullable=True, comment="错误信息")
    started_at = Column(DateTime, nullable=True, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    created_at = Column(DateTime, default=datetime.now, comment="创建时间")
