"""GET /api/v1/download/tasks/states —— 图片下载状态快照

背景：``yande_data.down_flag`` 只在下载**完成**时落库，前端在下单瞬间
到下载完成之间没有可见反馈（单图/批量/收藏自动下载都表现为「标识不变」）。
本端点把队列状态按 image_id 暴露给前端，驱动「下载中 / 已下载」三态标识。

覆盖：
1. DAO 聚合：同一 image_id 多条任务只保留最新一条
2. DAO 终态窗口：窗口期外的终态任务不返回
3. Service 合并：DB 状态 + 内存实时进度
4. Route：响应结构与错误处理
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import TaskStatus
from src.dao.database import Base, _get_session_factory
from src.models.database.yande import DownloadTask


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def db(monkeypatch):
    """in-memory sqlite + 替换 _get_session_factory，DAO 的 with 上下文走它。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)
    return TestSession


def _add_task(session, image_id, status, *, minutes_ago=0, task_id=None, progress=0.0):
    moment = datetime.now() - timedelta(minutes=minutes_ago)
    rec = DownloadTask(
        task_id=task_id or f"task-{image_id}-{status.value}-{minutes_ago}",
        image_id=image_id,
        file_name=f"{image_id}.jpg",
        file_size=1024,
        status=status,
        progress=progress,
        created_at=moment,
        updated_at=moment,
    )
    session.add(rec)
    session.commit()
    return rec


# ============================================================
# DAO
# ============================================================


def test_active_states_by_image_returns_active_tasks(db):
    from src.dao.download_task_dao import download_task_dao

    with db() as session:
        _add_task(session, 1, TaskStatus.PENDING)
        _add_task(session, 2, TaskStatus.DOWNLOADING)
        _add_task(session, 3, TaskStatus.PAUSED)
        _add_task(session, 4, TaskStatus.COMPLETED)  # 终态不算活跃

    with download_task_dao as dao:
        active = dao.active_states_by_image()

    assert set(active.keys()) == {1, 2, 3}


def test_active_states_by_image_keeps_latest_task_per_image(db):
    """同一 image_id 重复下单时只暴露最新一条（前端只看一个状态）。"""
    from src.dao.download_task_dao import download_task_dao

    with db() as session:
        _add_task(session, 1, TaskStatus.PENDING, minutes_ago=5, task_id="old")
        _add_task(session, 1, TaskStatus.DOWNLOADING, minutes_ago=0, task_id="new")

    with download_task_dao as dao:
        active = dao.active_states_by_image()

    assert active[1].task_id == "new"


def test_finished_states_by_image_respects_window(db):
    """窗口期外的终态任务不返回（避免每次轮询都回放全部历史）。"""
    from src.dao.download_task_dao import download_task_dao

    with db() as session:
        _add_task(session, 10, TaskStatus.COMPLETED, minutes_ago=0)
        _add_task(session, 11, TaskStatus.FAILED, minutes_ago=10)
        _add_task(session, 12, TaskStatus.CANCELLED, minutes_ago=0)

    with download_task_dao as dao:
        finished = dao.finished_states_by_image(datetime.now() - timedelta(seconds=30))

    assert finished == {10: "completed", 12: "cancelled"}


def test_finished_states_by_image_keeps_latest_per_image(db):
    from src.dao.download_task_dao import download_task_dao

    with db() as session:
        _add_task(session, 20, TaskStatus.FAILED, minutes_ago=2, task_id="f1")
        _add_task(session, 20, TaskStatus.COMPLETED, minutes_ago=0, task_id="c1")

    with download_task_dao as dao:
        finished = dao.finished_states_by_image(datetime.now() - timedelta(seconds=30))

    assert finished == {20: "completed"}


# ============================================================
# Service
# ============================================================


def test_get_image_states_shape_and_memory_progress_merge(db):
    """内存中的实时进度（progress_callback 不落 DB）必须被合并进来。"""
    from src.infrastructure.download_queue import task_store
    from src.services.download import DownloadService

    with db() as session:
        _add_task(session, 30, TaskStatus.DOWNLOADING, task_id="t30", progress=0.0)
        _add_task(session, 31, TaskStatus.COMPLETED, minutes_ago=0, task_id="t31")

    task_store._tasks["t30"] = task_store.DownloadTask(
        task_id="t30",
        image_id=30,
        file_name="30.jpg",
        status=TaskStatus.DOWNLOADING,
        progress=0.42,
        speed=1024.0,
        downloaded_size=512,
    )
    try:
        states = DownloadService.get_image_states(finished_window=30)
    finally:
        task_store._tasks.pop("t30", None)

    assert [item["image_id"] for item in states["active"]] == [30]
    active = states["active"][0]
    assert active["status"] == "downloading"
    # DB 里 progress=0，内存里 0.42 → 取内存
    assert active["progress"] == pytest.approx(0.42)
    assert active["downloaded_size"] == 512

    assert states["finished"] == [{"image_id": 31, "status": "completed"}]


def test_get_image_states_empty_when_no_tasks(db):
    from src.services.download import DownloadService

    assert DownloadService.get_image_states() == {"active": [], "finished": []}


# ============================================================
# Route
# ============================================================


@pytest.fixture
def client():
    from src.api.v1.download import router as download_router

    app = FastAPI()
    app.include_router(download_router, prefix="/api/v1/download")
    with patch("src.api.v1.download.DownloadService") as mock_svc:
        mock_svc.get_image_states = MagicMock(
            return_value={
                "active": [
                    {
                        "image_id": 1,
                        "task_id": "t1",
                        "status": "downloading",
                        "progress": 0.5,
                        "speed": 10.0,
                        "downloaded_size": 100,
                    }
                ],
                "finished": [{"image_id": 2, "status": "completed"}],
            }
        )
        yield TestClient(app), mock_svc


def test_states_endpoint_returns_active_and_finished(client):
    c, _ = client
    resp = c.get("/api/v1/download/tasks/states")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["active"][0]["image_id"] == 1
    assert body["data"]["active"][0]["status"] == "downloading"
    assert body["data"]["finished"] == [{"image_id": 2, "status": "completed"}]


def test_states_endpoint_passes_window(client):
    c, mock_svc = client
    c.get("/api/v1/download/tasks/states?finished_window=90")
    mock_svc.get_image_states.assert_called_once_with(90)


def test_states_endpoint_maps_error_to_4xx(client):
    c, mock_svc = client
    mock_svc.get_image_states.side_effect = RuntimeError("db down")
    resp = c.get("/api/v1/download/tasks/states")
    assert resp.status_code >= 400
