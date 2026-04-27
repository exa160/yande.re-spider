from typing import Union, Tuple, List
from xml.etree import ElementTree as ET

import requests
from loguru import logger

from src.common import config
from src.common.constant import (
    YANDE_RE_BASE_URL,
    YANDE_RE_POST_API,
    YANDE_RE_TAG_API,
)
from src.models.yande import YandePostData, YandeSearchTags


# Yande.re API 端点
YANDE_POST_JSON_API = f"{YANDE_RE_BASE_URL}/post.json"
YANDE_POST_XML_API = f"{YANDE_RE_BASE_URL}/post.xml"
YANDE_TAG_JSON_API = f"{YANDE_RE_BASE_URL}/tag.json"
YANDE_ARTIST_JSON_API = f"{YANDE_RE_BASE_URL}/artist.json"


class YandeApi:
    def __init__(self):
        self.post_json_api = YANDE_POST_JSON_API
        self.post_xml_api = YANDE_POST_XML_API
        self.tag_json_api = YANDE_TAG_JSON_API
        self.artist_json_api = YANDE_ARTIST_JSON_API
        config.yande_api.proxies = config.yande_api.proxies
        self.headers = config.yande_api.headers

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
                    proxies=config.yande_api.proxies,
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
            "user": "user:{value}",
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

        # 处理 ratings
        if search_tags.ratings:
            ratings = search_tags.ratings
            if len(ratings) == 3:
                pass  # 全部评级，无需添加
            elif len(ratings) == 2:
                excluded = list(set(["e", "q", "s"]) - set(ratings))
                if excluded:
                    parts.append(f"-rating:{excluded[0]}")
            else:
                parts.append(f"rating:{ratings[0]}")

        # 处理 file_exts
        if search_tags.file_exts:
            exts = search_tags.file_exts
            if len(exts) == 1:
                parts.append(f"ext:{exts[0]}")
            else:
                parts.extend(f"ext:{ext}" for ext in exts)

        # 处理 order (排除默认排序)
        if search_tags.order and search_tags.order not in ("id", "id_desc"):
            parts.append(f"order:{search_tags.order}")

        # 处理 parent_none
        if search_tags.parent_none:
            parts.append("parent:none")

        return " ".join(parts)

    def get_ranking(
        self, page: int, tags: str = "", search_tags: YandeSearchTags = None
    ) -> Union[Tuple[bool, bytes], Tuple[bool, YandePostData]]:
        query_params = dict(page=page)

        combined_tags = tags
        if search_tags:
            search_str = self.search_trans(search_tags)
            if search_str:
                combined_tags = f"{tags} {search_str}" if tags else search_str

        if combined_tags:
            query_params.update(dict(tags=combined_tags))

        for i in range(config.yande_api.retry):
            req = None
            try:
                req = requests.get(
                    self.post_json_api,
                    params=query_params,
                    proxies=config.yande_api.proxies,
                    headers=self.headers,
                )
                if req.status_code > 300:
                    logger.info(
                        f"get api error {page} {combined_tags}: {req.status_code}"
                    )
                    if req.status_code > 500:
                        continue
                    return False, req.content
                else:
                    return True, YandePostData.model_validate_json(req.content)
            except Exception as e:
                logger.warning(
                    f"[{i + 1}] requests error"
                    f"page: {page} tag: {combined_tags}: {e} {req.content if req is not None else req}"
                )
        return False, b""

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
                    proxies=config.yande_api.proxies,
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
        self, page: int = 1, limit: int = 100, name_pattern: str = None
    ) -> Tuple[bool, List[dict]]:
        """
        获取艺术家列表
        :param page: 页码
        :param limit: 每页数量 (最大 1000)
        :param name_pattern: 艺术家名匹配模式 (可选)
        :return: (成功标志, 艺术家列表)
        """
        query_params = {"page": page, "limit": min(limit, 1000)}
        if name_pattern:
            query_params["name"] = name_pattern

        for i in range(config.yande_api.retry):
            try:
                req = requests.get(
                    self.artist_json_api,
                    params=query_params,
                    proxies=config.yande_api.proxies,
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
                    proxies=config.yande_api.proxies,
                    headers=self.headers,
                    timeout=30,
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
                    proxies=config.yande_api.proxies,
                    headers=self.headers,
                    timeout=30,
                )
                if req.status_code == 200:
                    data = req.json()
                    if isinstance(data, list) and len(data) > 0:
                        return data[0].get("id", 0)
            except Exception as e:
                logger.warning(f"[{i + 1}] get artist count error: {e}")
        return 0
