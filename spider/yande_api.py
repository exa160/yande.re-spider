import os.path
from pathlib import Path
from queue import Queue
from typing import Union, Tuple

import requests
from urllib.parse import unquote
from loguru import logger

from utils.constant import config
from utils.downloader import MultiDown
from utils.items import YandePostData, YandeSearchTags, YandeRunningConfig


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

    def get_post_list(self, get_config: YandeRunningConfig = YandeRunningConfig()):
        s_page = max(1, get_config.start_page)
        e_page = get_config.end_page if get_config.end_page > 0 else 100
        s_page, e_page = (e_page, s_page) if s_page > e_page else (s_page, e_page)
        tags = get_config.tags

        save_dir_path = get_config.save_dir_path
        if save_dir_path is None:
            save_dir_path = Path('.', tags)
        else:
            save_dir_path = Path(save_dir_path)

        for page in range(s_page, e_page):

            if not save_dir_path.exists():
                os.makedirs(save_dir_path)
            # status, yande_item = self.y_api.get_ranking(page, tags='rating:e width:>=10000 ext:png')
            status, yande_item = self.y_api.get_ranking(page, tags=tags)
            if len(yande_item.root) == 0:
                logger.info('finish')
                break
            for i in yande_item.root:
                fn = unquote(i.file_url.rsplit("/", maxsplit=1)[-1])
                if i.id <= get_config.stop_id:
                    return
                if (save_dir_path / fn).exists():
                    continue
                MultiDown(i.file_url, str(save_dir_path), fn, i.file_size, i.md5, i.id)

    def update_tags(self, tag_list, b_path, get_config: YandeRunningConfig = YandeRunningConfig()):
        for tag, stop_id in tag_list:
            get_config.tags = tag
            get_config.stop_id = stop_id
            get_config.save_dir_path = b_path / tag
            self.get_post_list(get_config)
