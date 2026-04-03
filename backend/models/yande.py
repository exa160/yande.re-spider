from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, RootModel


class SearchRating(Enum):
    S = "safe"
    R15 = "questionable"
    R18 = "explicit"


class Rating(Enum):
    S = "s"
    R15 = "q"
    R18 = "e"


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


class YandeSearchTags(BaseModel):
    """Yande.re 高级搜索标签转换模型"""

    min_width: Optional[int] = None
    max_width: Optional[int] = None
    min_height: Optional[int] = None
    max_height: Optional[int] = None
    min_score: Optional[int] = None
    max_score: Optional[int] = None
    min_filesize: Optional[int] = None
    max_filesize: Optional[int] = None
    ratings: List[str] = []
    file_exts: List[str] = []
    order: str = "date"


class YandeRunningConfig(BaseModel):
    save_dir_path: Optional[str] = None
    start_page: int = 0
    end_page: int = 0
    stop_id: int = 0
    tags: str = ""
    add_flag: bool = False
    id_check: bool = True
    id_check_list: set = None


class YandeFilterTags(BaseModel):
    pass
