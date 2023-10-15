from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, RootModel


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
        creator_id: int
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
        jpeg_width:  int
        jpeg_height:  int
        jpeg_file_size:  int
        rating: str
        is_rating_locked: bool
        has_children: bool
        parent_id: Optional[int]
        status: str
        is_pending: bool
        width: int
        height: int
        is_held: bool
        frames_pending_string: Optional[str]
        frames_pending: Optional[list]
        frames_string: Optional[str]
        frames: Optional[List[str]]
        is_note_locked: bool
        last_noted_at: int
        last_commented_at: int

    root: List[YandePostItem]


class FileInfo(BaseModel):
    """
    下载文件的信息
    """
    file_path: str
    file_size: int
    url: str


if __name__ == '__main__':
    with open(r"C:\Users\sfy11\Documents\a.json", 'rb') as f:
        for i in YandePostData.model_validate_json(f.read()).root:
            print(i.id)
