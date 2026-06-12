"""
yande.re API 原始响应模型

对应 yande.re 站点返回的 JSON 结构（posts、tags 接口），
是 infrastructure 层解析外部 API 的数据契约。
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, RootModel

from src.common.constant import Rating


class YandePostData(RootModel):
    """
    yande.re接口获取的list json内容
    """

    class YandePostItem(BaseModel):
        id: int
        tags: str
        created_at: datetime
        updated_at: datetime
        creator_id: Optional[int] = None
        author: str
        change: int
        source: str
        score: int
        md5: str
        file_size: int
        file_ext: str
        file_url: str
        is_shown_in_index: bool
        preview_url: str
        preview_width: int
        preview_height: int
        actual_preview_width: int
        actual_preview_height: int
        sample_url: str
        sample_width: int
        sample_height: int
        sample_file_size: int
        jpeg_url: str
        jpeg_width: int
        jpeg_height: int
        jpeg_file_size: int
        rating: Rating
        is_rating_locked: bool
        has_children: bool
        parent_id: Optional[int]
        status: str
        is_pending: bool
        width: int
        height: int
        is_held: bool
        frames_pending_string: Optional[str]
        frames_pending: Optional[List[dict]]
        frames_string: Optional[str]
        frames: Optional[List[dict]]
        is_note_locked: bool
        last_noted_at: int
        last_commented_at: int

    root: List[YandePostItem]


class YandeTagData(RootModel):
    """
    yande.re接口获取的tag json内容
    """

    class YandeTagItem(BaseModel):
        id: int

    root: List[YandeTagItem]
