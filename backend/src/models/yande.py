from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, ConfigDict, RootModel

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


class YandeSearchTags(BaseModel):
    """Yande.re 高级搜索标签转换模型

    支持的搜索语法:
    - 标签: tag1 tag2 (AND), ~tag1 ~tag2 (OR), -tag1 (NOT), tag1* (前缀匹配)
    - 用户: user:bob
    - 投票: vote:3:bob
    - MD5: md5:foo
    - 来源: source:http://site.com
    - 评分: rating:questionable, -rating:questionable
    - ID范围: id:100, id:100.., id:>=100, id:>100, id:..100, id:<=100, id:<100, id:100..200
    - 尺寸: width:100, height:100 (支持范围语法同ID)
    - 像素: mpixels:2.5.. (百万像素)
    - 比例: ratio:16:9
    - 日期: date:2007-01-01 (支持范围语法同ID)
    - 评分: score:100 (支持范围语法同ID)
    - 文件大小: filesize:>=5000 (KB)
    - 排序: order:id, order:id_desc, order:score, order:score_asc, order:mpixels,
            order:mpixels_asc, order:landscape, order:portrait, order:vote
    - 父贴: parent:1234, parent:none
    """

    tags: Optional[str] = None  # 搜索标签（支持 +tag -tag 语法）
    user: Optional[str] = None  # 用户: user:bob
    vote: Optional[int] = None  # 投票数: vote:3
    md5: Optional[str] = None  # MD5哈希: md5:foo
    # source: Optional[str] = None  # 来源: source:http://site.com # TODO 与来源选择冲突
    min_id: Optional[int] = None  # 最小ID: id:>=100
    max_id: Optional[int] = None  # 最大ID: id:<=100
    min_width: Optional[int] = None
    max_width: Optional[int] = None
    min_height: Optional[int] = None
    max_height: Optional[int] = None
    min_mpixels: Optional[float] = None  # 最小百万像素: mpixels:>=2.5
    max_mpixels: Optional[float] = None  # 最大百万像素
    ratio: Optional[str] = None  # 宽高比: ratio:16:9
    min_date: Optional[str] = None  # 最早日期: date:>=2007-01-01
    max_date: Optional[str] = None  # 最晚日期: date:<=2007-01-01
    min_score: Optional[int] = None
    max_score: Optional[int] = None
    min_filesize: Optional[int] = None  # KB
    max_filesize: Optional[int] = None
    rating: Optional[List[Rating]] = None
    file_exts: List[str] = []
    sort_by: Optional[str] = None  # 排序字段
    sort_order: Optional[str] = None  # 排序方向: asc/desc
    parent_id: Optional[int] = None  # 父贴ID: parent:1234
    parent_none: bool = False  # 无父贴: parent:none

    model_config = ConfigDict(from_attributes=True)


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
