from functools import wraps
from random import uniform
import time
from typing import Optional, List, Union
from xml.etree import ElementTree as ET

import requests
from loguru import logger
from pydantic import BaseModel, Field, model_validator

from src.common import config
from src.common.constant import Rating, yande_constant
from src.common.utils import get_proxy
from src.models.request.yande import YandeSearchTags
from src.models.response.yande import YandePostData


def _with_retry(method):
    """重试装饰器 - 参考 image_cache.py 的实现"""
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        action_name = method.__name__.replace("_", " ")
        last_exception: Exception = Exception("Unknown error")
        for attempt in range(config.yande_api.retry):
            try:
                return method(self, *args, **kwargs)
            except requests.RequestException as e:
                last_exception = e
                logger.warning(f"[{attempt + 1}] {action_name} failed: {e}")
                if attempt < config.yande_api.retry - 1:
                    time.sleep(uniform(0.1, 1.0))
        raise last_exception
    return wrapper


class YandeApi:
    class PostRankQueryParams(BaseModel):
        page: int = 1
        limit: Optional[int] = 25
        tags: Optional[str] = None
        search_tags: YandeSearchTags = Field(
            default_factory=YandeSearchTags,
            exclude=True,
        )

        @model_validator(mode='after')
        def serialize(self) -> str:
            search_str = YandeApi.search_trans(self.search_tags)
            self.tags = f"{self.tags} {search_str}" if self.tags else search_str
            return self

    def __init__(self):
        self.post_json_api = yande_constant.post_json_api
        self.post_xml_api = yande_constant.post_xml_api
        self.tag_json_api = yande_constant.tag_json_api
        self.artist_json_api = yande_constant.artist_json_api

        self._session = requests.Session()
        proxies = get_proxy()
        if proxies:
            self._session.proxies = proxies
        headers = config.yande_api.headers
        if headers is not None:
            self._session.headers.update(headers.model_dump(by_alias=True, exclude_none=True))


    def _get(self, url: str, params: Optional[dict] = None, timeout: Optional[int] = None) -> requests.Response:
        """统一 GET 请求 - 内部使用 session"""
        if timeout is None:
            timeout = config.yande_api.timeout
        actual_params = params if params is not None else {}
        resp = self._session.get(url, params=actual_params, timeout=timeout)
        resp.raise_for_status()
        return resp


    def get_count(self, tags: str = "") -> int:
        """使用 XML API 获取指定标签的总数，返回 -1 表示获取失败"""
        query_params: dict[str, Union[str, int]] = {"page": 1, "limit": 1}
        if tags:
            query_params["tags"] = tags

        try:
            resp = self._get(self.post_xml_api, params=query_params)
            root = ET.fromstring(resp.content)
            count_attr = root.get("count")
            return int(count_attr) if count_attr else 0
        except requests.RequestException as e:
            logger.warning(f"get count error: {e}")
            return -1

    @staticmethod
    def search_trans(search_tags: YandeSearchTags) -> str:
        """将 YandeSearchTags 转换为 yande.re API 识别的搜索标签字符串"""
        parts = []

        simple_mappings = {
            "tags": "{value}",
            "artist": "artist:{value}",
            "vote": "vote:{value}",
            "md5": "md5:{value}",
            "source": "source:{value}",
            "ratio": "ratio:{value}",
            "parent_id": "parent:{value}",
        }

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

        for field, fmt in simple_mappings.items():
            value = getattr(search_tags, field, None)
            if value:
                parts.append(fmt.format(value=value))

        for field, (min_prefix, max_prefix) in range_mappings.items():
            if field.startswith("min_"):
                value = getattr(search_tags, field, None)
                if value is not None:
                    parts.append(f"{min_prefix}{value}")
            elif field.startswith("max_"):
                value = getattr(search_tags, field, None)
                if value is not None:
                    parts.append(f"{max_prefix}{value}")

        if search_tags.rating:
            rating_set = set(search_tags.rating)
            if len(rating_set) == 3:
                pass
            elif len(rating_set) == 2:
                excluded = list(set(Rating) - rating_set)
                if excluded:
                    parts.append(f"-rating:{excluded[0].value}")
            else:
                parts.append(f"rating:{next(iter(rating_set)).value}")

        if search_tags.file_exts:
            parts.extend(f"ext:{ext}" for ext in search_tags.file_exts)

        if search_tags.sort_by:
            sort_by = search_tags.sort_by
            if search_tags.sort_order in ("asc", "desc"):
                order = search_tags.sort_order
            else:
                order = "desc"
            parts.append(f"order:{sort_by}_{order}")

        if search_tags.parent_none:
            parts.append("parent:none")

        return " ".join(parts)

    @_with_retry
    def get_ranking(self, query_params: PostRankQueryParams) -> YandePostData:
        """获取 ranking 数据"""
        resp = self._get(
            self.post_json_api,
            params=query_params.model_dump(mode="json"),
        )
        return YandePostData.model_validate_json(resp.content)

    @_with_retry
    def get_tags(
        self,
        page: int = 1,
        limit: int = 100,
        name_pattern: Optional[str] = None,
        after_id: Optional[int] = None,
    ) -> List[dict]:
        """获取标签列表"""
        query_params: dict[str, Union[str, int]] = {"page": page, "limit": min(limit, 1000)}
        if name_pattern is not None:
            query_params["name"] = name_pattern
        if after_id is not None:
            query_params["after_id"] = after_id
        resp = self._get(self.tag_json_api, params=query_params, timeout=60)
        return resp.json()


    @_with_retry
    def get_artists(self, page: int = 1, name_pattern: Optional[str] = None) -> List[dict]:
        """获取艺术家列表"""
        query_params: dict[str, Union[str, int]] = {"page": page}
        if name_pattern is not None:
            query_params["name"] = name_pattern

        resp = self._get(self.artist_json_api, params=query_params, timeout=60)
        return resp.json()


    def get_tag_count(self) -> int:
        """获取标签总数"""
        try:
            resp = self._get(self.tag_json_api, params={"page": 1, "limit": 1}, timeout=60)
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("id", 0)
        except requests.RequestException as e:
            logger.warning(f"get_tag_count error: {e}")
        return 0


    def get_artist_count(self) -> int:
        """获取艺术家总数"""
        try:
            resp = self._get(self.artist_json_api, params={"page": 1, "limit": 1}, timeout=60)
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("id", 0)
        except requests.RequestException as e:
            logger.warning(f"get_artist_count error: {e}")
        return 0
