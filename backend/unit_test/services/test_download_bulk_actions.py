"""下载页批量操作（清理预览 / 全部重试）的服务层测试。"""
import asyncio
import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

import src.dao.database as dbmod
from src.common.constant import TaskStatus
from src.models.database.yande import Base, DownloadTask
from src.services.download import DownloadService


@pytest.fixture
def factory(tmp_path, monkeypatch):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'bulk.db'}",
        poolclass=NullPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine, tables=[DownloadTask.__table__])
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(dbmod, "_get_session_factory", lambda: session_factory)
    yield session_factory
    engine.dispose()


def _add(session_factory, task_id: str, status: TaskStatus, completed_days_ago=None):
    now = dt.datetime.now()
    session = session_factory()
    session.add(
        DownloadTask(
            task_id=task_id,
            image_id=1,
            file_name="1.jpg",
            status=status,
            completed_at=(
                now - dt.timedelta(days=completed_days_ago)
                if completed_days_ago is not None
                else None
            ),
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    session.close()


def test_clear_preview_counts_match_delete_scope(factory):
    _add(factory, "c2", TaskStatus.COMPLETED, completed_days_ago=2)
    _add(factory, "c10", TaskStatus.COMPLETED, completed_days_ago=10)
    _add(factory, "c40", TaskStatus.COMPLETED, completed_days_ago=40)
    _add(factory, "c100", TaskStatus.COMPLETED, completed_days_ago=100)
    # 以下两类都不可清理，必须被排除
    _add(factory, "failed-old", TaskStatus.FAILED, completed_days_ago=100)
    _add(factory, "no-completed-at", TaskStatus.COMPLETED, completed_days_ago=None)

    preview = DownloadService.get_clear_preview()

    assert preview["all"] == 4
    assert preview["before_days"]["7"] == 3    # 10/40/100 天前
    assert preview["before_days"]["30"] == 2   # 40/100 天前
    assert preview["before_days"]["90"] == 1   # 100 天前


def test_retry_all_failed_summarizes_started_and_skipped(factory, monkeypatch):
    _add(factory, "ok-1", TaskStatus.FAILED, completed_days_ago=1)
    _add(factory, "ok-2", TaskStatus.FAILED, completed_days_ago=1)
    _add(factory, "no-meta", TaskStatus.FAILED, completed_days_ago=1)
    _add(factory, "pending", TaskStatus.PENDING)   # 不应被批量重试选中

    seen = []

    async def fake_start(task_id: str):
        seen.append(task_id)
        if task_id == "no-meta":
            return False, "图片元数据已丢失，无法重试"
        return True, "任务已启动"

    monkeypatch.setattr(DownloadService, "start_task", staticmethod(fake_start))

    result = asyncio.run(DownloadService.retry_all_failed())

    assert result == {"requested": 3, "started": 2, "skipped": 1}
    assert set(seen) == {"ok-1", "ok-2", "no-meta"}
