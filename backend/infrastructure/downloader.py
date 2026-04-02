import os.path
from contextlib import closing
from hashlib import md5
from multiprocessing import Queue
from threading import Thread
from time import sleep

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
    TaskID,
    Task,
)
from pathvalidate import sanitize_filename

from backend.config.settings import config
from backend.models.download import FileInfo


class DownloadException(Exception):
    pass


class MultiDown:
    def __init__(
        self,
        url: str,
        file_path: str,
        file_name: str,
        file_size: int = 0,
        _md5: str = None,
        _id: int = None,
        _show_progress: bool = True,
        _progress_callback=None,
    ) -> None:
        self.thread_num = config.downloader.thread_num
        self.data_q: Queue = Queue()
        self.progress_q: Queue = Queue()
        self.close_q: Queue = Queue(1)
        self.show_progress = _show_progress
        self.progress_callback = _progress_callback
        if file_size == 0:
            file_size = self.get_file_size(url)
        file_name = sanitize_filename(file_name)
        self.file_info = FileInfo(
            url=url,
            id=_id,
            file_path=os.path.join(file_path, file_name),
            file_size=file_size,
            md5=_md5,
        )
        if self.show_progress:
            self.progress = Progress(
                TextColumn("down file [progress.description] {task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                SpeedColumn(" {task.speed}"),
                TextColumn("{task.completed:>.03f}/{task.total:>.03f} MB"),
                TimeRemainingColumn(),
                TimeElapsedColumn(),
            )
            self.progress.start()
        self.start()

    @staticmethod
    def get_file_size(_url):
        with closing(
            requests.get(
                _url,
                stream=True,
                proxies=config.yande_api.proxies,
                headers=config.yande_api.headers,
            )
        ) as res:
            file_size = int(res.headers.get("Content-Length", "0"))
        return file_size

    @staticmethod
    def get_content(url: str, _id: int, s: int, e: int, rx_q: Queue, data_q: Queue):
        headers = {"authority": "files.yande.re", "Referer": "https://yande.re/"}
        if s != 0 or e != "":
            headers.update({"Range": f"bytes={s}-{e}"})
        headers.update(config.yande_api.headers)
        for retry in range(config.yande_api.retry):
            content_data = []
            chunk_sum = 0
            try:
                with closing(
                    requests.get(
                        url,
                        stream=True,
                        proxies=config.yande_api.proxies,
                        headers=headers,
                        timeout=50,
                    )
                ) as res:
                    for chunk in res.iter_content(
                        chunk_size=config.downloader.chunk_size
                    ):
                        if chunk:
                            rx_q.put(len(chunk) / 1024 / 1024)
                            chunk_sum += len(chunk) / 1024 / 1024
                            content_data.append(chunk)
                data_q.put([s, e, b"".join(content_data)])
                return
            except Exception as err:
                logger.warning(f"[{_id}] down error {retry} {url} {s}-{e}: {err}")
                rx_q.put(-chunk_sum)
                sleep(6)
        raise DownloadException(
            f"Failed to download range {s}-{e} after {config.yande_api.retry} retries"
        )

    @staticmethod
    def progress_update(rx_q: Queue, msg_q: Queue, progress: Progress, task: TaskID):
        while queue_wait(rx_q, msg_q):
            down_length = rx_q.get()
            progress.advance(task, down_length)

    @staticmethod
    def file_writer(file_info: FileInfo, data_q: Queue, msg_q: Queue):
        f_size = file_info.file_size
        f_path = file_info.file_path
        with open(f_path, "w") as f:
            f.seek(f_size - 1)
            f.write("\x00")

        file = open(f_path, "rb+")
        while queue_wait(data_q, msg_q):
            s, e, data = data_q.get()
            if not data:
                file.close()
                raise DownloadException(
                    f"Empty data received for range {s}-{e}, possible download failure"
                )
            file.seek(s)
            file.write(data)

        file.close()

        if file_info.md5:
            file = open(f_path, "rb+")
            file_md5 = md5(file.read()).hexdigest()
            file.close()
            if file_info.md5 != file_md5:
                logger.warning(f"md5 check err: {f_path}")
                os.remove(f_path)
                raise DownloadException(f"MD5 mismatch for {f_path}")

    def down_file_in_range(self, file_size):
        split_size = config.downloader.split_size

        num_chunks = file_size // split_size if split_size > 0 else 1
        if num_chunks < 1:
            num_chunks = 1

        if num_chunks == 1:
            self._download_single_threaded(file_size)
            return

        executor = ThreadPoolExecutor(max_workers=self.thread_num)
        executor_pool = []
        expected_ranges = []

        for s_offset in range(0, file_size, split_size):
            e_offset = s_offset + split_size - 1
            if e_offset >= file_size - 1:
                e_offset = file_size - 1
            expected_ranges.append((s_offset, e_offset))

            if self.show_progress:
                t = executor.submit(
                    self.get_content,
                    self.file_info.url,
                    self.file_info.id,
                    s_offset,
                    e_offset,
                    self.progress_q,
                    self.data_q,
                )
            else:
                t = executor.submit(
                    self._download_range_with_callback,
                    s_offset,
                    e_offset,
                )
            t.add_done_callback(
                lambda x: logger.warning(x.exception()) if x.exception() else ""
            )
            executor_pool.append(t)

        for t in as_completed(executor_pool):
            t.result()

    def _download_single_threaded(self, file_size):
        downloaded_size = 0
        content_data = []
        headers = {"authority": "files.yande.re", "Referer": "https://yande.re/"}
        headers.update(config.yande_api.headers)

        for retry in range(config.yande_api.retry):
            try:
                with closing(
                    requests.get(
                        self.file_info.url,
                        stream=True,
                        proxies=config.yande_api.proxies,
                        headers=headers,
                        timeout=50,
                    )
                ) as res:
                    for chunk in res.iter_content(
                        chunk_size=config.downloader.chunk_size
                    ):
                        if chunk:
                            downloaded_size += len(chunk)
                            content_data.append(chunk)
                            if self.progress_callback:
                                self.progress_callback(len(chunk) / 1024 / 1024)

                self.data_q.put([0, file_size - 1, b"".join(content_data)])
                return
            except Exception as err:
                logger.warning(
                    f"[{self.file_info.id}] single-thread download error {retry}: {err}"
                )
                sleep(6)

        raise DownloadException(
            f"Single-thread download failed after {config.yande_api.retry} retries"
        )

    def _download_range_with_callback(self, s: int, e: int):
        content_data = []
        chunk_sum = 0
        headers = {"authority": "files.yande.re", "Referer": "https://yande.re/"}
        headers.update({"Range": f"bytes={s}-{e}"})
        headers.update(config.yande_api.headers)

        for retry in range(config.yande_api.retry):
            try:
                with closing(
                    requests.get(
                        self.file_info.url,
                        stream=True,
                        proxies=config.yande_api.proxies,
                        headers=headers,
                        timeout=50,
                    )
                ) as res:
                    for chunk in res.iter_content(
                        chunk_size=config.downloader.chunk_size
                    ):
                        if chunk:
                            chunk_sum += len(chunk) / 1024 / 1024
                            content_data.append(chunk)
                    self.data_q.put([s, e, b"".join(content_data)])
                    if self.progress_callback:
                        self.progress_callback(chunk_sum)
                    return
            except Exception as err:
                logger.warning(
                    f"[{self.file_info.id}] range {s}-{e} error {retry}: {err}"
                )
                sleep(6)

        raise DownloadException(
            f"Range {s}-{e} download failed after {config.yande_api.retry} retries"
        )

    def start(self):
        file_size = self.file_info.file_size
        file_path = self.file_info.file_path
        description = (
            file_path
            if len(file_path) < 21
            else f"{file_path[:10]}...{file_path[-10:]}"
        )

        writer_exception = None
        download_exception = None

        def writer_target():
            nonlocal writer_exception
            try:
                self.file_writer(self.file_info, self.data_q, self.close_q)
            except DownloadException as e:
                writer_exception = e
            except Exception as e:
                writer_exception = e

        writer_t = Thread(target=writer_target)
        writer_t.start()

        try:
            self.down_file_in_range(file_size)
        except DownloadException as e:
            download_exception = e
        except Exception as e:
            download_exception = e

        self.close_q.put("1")
        writer_t.join()

        if self.show_progress:
            self.progress.stop()

        if writer_exception:
            if isinstance(writer_exception, DownloadException):
                raise writer_exception
            raise DownloadException(str(writer_exception))

        if download_exception:
            raise download_exception

        if self.file_info.md5 and not os.path.exists(file_path):
            raise DownloadException(
                f"MD5 check failed for {file_path}, file was removed"
            )


class SpeedColumn(TextColumn):
    def render(self, task: Task) -> str:
        if task.speed is None:
            return "0.000 MB/s"
        elif task.speed is not None:
            return f"{task.speed:.03f} MB/s"


def queue_wait(data_q: Queue, close_q: Queue):
    while True:
        if data_q.empty():
            if close_q.full():
                return False
            sleep(1)
        else:
            return True
