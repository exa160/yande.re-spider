from datetime import datetime
from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, RootModel


class SearchRating(Enum):
    S = 'safe'
    R15 = 'questionable'
    R18 = 'explicit'


class Rating(Enum):
    S = 's'
    R15 = 'q'
    R18 = 'e'


class IntegerInput(BaseModel):
    pass


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
        # 文件类型
        file_ext: str
        # 主下载连接
        file_url: str
        is_shown_in_index: bool
        # 预览图信息
        preview_url: str
        preview_width: int
        preview_height: int
        actual_preview_width: int
        actual_preview_height: int
        # 小图信息
        sample_url: str
        sample_width: int
        sample_height: int
        sample_file_size: int
        # jpg信息
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
    width: str = None
    rating: Rating = None


class YandeRunningConfig(BaseModel):
    save_dir_path: Optional[str] = None
    start_page: int = 0
    end_page: int = 0
    stop_id: int = 0
    tags: str = ''
    add_flag: bool = False  # 文件插入
    id_check: bool = True  # 检查文件夹内id是否重复
    id_check_list: set = None  # 检查文件夹内id是否重复


class YandeFilterTags(BaseModel):
    pass


class FileInfo(BaseModel):
    """
    下载文件的信息
    """
    id: Optional[int] = None
    file_path: str
    file_size: int
    md5: Optional[str] = None
    url: str


class IterStatus(Enum):
    next = 'continue'
    stop = 'stop'


if __name__ == '__main__':
    import json
    with open(r"C:\Share\a.json", 'rb') as f:
        # print(json.loads(f.read())[0]['frames'])
        for i in YandePostData.model_validate_json(f.read()).root:
            print(i.frames)
            # break
