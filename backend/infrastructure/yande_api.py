from typing import Union, Tuple

import requests
from loguru import logger

from backend.config.settings import config
from backend.config.constant import YANDE_RE_POST_API, YANDE_RE_REFERER
from backend.models.yande import YandePostData


class YandeApi:
    def __init__(self):
        self.post_api = YANDE_RE_POST_API
        self.proxies = config.yande_api.proxies
        self.headers = config.yande_api.headers

    def get_ranking(
        self, page: int, tags: str = ""
    ) -> Union[Tuple[bool, bytes], Tuple[bool, YandePostData]]:
        query_params = dict(page=page)
        if tags:
            query_params.update(dict(tags=tags))
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
                    logger.info(f"get api error {page} {tags}: {req.status_code}")
                    if req.status_code > 500:
                        continue
                    return False, req.content
                else:
                    return True, YandePostData.model_validate_json(req.content)
            except Exception as e:
                logger.warning(
                    f"[{i + 1}] requests error"
                    f"page: {page} tag: {tags}: {e} {req.content if req is not None else req}"
                )
        return False, b""
