"""下载队列启动恢复 / 重复队列条目的回归测试。

生产事故（2026-10-22）：服务重启后 ``TaskStore.load_from_db`` 只恢复
``download_task`` 行，不带 ``yande_data``；``run_download_async`` 拿不到
file_url/md5，333 个 pending 任务在几秒内全部以 "Missing yande_data" 失败。

本测试锁定两条约束：
1. 启动恢复必须回表 yande_data，恢复出的任务可直接执行；
2. 队列里的重复条目（重复点「启动」）遇到非 PENDING 状态必须跳过，
   不能把已完成任务重新拉回 DOWNLOADING 再失败。
"""
import asyncio
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import src.dao.database as dbmod
from src.common.constant import TaskStatus
from src.infrastructure.download_queue import TaskStore
from src.models.database.yande import Base, DownloadTask, YandeData


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'recovery.db'}",
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


def _seed(session_factory, status: TaskStatus) -> str:
    now = dt.datetime.now()
    task_id = "11111111-1111-1111-1111-111111111111"
    session = session_factory()
    session.add(
        YandeData(
            id=823153,
            md5="a" * 32,
            file_url="https://assets.yande.re/data/original/823153.png",
            file_ext="png",
            file_size=1886783,
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


def test_load_from_db_restores_yande_data(factory):
    """恢复出的 pending 任务必须带 yande_data，否则启动即全部失败。"""
    task_id = _seed(factory, TaskStatus.PENDING)

    store = TaskStore()
    assert store.load_from_db() == 1

    task = store._tasks[task_id]
    assert task.yande_data is not None
    assert task.yande_data.file_url == (
        "https://assets.yande.re/data/original/823153.png"
    )
    assert task.yande_data.md5 == "a" * 32
    assert task.yande_data.file_ext == "png"


def test_duplicate_queue_entry_skips_terminal_task(factory, monkeypatch):
    """重复队列条目命中已完成任务时必须原地跳过，不能改写状态。"""
    task_id = _seed(factory, TaskStatus.COMPLETED)

    import src.infrastructure.download_queue as queue_module

    store = TaskStore()
    monkeypatch.setattr(queue_module, "task_store", store)
    asyncio.run(queue_module.run_download_async(task_id))

    session = factory()
    record = session.get(DownloadTask, task_id)
    try:
        assert record.status == TaskStatus.COMPLETED
        assert record.error_message is None
    finally:
        session.close()
