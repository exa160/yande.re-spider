import os.path
from pathlib import Path
from queue import Queue
from typing import Union, Tuple

import requests
from urllib.parse import unquote
from loguru import logger
from pathvalidate import sanitize_filename

from utils.constant import config
from utils.downloader import MultiDown
from utils.items import YandePostData, YandeSearchTags, YandeRunningConfig, IterStatus


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
        req = None
        for i in range(config.yande_api.retry):
            req = None
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
                logger.warning(f'[{i + 1}] requests error'
                               f'page: {page} tag: {tags}: {e} {req.content if req is not None else req}')


class YandeSpider:
    def __init__(self, search_config: YandeSearchTags = YandeSearchTags()):
        self.y_api = YandeApi()
        self.download_queue = Queue()
        self.search_config = search_config

    @staticmethod
    def scan_id_in_dir(save_dir_path) -> set:
        ret_set = set()
        for entry_dir in os.scandir(save_dir_path):
            if not entry_dir.is_file():
                continue
            try:
                yid = entry_dir.name.split(' ', maxsplit=2)[1]
                yid = int(yid)
                ret_set.add(yid)
            except Exception as e:
                logger.warning(e)
                continue
        return ret_set

    @staticmethod
    def item_iter_and_down(yande_item, save_dir_path, get_config: YandeRunningConfig):
        """
        遍历及下载
        :param yande_item:
        :param save_dir_path:
        :param get_config:
        :return:
        """
        for i in yande_item.root:
            fn = sanitize_filename(unquote(i.file_url.rsplit("/", maxsplit=1)[-1]))
            if i.id <= get_config.stop_id:
                return IterStatus.stop
            if get_config.id_check and get_config.id_check_list is not None:
                if i.id in get_config.id_check_list:
                    continue
            if (save_dir_path / fn).exists():
                if get_config.add_flag:
                    continue
                else:
                    return IterStatus.stop
            MultiDown(i.file_url, str(save_dir_path), fn, i.file_size, i.md5, i.id)
        return IterStatus.next

    def search_trans(self):
        pass

    def get_post_list(self, get_config: YandeRunningConfig = None):
        """
        获取yande搜索列表
        :param get_config:
        :return:
        """
        if get_config is None:
            get_config = YandeRunningConfig()

        s_page = max(1, get_config.start_page)
        e_page = get_config.end_page if get_config.end_page > 0 else 100
        s_page, e_page = (e_page, s_page) if s_page > e_page else (s_page, e_page)
        tags = get_config.tags

        save_dir_path = get_config.save_dir_path
        if save_dir_path is None:
            save_dir_path = Path('.', tags)
        else:
            save_dir_path = Path(save_dir_path)
        logger.info(f'*search start\t{"[" + tags + "]":>20} \tdown path:{save_dir_path}')
        for page in range(s_page, e_page):

            if not save_dir_path.exists():
                os.makedirs(save_dir_path)
            # status, yande_item = self.y_api.get_ranking(page, tags='rating:e width:>=10000 ext:png')
            status, yande_item = self.y_api.get_ranking(page, tags=tags)
            if len(yande_item.root) == 0:
                logger.info(f'**search finish\t{"[" + tags + "]":>20}')
                break
            iter_status = self.item_iter_and_down(yande_item, save_dir_path, get_config)
            if iter_status == IterStatus.stop:
                break

    def update_tags(self, tag_list, b_path, get_config: YandeRunningConfig = YandeRunningConfig()):
        """
        批量搜索tag
        :param tag_list:
        :param b_path:
        :param get_config:
        :return:
        """
        for tag, stop_id, add_flag in tag_list:
            get_config.tags = tag
            get_config.stop_id = stop_id
            get_config.save_dir_path = Path(b_path) / tag
            if get_config.id_check:
                get_config.id_check_list = YandeSpider.scan_id_in_dir(get_config.save_dir_path)
            get_config.add_flag = add_flag
            self.get_post_list(get_config)
