from sqlalchemy import Column, Integer, Boolean, Text, DateTime, String, Enum, JSON
from sqlalchemy.orm import DeclarativeBase

from src.models.yande import Rating


class Base(DeclarativeBase):
    pass


class YandeData(Base):
    __tablename__ = "yande_data"
    """Yande.re 图片数据表"""
    id = Column(Integer, primary_key=True, comment="yande picture ID")
    down_flag = Column(Boolean, index=True, default=False, comment="yande picture down status")
    tags = Column(Text, comment="picture tag", nullable=True)
    source = Column(Text, comment="source url")
    created_at = Column(DateTime, comment="yande picture create time")
    updated_at = Column(DateTime, comment="yande picture update time")
    creator_id = Column(Integer, comment="yande picture update author ID")
    author = Column(String(32), nullable=True, comment="yande picture update author name")
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
    rating = Column(Enum(Rating), index=True, comment="图片评级")
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

    __tablename__ = "yande_tags"

    id = Column(Integer, primary_key=True, comment="标签ID")
    name = Column(String(512), unique=True, nullable=False, comment="标签名称")
    count = Column(Integer, default=0, comment="使用数量")
    type = Column(
        Integer,
        default=0,
        comment="类型: 0=general, 1=artist, 2=character, 3=copyright, 4=meta",
    )
    ambiguous = Column(Boolean, default=False, comment="是否模糊")
    updated_at = Column(DateTime, nullable=True, comment="最后更新时间")


class YandeArtist(Base):
    """Yande.re 艺术家缓存表"""

    __tablename__ = "yande_artists"

    id = Column(Integer, primary_key=True, comment="艺术家ID")
    name = Column(String(512), unique=True, nullable=False, comment="艺术家名称")
    alias_id = Column(Integer, nullable=True, comment="别名ID")
    group_id = Column(Integer, nullable=True, comment="组ID")
    urls = Column(Text, nullable=True, comment="相关链接 (JSON)")
    updated_at = Column(DateTime, nullable=True, comment="最后更新时间")


class TagLocalStats(Base):
    """本地标签统计表 - 记录每个标签在本地图片中的使用次数"""

    __tablename__ = "tag_local_stats"

    tag_id = Column(Integer, primary_key=True, comment="标签ID")
    local_count = Column(Integer, default=0, comment="本地使用次数")
    last_calculated = Column(DateTime, nullable=True, comment="最后计算时间")
