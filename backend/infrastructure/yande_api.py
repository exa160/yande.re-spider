from typing import Union, Tuple, Optional, List

import requests
from loguru import logger

from backend.config.settings import config
from backend.models.yande import YandePostData, YandeSearchTags


class YandeApi:
    def __init__(self):
        self.post_api = "https://yande.re/post.json"
        self.proxies = config.yande_api.proxies
        self.headers = config.yande_api.headers

    def search_trans(self, search_tags: YandeSearchTags) -> str:
        """将 YandeSearchTags 转换为 yande.re API 识别的搜索标签字符串"""
        parts = []

        if search_tags.min_width is not None:
            parts.append(f"width:>={search_tags.min_width}")

        if search_tags.max_width is not None:
            parts.append(f"width:<={search_tags.max_width}")

        if search_tags.min_height is not None:
            parts.append(f"height:>={search_tags.min_height}")

        if search_tags.max_height is not None:
            parts.append(f"height:<={search_tags.max_height}")

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
                parts.append(f"rating:-{list(set(["e", "q", "s"]) - set(search_tags.ratings))[0]}")
            else:
                parts.append(f"rating:{rating}")

        if search_tags.file_exts:
            if len(search_tags.file_exts) == 1:
                parts.append(f"ext:{search_tags.file_exts[0]}")
            else:
                for ext in search_tags.file_exts:
                    parts.append(f"ext:{ext}")

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
                    self.post_api,
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
