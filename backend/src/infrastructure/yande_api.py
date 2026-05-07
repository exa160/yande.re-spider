import traceback
from typing import Optional, Tuple, List
from xml.etree import ElementTree as ET

import requests
from loguru import logger
from pydantic import BaseModel, Field, model_serializer

from src.common import config
from src.common.constant import Rating, yande_constant
from src.common.utils import get_proxy
from src.models.yande import YandePostData, YandeSearchTags


class YandeApi:
    class PostRankQueryParams(BaseModel):
        page: int = 1
        limit: Optional[int] = 25
        tags: Optional[str] = None
        search_tags: YandeSearchTags = Field(
            default_factory=YandeSearchTags,
            exclude=True,  # 排除在序列化之外，单独处理
            )

        @model_serializer(mode="wrap")
        def serialize(self, handler):
            if self.search_tags:
                search_str = YandeApi().search_trans(self.search_tags)
                self.tags = f"{self.tags} {search_str}" if self.tags else search_str
            return handler(self)


    def __init__(self):
        self.post_json_api = yande_constant.post_json_api
        self.post_xml_api = yande_constant.post_xml_api
        self.tag_json_api = yande_constant.tag_json_api
        self.artist_json_api = yande_constant.artist_json_api
        self.proxies = get_proxy()
        self.headers = config.yande_api.headers.model_dump(by_alias=True)

    def get_count(self, tags: str = "") -> int:
        """
        使用 XML API 获取指定标签的总数
        返回 -1 表示获取失败
        """
        query_params = {"page": 1, "limit": 1}
        if tags:
            query_params["tags"] = tags

        for i in range(config.yande_api.retry):
            try:
                req = requests.get(
                    self.post_xml_api,
                    params=query_params,
                    proxies=self.proxies,
                    headers=self.headers,
                    timeout=config.yande_api.timeout,
                )
                if req.status_code != 200:
                    logger.warning(
                        f"[{i + 1}] get count error {req.status_code}: {req.text[:200]}"
                    )
                    continue

                root = ET.fromstring(req.content)
                count_attr = root.get("count")
                if count_attr:
                    return int(count_attr)
                return 0
            except Exception as e:
                logger.warning(f"[{i + 1}] get count error: {e}")
        return -1

    def search_trans(self, search_tags: YandeSearchTags) -> str:
        """将 YandeSearchTags 转换为 yande.re API 识别的搜索标签字符串"""
        parts = []

        # 简单字段映射: {模型字段名: 格式字符串}
        simple_mappings = {
            "tags": "{value}",
            "artist": "artist:{value}",
            "vote": "vote:{value}",
            "md5": "md5:{value}",
            "source": "source:{value}",
            "ratio": "ratio:{value}",
            "parent_id": "parent:{value}",
        }

        # 范围字段映射: {模型字段名: (最小值前缀, 最大值前缀)}
        range_mappings = {
            "min_id": ("id:>=", "id:<="),
            "max_id": ("id:<=", "id:>="),
            "min_width": ("width:>=", "width:<="),
            "max_width": ("width:<=", "width:>="),
            "min_height": ("height:>=", "height:<="),
            "max_height": ("height:<=", "height:>="),
            "min_mpixels": ("mpixels:>=", "mpixels:<="),
            "max_mpixels": ("mpixels:<=", "mpixels:>="),
            "min_date": ("date:>=", "date:<="),
            "max_date": ("date:<=", "date:>="),
            "min_score": ("score:>=", "score:<="),
            "max_score": ("score:<=", "score:>="),
            "min_filesize": ("filesize:>=", "filesize:<="),
            "max_filesize": ("filesize:<=", "filesize:>="),
        }

        # 处理简单映射字段
        for field, fmt in simple_mappings.items():
            value = getattr(search_tags, field, None)
            if value:
                parts.append(fmt.format(value=value))

        # 处理范围映射字段
        for field, (min_prefix, max_prefix) in range_mappings.items():
            if field.startswith("min_"):
                value = getattr(search_tags, field, None)
                if value is not None:
                    parts.append(f"{min_prefix}{value}")
            elif field.startswith("max_"):
                value = getattr(search_tags, field, None)
                if value is not None:
                    parts.append(f"{max_prefix}{value}")

        # 处理 rating
        if search_tags.rating:
            rating = set(search_tags.rating)
            if len(rating) == 3:
                pass  # 全部评级，无需添加
            elif len(rating) == 2:
                excluded = list(set(Rating) - rating)
                if excluded:
                    parts.append(f"-rating:{excluded[0].value}")
            else:
                parts.append(f"rating:{rating[0].value}")

        # 处理 file_exts
        if search_tags.file_exts:
            exts = search_tags.file_exts
            if len(exts) == 1:
                parts.append(f"ext:{exts[0]}")
            else:
                parts.extend(f"ext:{ext}" for ext in exts)

        # 处理 order (排除默认排序)
        if search_tags.sort_by:
            sort_by = search_tags.sort_by
            if search_tags.sort_order in ("asc", "desc"):
                order = search_tags.sort_order
            else:
                order = "desc"
            parts.append(f"order:{sort_by}_{order}")

        # 处理 parent_none
        if search_tags.parent_none:
            parts.append("parent:none")

        return " ".join(parts)

    def get_ranking(
        self,
        query_params: PostRankQueryParams
    ) -> Tuple[bool, Optional[YandePostData]]:
        exception = None
        for i in range(config.yande_api.retry):
            req = None
            try:
                logger.info(f"Requesting Yande API with params: {query_params.model_dump()}")
                logger.info(f"{self.proxies} {self.headers}")
                req = requests.get(
                    self.post_json_api,
                    params=query_params.model_dump(mode="json"),
                    proxies=self.proxies,
                    headers=self.headers,
                    timeout=config.yande_api.timeout,
                )
                req.raise_for_status()
                return True, YandePostData.model_validate_json(req.content)
            except Exception as e:
                logger.warning(traceback.format_exc())
                logger.warning(
                    f"[{i + 1}] requests error"
                    f"page: {query_params.page} tag:"
                    f"{query_params.tags}: {e} {req.content if req is not None else req}"
                )
                exception = e
        return False, exception

    def get_tags(
        self,
        page: int = 1,
        limit: int = 100,
        name_pattern: str = None,
        after_id: int = None,
    ) -> Tuple[bool, List[dict]]:
        """
        获取标签列表
        :param page: 页码
        :param limit: 每页数量 (最大 1000)
        :param name_pattern: 标签名匹配模式 (可选)
        :param after_id: 仅返回 ID 大于此值的标签 (用于增量更新)
        :return: (成功标志, 标签列表)
        """
        query_params = {"page": page, "limit": min(limit, 1000)}
        if name_pattern:
            query_params["name"] = name_pattern
        if after_id is not None:
            query_params["after_id"] = after_id

        for i in range(config.yande_api.retry):
            try:
                req = requests.get(
                    self.tag_json_api,
                    params=query_params,
                    proxies=self.proxies,
                    headers=self.headers,
                    timeout=60,
                )
                if req.status_code != 200:
                    logger.warning(f"[{i + 1}] get tags error {req.status_code}")
                    continue
                tags = req.json()
                return True, tags
            except Exception as e:
                logger.warning(f"[{i + 1}] get tags error: {e}")
        return False, []

    def get_artists(
        self, page: int = 1, name_pattern: str = None
    ) -> Tuple[bool, List[dict]]:
        """
        获取艺术家列表
        :param page: 页码
        :param name_pattern: 艺术家名匹配模式 (可选)
        :return: (成功标志, 艺术家列表)
        """
        query_params = {"page": page}
        if name_pattern:
            query_params["name"] = name_pattern

        for i in range(config.yande_api.retry):
            try:
                req = requests.get(
                    self.artist_json_api,
                    params=query_params,
                    proxies=self.proxies,
                    headers=self.headers,
                    timeout=60,
                )
                if req.status_code != 200:
                    logger.warning(f"[{i + 1}] get artists error {req.status_code}")
                    continue
                artists = req.json()
                return True, artists
            except Exception as e:
                logger.warning(f"[{i + 1}] get artists error: {e}")
        return False, []

    def get_tag_count(self) -> int:
        """获取标签总数"""
        for i in range(config.yande_api.retry):
            try:
                req = requests.get(
                    self.tag_json_api,
                    params={"page": 1, "limit": 1},
                    proxies=self.proxies,
                    headers=self.headers,
                    timeout=config.yande_api.timeout,
                )
                if req.status_code == 200:
                    data = req.json()
                    if isinstance(data, list) and len(data) > 0:
                        return data[0].get("id", 0)
            except Exception as e:
                logger.warning(f"[{i + 1}] get tag count error: {e}")
        return 0

    def get_artist_count(self) -> int:
        """获取艺术家总数"""
        for i in range(config.yande_api.retry):
            try:
                req = requests.get(
                    self.artist_json_api,
                    params={"page": 1, "limit": 1},
                    proxies=self.proxies,
                    headers=self.headers,
                    timeout=config.yande_api.timeout,
                )
                if req.status_code == 200:
                    data = req.json()
                    if isinstance(data, list) and len(data) > 0:
                        return data[0].get("id", 0)
            except Exception as e:
                logger.warning(f"[{i + 1}] get artist count error: {e}")
        return 0
