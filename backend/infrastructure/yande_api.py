from typing import Union, Tuple, Optional, List, Any
from xml.etree import ElementTree as ET
import json

import requests
from loguru import logger

from backend.config.settings import config
from backend.models.yande import YandePostData, YandeSearchTags


class YandeApi:
    def __init__(self):
        self.post_json_api = "https://yande.re/post.json"
        self.post_xml_api = "https://yande.re/post.xml"
        self.tag_json_api = "https://yande.re/tag.json"
        self.artist_json_api = "https://yande.re/artist.json"
        self.proxies = config.yande_api.proxies
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
                    proxies=self.proxies,
                    headers=self.headers,
                    timeout=30,
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

        if search_tags.tags:
            parts.append(search_tags.tags)

        if search_tags.user:
            parts.append(f"user:{search_tags.user}")

        if search_tags.vote is not None:
            parts.append(f"vote:{search_tags.vote}")

        if search_tags.md5:
            parts.append(f"md5:{search_tags.md5}")

        if search_tags.source:
            parts.append(f"source:{search_tags.source}")

        if search_tags.min_id is not None:
            parts.append(f"id:>={search_tags.min_id}")

        if search_tags.max_id is not None:
            parts.append(f"id:<={search_tags.max_id}")

        if search_tags.min_width is not None:
            parts.append(f"width:>={search_tags.min_width}")

        if search_tags.max_width is not None:
            parts.append(f"width:<={search_tags.max_width}")

        if search_tags.min_height is not None:
            parts.append(f"height:>={search_tags.min_height}")

        if search_tags.max_height is not None:
            parts.append(f"height:<={search_tags.max_height}")

        if search_tags.min_mpixels is not None:
            parts.append(f"mpixels:>={search_tags.min_mpixels}")

        if search_tags.max_mpixels is not None:
            parts.append(f"mpixels:<={search_tags.max_mpixels}")

        if search_tags.ratio:
            parts.append(f"ratio:{search_tags.ratio}")

        if search_tags.min_date:
            parts.append(f"date:>={search_tags.min_date}")

        if search_tags.max_date:
            parts.append(f"date:<={search_tags.max_date}")

        if search_tags.min_score is not None:
            parts.append(f"score:>={search_tags.min_score}")

        if search_tags.max_score is not None:
            parts.append(f"score:<={search_tags.max_score}")

        if search_tags.min_filesize is not None:
            parts.append(f"filesize:>={search_tags.min_filesize}")

        if search_tags.max_filesize is not None:
            parts.append(f"filesize:<={search_tags.max_filesize}")

        if search_tags.ratings:
            if len(search_tags.ratings) == 3:
                pass
            elif len(search_tags.ratings) == 2:
                parts.append(
                    f"-rating:{list(set(['e', 'q', 's']) - set(search_tags.ratings))[0]}"
                )
            else:
                parts.append(f"rating:{search_tags.ratings[0]}")

        if search_tags.file_exts:
            if len(search_tags.file_exts) == 1:
                parts.append(f"ext:{search_tags.file_exts[0]}")
            else:
                for ext in search_tags.file_exts:
                    parts.append(f"ext:{ext}")

        if search_tags.order and search_tags.order not in ("id", "id_desc"):
            parts.append(f"order:{search_tags.order}")

        if search_tags.parent_id is not None:
            parts.append(f"parent:{search_tags.parent_id}")

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
                    proxies=self.proxies,
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
                    proxies=self.proxies,
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
