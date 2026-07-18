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


# ===== download_first API 参数 =====

@pytest.fixture
def setup_data_with_active_mix():
    """混入 pending / downloading / paused 三个活跃状态，便于测 download_first 分组效果。"""
    with DownloadTaskDao() as dao:
        dao.session.query(DownloadTask).delete()
        # image_id 顺序：31001=pending, 31002=downloading, 31003=paused, 31004=downloading
        for image_id, status in [
            (31001, TaskStatus.PENDING),
            (31002, TaskStatus.DOWNLOADING),
            (31003, TaskStatus.PAUSED),
            (31004, TaskStatus.DOWNLOADING),
        ]:
            dao.create(task_id=f"act-{image_id}", image_id=image_id, file_name=f"{image_id}.jpg")
            rec = dao.get_by_id(f"act-{image_id}")
            rec.status = status


def test_get_tasks_download_first_default_false(client, setup_data_with_active_mix):
    """不传 download_first 时，行为与原有排序一致（纯按 image_id desc）"""
    resp = client.get("/api/v1/download/tasks?status=pending&status=downloading&status=paused")
    assert resp.status_code == 200
    data = resp.json()["data"]
    image_ids = [t["image_id"] for t in data]
    # 不带 download_first：纯按 image_id desc
    assert image_ids == [31004, 31003, 31002, 31001]


def test_get_tasks_download_first_groups_downloading_to_top(client, setup_data_with_active_mix):
    """download_first=true 时，downloading 任务排在最前，其他状态按 image_id desc 排后"""
    resp = client.get(
        "/api/v1/download/tasks?status=pending&status=downloading&status=paused&download_first=true"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    statuses = [t["status"] for t in data]
    # 前 2 个必须是 downloading
    assert statuses[:2] == ["downloading", "downloading"]
    # 后 2 个是 pending + paused
    assert set(statuses[2:]) == {"pending", "paused"}
    # downloading 组内按 image_id desc：31004 在前
    downloading_ids = [t["image_id"] for t in data if t["status"] == "downloading"]
    assert downloading_ids == [31004, 31002]
    # 非 downloading 组内按 image_id desc：31003 在前
    other_ids = [t["image_id"] for t in data if t["status"] != "downloading"]
    assert other_ids == [31003, 31001]


def test_get_tasks_download_first_accepts_false_explicitly(client, setup_data_with_active_mix):
    """显式传 download_first=false 也正常工作（边界：API 路由接受字面 false）"""
    resp = client.get(
        "/api/v1/download/tasks?status=pending&status=downloading&status=paused&download_first=false"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    image_ids = [t["image_id"] for t in data]
    assert image_ids == [31004, 31003, 31002, 31001]
