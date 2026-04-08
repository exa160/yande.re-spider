import os.path
from contextlib import closing
from hashlib import md5
from multiprocessing import Queue
from threading import Thread
from time import sleep

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from loguru import logger
from pathvalidate import sanitize_filename

from backend.config.settings import config
from backend.models.download import FileInfo


class DownloadException(Exception):
    pass


class MD5MismatchException(DownloadException):
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
    def get_content(
        url: str,
        _id: int,
        s: int,
        e: int,
        data_q: Queue,
        progress_callback=None,
    ):
        content_data = []
        success = False
        actual_start = s

        for retry in range(config.yande_api.retry):
            current_start = actual_start
            try:
                headers = {
                    "authority": "files.yande.re",
                    "Referer": "https://yande.re/",
                }
                if current_start > 0 or (e != "" and e is not None):
                    if e == "" or e is None:
                        headers.update({"Range": f"bytes={current_start}-"})
                    else:
                        headers.update({"Range": f"bytes={current_start}-{e}"})
                headers.update(config.yande_api.headers)

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
                            chunk_len = len(chunk) / 1024 / 1024
                            content_data.append(chunk)
                            current_start += len(chunk)
                            if progress_callback:
                                progress_callback(chunk_len)

                success = True
                break
            except Exception as err:
                logger.warning(
                    f"[{_id}] down error {retry} {url} {current_start}-{e}: {err}"
                )
                actual_start = current_start
                sleep(6)

        if success:
            data_q.put([s, current_start, b"".join(content_data)])
        else:
            logger.error(
                f"[{_id}] download failed after {config.yande_api.retry} retries: {url} {s}-{e}"
            )
            if content_data:
                data_q.put([s, current_start, b"".join(content_data)])
            else:
                data_q.put([s, e, b""])

    @staticmethod
    def file_writer(file_info: FileInfo, data_q: Queue, msg_q: Queue):
        f_size = file_info.file_size
        f_path = file_info.file_path

        with open(f_path, "wb") as f:
            f.seek(f_size - 1)
            f.write(b"\x00")

        file = open(f_path, "rb+")
        while queue_wait(data_q, msg_q):
            s, e, data = data_q.get()
            if data:
                file.seek(s)
                file.write(data)

        file.close()

        if file_info.md5:
            file_md5 = md5(open(f_path, "rb").read()).hexdigest()
            if file_info.md5 != file_md5:
                logger.warning(
                    f"md5 check err: {f_path}, expected {file_info.md5}, got {file_md5}"
                )
                raise MD5MismatchException(
                    f"MD5 mismatch for {f_path}: expected {file_info.md5}, got {file_md5}"
                )

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

        for s_offset in range(0, file_size, split_size):
            e_offset = s_offset + split_size - 1
            if e_offset >= file_size - 1:
                e_offset = file_size - 1

            t = executor.submit(
                self.get_content,
                self.file_info.url,
                self.file_info.id,
                s_offset,
                e_offset,
                self.data_q,
                self.progress_callback,
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

    def start(self):
        max_retries = config.yande_api.retry
        last_exception = None

        for attempt in range(max_retries):
            self.data_q = Queue()
            self.close_q = Queue(1)

            file_size = self.file_info.file_size
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

            exception = writer_exception or download_exception
            if exception:
                last_exception = exception
                if isinstance(exception, MD5MismatchException):
                    logger.info(
                        f"[{self.file_info.id}] MD5 mismatch, retrying download..."
                    )
                    continue
                raise exception

            return

        raise last_exception


def queue_wait(data_q: Queue, close_q: Queue):
    while True:
        if data_q.empty():
            if close_q.full():
                return False
            sleep(1)
        else:
            return True
