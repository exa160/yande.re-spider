"""
标签缓存相关响应模型
"""

from typing import Optional, List

from pydantic import BaseModel


class TagInfo(BaseModel):
    """标签信息"""

    id: int
    name: str
    count: int
    type: int
    ambiguous: bool


class ArtistInfo(BaseModel):
    """艺术家信息"""

    id: int
    name: str
    alias_id: Optional[int]
    group_id: Optional[int]
    urls: List[str]
