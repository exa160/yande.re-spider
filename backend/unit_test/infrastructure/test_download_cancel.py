"""下载取消链路回归测试。

背景：此前前端「下载中」任务的取消按钮被禁用 —— ``MultiDown`` 没有停止信号，
取消仅改 DB 状态，worker 仍会把文件下完并在收尾时继续走 COMPLETED 分支。
现在通过 ``threading.Event`` 协作式取消：每个 chunk / 重试等待前检查，
取消后清理半成品文件，且不再写 completed/failed。
"""
import asyncio
import datetime as dt
import threading
from queue import Queue
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import src.dao.database as dbmod
from src.common.constant import TaskStatus
from src.infrastructure.downloader import DownloadCancelled, MultiDown
from src.infrastructure.download_queue import TaskStore
from src.models.database.yande import Base, DownloadTask, YandeData


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'cancel.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(
        engine, tables=[DownloadTask.__table__, YandeData.__table__]
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(dbmod, "_get_session_factory", lambda: session_factory)
    yield session_factory
    engine.dispose()


class _FakeResponse:
    def __init__(self, cancel_event: threading.Event):
        self._cancel_event = cancel_event

    def close(self):
        pass

    def iter_content(self, chunk_size):
        yield b"a" * 16
        self._cancel_event.set()   # 第一个 chunk 到达后用户点了取消
        yield b"b" * 16


class _FakeSession:
    def __init__(self, cancel_event: threading.Event):
        self._cancel_event = cancel_event

    def get(self, *args, **kwargs):
        return _FakeResponse(self._cancel_event)


def test_get_content_stops_mid_stream_on_cancel():
    cancel_event = threading.Event()
    with pytest.raises(DownloadCancelled):
        MultiDown.get_content(
            "https://example.invalid/1.png",
            1,
            0,
            32,
            Queue(),
            _FakeSession(cancel_event),
            None,
            cancel_event,
        )


def _seed_task(factory, status: TaskStatus) -> str:
    now = dt.datetime.now()
    task_id = "22222222-2222-2222-2222-222222222222"
    session = factory()
    session.add(
        YandeData(
            id=823153,
            md5="a" * 32,
            file_url="https://assets.yande.re/data/original/823153.png",
            file_ext="png",
            file_size=1234,
        )
    )
    session.add(
        DownloadTask(
            task_id=task_id,
            image_id=823153,
            file_name="823153.png",
            status=status,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    session.close()
    return task_id


def _memory_task(store, task_id: str, status: TaskStatus, yande_data=None):
    task = store.DownloadTask(
        task_id=task_id,
        image_id=yande_data.id if yande_data is not None else 823153,
        yande_data=yande_data,
        file_name="823153.png",
        status=status,
    )
    with store._lock:
        store._tasks[task_id] = task
    return task


def test_cancel_task_signals_worker_and_persists_cancelled(factory, monkeypatch):
    import src.services.download as service_module

    task_id = _seed_task(factory, TaskStatus.DOWNLOADING)
    store = TaskStore()
    _memory_task(store, task_id, TaskStatus.DOWNLOADING)
    event = store.get_cancel_event(task_id)
    monkeypatch.setattr(service_module, "task_store", store)

    ok, message = service_module.DownloadService.cancel_task(task_id)

    assert ok and message == "任务已取消"
    assert event.is_set(), "取消必须给正在执行的 worker 发停止信号"
    assert task_id not in store._tasks

    session = factory()
    try:
        record = session.get(DownloadTask, task_id)
        assert record.status == TaskStatus.CANCELLED
        assert record.completed_at is not None
    finally:
        session.close()


def test_run_download_async_cancel_cleans_file_without_overwriting_status(
    factory, monkeypatch, tmp_path
):
    import src.infrastructure.download_queue as queue_module

    task_id = _seed_task(factory, TaskStatus.PENDING)
    yande_data = YandeData(
        id=823153,
        md5="a" * 32,
        file_url="https://assets.yande.re/data/original/823153.png",
        file_ext="png",
        file_size=1234,
    )
    store = queue_module.TaskStore()
    _memory_task(store, task_id, TaskStatus.PENDING, yande_data=yande_data)
    partial = tmp_path / "823153.png"

    class FakeMultiDown:
        def __init__(self, file_info, _progress_callback=None, cancel_event=None):
            self.cancel_event = cancel_event

        def start(self):
            partial.write_bytes(b"partial")
            self.cancel_event.set()
            raise DownloadCancelled("cancelled")

        def cleanup(self):
            pass

    monkeypatch.setattr(queue_module, "task_store", store)
    monkeypatch.setattr(queue_module, "path_constant", SimpleNamespace(originals_dir=tmp_path))
    monkeypatch.setattr(queue_module, "MultiDown", FakeMultiDown)

    asyncio.run(queue_module.run_download_async(task_id))

    assert not partial.exists(), "取消后必须删除半成品文件"
    assert not (tmp_path / "823153.png.lock").exists()

    session = factory()
    try:
        record = session.get(DownloadTask, task_id)
        assert record.status == TaskStatus.CANCELLED
    finally:
        session.close()
