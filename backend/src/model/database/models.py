"""
数据库模型定义（使用 SQLModel）

基于 FastAPI 官方 SQLModel 规范：
https://fastapi.tiangolo.com/zh/tutorial/sql-databases/
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlmodel import SQLModel, Field


class RatingEnum(str, Enum):
    SAFE = "s"
    QUESTIONABLE = "q"
    EXPLICIT = "e"


class TagTypeEnum(int, Enum):
    GENERAL = 0
    ARTIST = 1
    CHARACTER = 2
    COPYRIGHT = 3
    META = 4


class YandeTag(SQLModel, table=True):
    __tablename__ = "yande_tags"
    __table_args__ = {"extend_existing": True}

    id: int = Field(primary_key=True)
    name: str = Field(unique=True, max_length=512)
    count: int = Field(default=0)
    type: int = Field(default=0)
    ambiguous: bool = Field(default=False)
    updated_at: Optional[datetime] = Field(default=None)


class YandeArtist(SQLModel, table=True):
    __tablename__ = "yande_artists"
    __table_args__ = {"extend_existing": True}

    id: int = Field(primary_key=True)
    name: str = Field(unique=True, max_length=512)
    alias_id: Optional[int] = Field(default=None)
    group_id: Optional[int] = Field(default=None)
    urls: Optional[str] = Field(default=None)
    updated_at: Optional[datetime] = Field(default=None)


class YandeData(SQLModel, table=True):
    __tablename__ = "yande_data"
    __table_args__ = {"extend_existing": True}

    id: int = Field(primary_key=True)
    down_flag: bool = Field(default=True)
    tags: Optional[str] = Field(default=None, max_length=918)
    created_at: datetime
    updated_at: datetime
    creator_id: Optional[int] = Field(default=None)
    author: Optional[str] = Field(default=None, max_length=32)
    change: Optional[int] = Field(default=None)
    source: Optional[str] = Field(default=None, max_length=918)
    score: Optional[int] = Field(default=None)
    md5: Optional[str] = Field(default=None, max_length=32)
    file_size: Optional[int] = Field(default=None)
    file_ext: str = Field(max_length=6)
    file_url: Optional[str] = Field(default=None, max_length=918)
    is_shown_in_index: Optional[bool] = Field(default=None)
    preview_url: Optional[str] = Field(default=None, max_length=918)
    preview_width: Optional[int] = Field(default=None)
    preview_height: Optional[int] = Field(default=None)
    actual_preview_width: Optional[int] = Field(default=None)
    actual_preview_height: Optional[int] = Field(default=None)
    sample_url: Optional[str] = Field(default=None, max_length=918)
    sample_width: Optional[int] = Field(default=None)
    sample_height: Optional[int] = Field(default=None)
    sample_file_size: Optional[int] = Field(default=None)
    jpeg_url: Optional[str] = Field(default=None, max_length=918)
    jpeg_width: Optional[int] = Field(default=None)
    jpeg_height: Optional[int] = Field(default=None)
    jpeg_file_size: Optional[int] = Field(default=None)
    rating: str = Field(max_length=1)
    is_rating_locked: Optional[bool] = Field(default=None)
    has_children: Optional[bool] = Field(default=None)
    parent_id: Optional[int] = Field(default=None)
    status: Optional[str] = Field(default=None, max_length=16)
    is_pending: Optional[bool] = Field(default=None)
    width: int
    height: int
    is_held: Optional[bool] = Field(default=None)
    frames_pending_string: Optional[str] = Field(default=None, max_length=918)
    frames_pending: Optional[str] = Field(default=None)
    frames_string: Optional[str] = Field(default=None, max_length=918)
    frames: Optional[str] = Field(default=None)
    is_note_locked: Optional[bool] = Field(default=None)
    last_noted_at: Optional[int] = Field(default=None)
    last_commented_at: Optional[int] = Field(default=None)


class FavoriteFolder(SQLModel, table=True):
    __tablename__ = "favorite_folders"
    __table_args__ = {"extend_existing": True}

    id: int = Field(default=None, primary_key=True)
    name: str
    tags: str = ""
    color: str = "#409EFF"
    icon: str = "folder"
    sort_order: int = 0
    local_count: int = 0
    online_count: int = 0
    last_refresh: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


__all__ = [
    "YandeTag",
    "YandeArtist",
    "YandeData",
    "FavoriteFolder",
    "RatingEnum",
    "TagTypeEnum",
]
