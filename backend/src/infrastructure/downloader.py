from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from hashlib import md5
from pathlib import Path
from queue import Queue
from threading import Thread, Event, Lock
from time import sleep
from typing import Optional

import requests
from filelock import FileLock
from loguru import logger
from pathvalidate import sanitize_filename
from pydantic import BaseModel

from src.common import config
from src.common.utils import get_proxy


class FileInfo(BaseModel):
    """下载文件的信息"""

    id: Optional[int] = None
    file_size: int
    file_name: str
    file_path: Path
    md5: Optional[str] = None
    url: str


class DownloadException(Exception):
    pass


class MD5MismatchException(DownloadException):
    pass


class MultiDown:
    def __init__(self, file_info: FileInfo, _progress_callback=None) -> None:
        self.thread_num = config.downloader.thread_num
        self.data_q: Queue = Queue()
        self.close_event = Event()
        self.progress_lock = Lock()
        self.progress_callback = _progress_callback
        if not file_info.file_size:
            file_info.file_size = self.get_file_size(file_info.url)
        file_info.file_name = sanitize_filename(file_info.file_name)
        self._file_info = file_info

    def __del__(self):
        if hasattr(self, 'data_q') and self.data_q:
            try:
                self.close_event.set()
            except Exception:
                pass

    @property
    def file_info(self):
        return self._file_info

    @staticmethod
    def get_file_size(_url):
        with closing(
            requests.get(
                _url,
                stream=True,
                proxies=get_proxy(),
                headers=config.yande_api.headers.model_dump(by_alias=True),
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

        for retry in range(config.downloader.retry_times):
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
                        proxies=get_proxy(),
                        headers=headers,
                        timeout=config.yande_api.timeout,
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
                f"[{_id}] download failed after {config.downloader.retry_times} retries: {url} {s}-{e}"
            )
            if content_data:
                data_q.put([s, current_start, b"".join(content_data)])
            else:
                data_q.put([s, e, b""])

    @staticmethod
    def file_writer(file_info: FileInfo, data_q: Queue, close_event: Event):
        f_size = file_info.file_size
        f_path = file_info.file_path / file_info.file_name

        # 使用文件锁确保写入安全
        lock_path = f_path.with_suffix(f_path.suffix + ".lock")
        lock = FileLock(lock_path, timeout=300)

        with lock:
            # 创建占位文件
            with open(f_path, "wb") as f:
                f.seek(f_size - 1)
                f.write(b"\x00")

            # 使用上下文管理器确保文件关闭
            with open(f_path, "rb+") as file:
                while True:
                    if data_q.empty():
                        if close_event.is_set():
                            break
                        sleep(0.1)
                    else:
                        try:
                            s, e, data = data_q.get_nowait()
                        except:
                            if close_event.is_set():
                                break
                            sleep(0.1)
                            continue

                        if data:
                            file.seek(s)
                            file.write(data)

            # MD5验证
            if file_info.md5:
                with open(f_path, "rb") as f:
                    file_md5 = md5(f.read()).hexdigest()
                if file_info.md5 != file_md5:
                    logger.warning(
                        f"md5 check err: {f_path}, expected {file_info.md5}, got {file_md5}"
                    )
                    raise MD5MismatchException(
                        f"MD5 mismatch for {f_path}: expected {file_info.md5}, got {file_md5}"
                    )

        # 清理锁文件
        try:
            lock_path.unlink(missing_ok=True)
        except OSError:
            pass

    def cleanup(self):
        if hasattr(self, 'data_q') and self.data_q:
            try:
                self.data_q.close()
                self.data_q.join_thread()
            except Exception:
                pass

    def down_file_in_range(self, file_size):
        split_size = config.downloader.split_size

        num_chunks = file_size // split_size if split_size > 0 else 1
        if num_chunks < 1:
            num_chunks = 1

        with  ThreadPoolExecutor(max_workers=self.thread_num) as executor:
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

    def start(self):
        max_retries = config.downloader.retry_times
        last_exception = None

        for _ in range(max_retries):
            self.data_q = Queue()
            self.close_event.clear()

            file_size = self.file_info.file_size
            writer_exception = None
            download_exception = None

            def writer_target():
                nonlocal writer_exception
                try:
                    self.file_writer(self.file_info, self.data_q, self.close_event)
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

            self.close_event.set()
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
