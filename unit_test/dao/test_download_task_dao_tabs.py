"""DownloadTaskDao 多状态/排序/计数测试（TDD）"""
import pytest

from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao
from src.models.database.yande import DownloadTask


@pytest.fixture
def dao():
    with DownloadTaskDao() as d:
        d.session.query(DownloadTask).delete()
        yield d


def test_count_by_status_empty_db_returns_all_zero(dao):
    """空库时所有状态返回 0"""
    counts = dao.count_by_status()
    assert counts == {
        "pending": 0, "downloading": 0, "paused": 0,
        "completed": 0, "failed": 0, "cancelled": 0,
    }


def test_count_by_status_groups_by_status(dao):
    """插入混合状态后按 status 分组统计"""
    for i in range(3):
        dao.create(task_id=f"c-{i}", image_id=100 + i, file_name=f"c{i}.jpg")
        rec = dao.get_by_id(f"c-{i}")
        rec.status = TaskStatus.COMPLETED
    for i in range(2):
        dao.create(task_id=f"f-{i}", image_id=200 + i, file_name=f"f{i}.jpg")
        rec = dao.get_by_id(f"f-{i}")
        rec.status = TaskStatus.FAILED
    dao.create(task_id="p-0", image_id=300, file_name="p0.jpg")

    counts = dao.count_by_status()
    assert counts["completed"] == 3
    assert counts["failed"] == 2
    assert counts["pending"] == 1
    assert counts["downloading"] == 0
    assert counts["paused"] == 0
    assert counts["cancelled"] == 0


def test_query_tasks_filters_by_single_status(dao):
    for i, s in enumerate([TaskStatus.PENDING, TaskStatus.COMPLETED, TaskStatus.FAILED]):
        dao.create(task_id=f"t-{i}", image_id=1000 + i, file_name=f"t{i}.jpg")
        rec = dao.get_by_id(f"t-{i}")
        rec.status = s

    results, total = dao.query_tasks(status_list=[TaskStatus.COMPLETED])
    assert total == 1
    assert len(results) == 1
    assert results[0]["status"] == "completed"


def test_query_tasks_filters_by_multiple_status(dao):
    for i, s in enumerate([
        TaskStatus.PENDING, TaskStatus.DOWNLOADING, TaskStatus.PAUSED,
        TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
    ]):
        dao.create(task_id=f"m-{i}", image_id=2000 + i, file_name=f"m{i}.jpg")
        rec = dao.get_by_id(f"m-{i}")
        rec.status = s

    results, total = dao.query_tasks(
        status_list=[TaskStatus.PENDING, TaskStatus.DOWNLOADING, TaskStatus.PAUSED]
    )
    assert total == 3
    assert {r["status"] for r in results} == {"pending", "downloading", "paused"}


def test_query_tasks_sorts_by_created_at_desc(dao):
    for i in range(3):
        dao.create(task_id=f"s-{i}", image_id=3000 + i, file_name=f"s{i}.jpg")
        rec = dao.get_by_id(f"s-{i}")
        rec.status = TaskStatus.COMPLETED

    results, _ = dao.query_tasks(sort_by="created_at", order="desc")
    assert results[0]["task_id"] == "s-2"
    assert results[-1]["task_id"] == "s-0"


def test_query_tasks_sorts_by_completed_at(dao):
    for i in range(3):
        dao.create(task_id=f"co-{i}", image_id=4000 + i, file_name=f"co{i}.jpg")
        rec = dao.get_by_id(f"co-{i}")
        rec.status = TaskStatus.COMPLETED

    results, _ = dao.query_tasks(sort_by="completed_at", order="desc")
    assert len(results) == 3


def test_query_tasks_rejects_invalid_sort_by(dao):
    with pytest.raises(ValueError, match="Invalid sort_by"):
        dao.query_tasks(sort_by="invalid_field")


def test_query_tasks_rejects_invalid_order(dao):
    with pytest.raises(ValueError, match="Invalid order"):
        dao.query_tasks(order="invalid_order")


def test_query_tasks_pagination(dao):
    for i in range(5):
        dao.create(task_id=f"p-{i}", image_id=5000 + i, file_name=f"p{i}.jpg")
        rec = dao.get_by_id(f"p-{i}")
        rec.status = TaskStatus.COMPLETED

    page1, total = dao.query_tasks(page=1, page_size=2)
    assert total == 5
    assert len(page1) == 2

    page3, _ = dao.query_tasks(page=3, page_size=2)
    assert len(page3) == 1
