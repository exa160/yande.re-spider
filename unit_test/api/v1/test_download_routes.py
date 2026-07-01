import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src import init_app, app_config
from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao
from src.models.database.yande import DownloadTask


@pytest.fixture
def client():
    test_app = FastAPI(**app_config.model_dump())
    init_app(test_app)
    return TestClient(test_app)


@pytest.fixture(autouse=True)
def setup_data():
    with DownloadTaskDao() as dao:
        dao.session.query(DownloadTask).delete()
        for i, s in enumerate([
            TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.FAILED,
        ]):
            dao.create(task_id=f"api-{i}", image_id=20000 + i, file_name=f"api{i}.jpg")
            rec = dao.get_by_id(f"api-{i}")
            rec.status = s


def test_get_tasks_without_status_returns_all(client):
    resp = client.get("/api/v1/download/tasks")
    assert resp.status_code == 200
    assert "data" in resp.json()


def test_get_tasks_with_single_status_param(client):
    resp = client.get("/api/v1/download/tasks?status=completed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1


def test_get_tasks_with_multiple_status_params(client):
    resp = client.get("/api/v1/download/tasks?status=pending&status=failed")
    assert resp.status_code == 200
    data = resp.json()
    statuses = {t["status"] for t in data["data"]}
    assert statuses.issubset({"pending", "failed"})


def test_get_tasks_with_sort_by_and_order(client):
    resp = client.get("/api/v1/download/tasks?sort_by=created_at&order=asc")
    assert resp.status_code == 200


def test_get_tasks_rejects_invalid_sort_by(client):
    resp = client.get("/api/v1/download/tasks?sort_by=invalid_field")
    assert resp.status_code == 422


def test_get_tasks_rejects_invalid_order(client):
    resp = client.get("/api/v1/download/tasks?order=invalid_order")
    assert resp.status_code == 422


def test_get_tasks_count_returns_all_six_statuses(client):
    resp = client.get("/api/v1/download/tasks/count")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert set(data.keys()) == {
        "pending", "downloading", "paused",
        "completed", "failed", "cancelled",
    }
    assert all(isinstance(data[k], int) for k in data)


def test_get_tasks_with_sort_by_image_id(client):
    resp = client.get("/api/v1/download/tasks?sort_by=image_id&order=desc")
    assert resp.status_code == 200
    data = resp.json()["data"]
    image_ids = [t["image_id"] for t in data]
    assert image_ids == sorted(image_ids, reverse=True)


def test_get_tasks_default_sort_is_image_id_desc(client):
    resp = client.get("/api/v1/download/tasks")
    assert resp.status_code == 200
    data = resp.json()["data"]
    image_ids = [t["image_id"] for t in data]
    assert image_ids == sorted(image_ids, reverse=True)
