"""
yande.re 搜索相关请求模型

YandeSearchTags 是高级搜索参数模型，被
infrastructure/yande_api.py 用于将结构化参数转换为 yande.re 查询字符串。
"""

from typing import Optional, List

from pydantic import BaseModel, ConfigDict

from src.common.constant import Rating


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
