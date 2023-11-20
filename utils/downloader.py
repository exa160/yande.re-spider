import os.path
from contextlib import closing
from hashlib import md5
from multiprocessing import Queue
from threading import Thread
from time import sleep

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger
from rich.progress import Progress, TextColumn, BarColumn, TimeRemainingColumn, TimeElapsedColumn, TaskID
from pathvalidate import sanitize_filename

from utils.constant import config
from utils.items import FileInfo


class MultiDown:
    """
    利用header Range实现分段下载
    """

    def __init__(self, url: str, file_path: str, file_name: str,
                 file_size: int = 0, _md5: str = None, _id: int = None) -> None:
        self.thread_num = config.downloader.thread_num
        self.data_q: Queue = Queue()
        self.progress_q: Queue = Queue()
        self.close_q: Queue = Queue(1)
        if file_size == 0:
            file_size = self.get_file_size(url)
        # 排除文件名特殊字符
        file_name = sanitize_filename(file_name)
        self.file_info = FileInfo(url=url, id=_id,
                                  file_path=os.path.join(file_path, file_name), file_size=file_size, md5=_md5)
        self.progress = Progress(TextColumn('down file [progress.description] {task.description}'),
                                 BarColumn(),
                                 TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                                 SpeedColumn(" {task.speed}"),
                                 TextColumn("{task.completed:>.03f}/{task.total:>.03f} MB"),
                                 TimeRemainingColumn(),
                                 TimeElapsedColumn()
                                 )
        self.progress.start()
        self.start()

    @staticmethod
    def get_file_size(_url):
        with closing(requests.get(_url, stream=True,
                                  proxies=config.yande_api.proxies,
                                  headers=config.yande_api.headers)) as res:
            file_size = int(res.headers.get('Content-Length', '0'))
        return file_size

    @staticmethod
    def get_content(url: str, _id: int, s: int, e: int, rx_q: Queue, data_q: Queue):
        headers = {
            "authority": "files.yande.re",
            'Referer': 'https://yande.re/'
        }
        if s != 0 or e != '':
            headers.update({"Range": f"bytes={s}-{e}"})
        headers.update(config.yande_api.headers)
        for retry in range(config.yande_api.retry):
            content_data = []
            chunk_sum = 0
            try:
                with closing(requests.get(url, stream=True,
                                          proxies=config.yande_api.proxies,
                                          headers=headers,
                                          timeout=5)) as res:
                    for chunk in res.iter_content(chunk_size=config.downloader.chunk_size):
                        if chunk:
                            rx_q.put(len(chunk) / 1024 / 1024)
                            chunk_sum += len(chunk) / 1024 / 1024
                            content_data.append(chunk)
                data_q.put([s, e, b''.join(content_data)])
                return
            except Exception as err:
                logger.warning(f'[{_id}] down error {retry} {url} {s}-{e}: {err}')
                if s != 0 or e != '':
                    rx_q.put(-chunk_sum)
                sleep(6)

    @staticmethod
    def progress_update(rx_q: Queue, msg_q: Queue, progress: Progress, task: TaskID):
        """
        刷新进度条
        """
        # add = 0
        while queue_wait(rx_q, msg_q):
            down_length = rx_q.get()
            # add += down_length
            progress.advance(task, down_length)

    @staticmethod
    def file_writer(file_info: FileInfo, data_q: Queue, msg_q: Queue):
        f_size = file_info.file_size
        f_path = file_info.file_path
        with open(f_path, 'w') as f:
            f.seek(f_size - 1)
            f.write('\x00')

        file = open(f_path, 'rb+')
        while queue_wait(data_q, msg_q):
            s, e, data = data_q.get()
            file.seek(s)
            file.write(data)

        file.close()

        if file_info.md5:
            file = open(f_path, 'rb+')
            file_md5 = md5(file.read()).hexdigest()
            file.close()
            # print(file_md5, file_info.md5)
            if file_info.md5 != file_md5:
                logger.warning(f'md5 check err: {f_path}')
                os.remove(f_path)

    def down_file_in_range(self, file_size):
        executor = ThreadPoolExecutor(max_workers=self.thread_num)
        split_size = config.downloader.split_size
        executor_pool = []
        if (file_size // split_size) < 2:
            split_size = file_size + 1

        for s_offset in range(0, file_size + 1, split_size):
            e_offset = s_offset + split_size - 1
            if e_offset >= file_size:
                e_offset = ''
            t = executor.submit(self.get_content,
                                self.file_info.url, self.file_info.id,
                                s_offset, e_offset, self.progress_q, self.data_q)
            t.add_done_callback(lambda x: logger.warning(x.exception()) if x.exception() else '')
            executor_pool.append(t)
            # self.get_content(self.file_info.url, s_offset, e_offset, self.progress_q, self.data_q)

        for t in as_completed(executor_pool):
            t.result()

    def start(self):
        file_size = self.file_info.file_size
        file_path = self.file_info.file_path
        description = file_path if len(file_path) < 21 else f'{file_path[:10]}...{file_path[-10:]}'
        # 启动进度条
        task_id = self.progress.add_task(f'[{self.file_info.id}] {description}',
                                         total=file_size / 1024 / 1024)
        progress_t = Thread(target=self.progress_update, args=(self.progress_q, self.close_q, self.progress, task_id))
        progress_t.start()
        # 启动文件写
        writer_t = Thread(target=self.file_writer, args=(self.file_info, self.data_q, self.close_q))
        writer_t.start()
        # 启动下载分割
        self.down_file_in_range(file_size)
        self.close_q.put('1')
        writer_t.join()
        progress_t.join()
        self.progress.stop()


class SpeedColumn(TextColumn):
    def render(self, task: "Task") -> str:
        if task.speed is None:
            return 'NA'
        elif task.speed is not None:
            return f'{task.speed:.03f} MB/s'


def queue_wait(data_q: Queue, close_q: Queue):
    while True:
        if data_q.empty():
            if close_q.full():
                return False
            sleep(1)
        else:
            return True
