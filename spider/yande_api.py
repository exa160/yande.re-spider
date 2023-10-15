import os.path
from queue import Queue
from typing import Union, Tuple

import requests
from urllib.parse import unquote
from loguru import logger

from utils.constant import config
from utils.downloader import MultiDown
from utils.items import YandePostData, YandeSearchTags


class YandeApi:
    def __init__(self):
        self.post_api = 'https://yande.re/post.json'
        self.proxies = config.yande_api.proxies
        self.headers = config.yande_api.headers

    def get_ranking(self, page: int, tags: str = '') -> Union[tuple[bool, bytes], tuple[bool, YandePostData]]:
        query_params = dict(
            page=page
        )
        if tags:
            query_params.update(dict(tags=tags))
        for i in range(config.yande_api.retry):
            try:
                req = requests.get(self.post_api,
                                   params=query_params,
                                   proxies=self.proxies,
                                   headers=self.headers)
                if req.status_code > 300:
                    logger.info(f'get api error {page} {tags}: {req.status_code}')
                    return False, req.content
                else:
                    # 利用pydantic解析request
                    return True, YandePostData.model_validate_json(req.content)
            except Exception as e:
                logger.warning(f'requests error {page} {tags}: {e}')


class YandeSpider:
    def __init__(self, search_config: YandeSearchTags = YandeSearchTags()):
        self.y_api = YandeApi()
        self.download_queue = Queue()
        self.search_config = search_config

    def get_post_list(self):
        for page in range(1, 2):
            # status, yande_item = self.y_api.get_ranking(page, tags='rating:e width:>=10000 ext:png')
            status, yande_item = self.y_api.get_ranking(page, tags='rating:e width:>=4000 ext:png')
            for i in yande_item.root:
                f = f'./'
                fn = unquote(i.file_url.rsplit("/", maxsplit=1)[-1])
                if os.path.exists(os.path.join(f, fn)):
                    continue
                MultiDown(i.file_url, f, fn, i.file_size, i.md5)


if __name__ == '__main__':
    y = YandeSpider()
    y.get_post_list()
