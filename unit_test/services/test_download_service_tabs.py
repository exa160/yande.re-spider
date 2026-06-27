from src.common.constant import TaskStatus
from src.dao.download_task_dao import DownloadTaskDao
from src.models.database.yande import DownloadTask
from src.services.download import DownloadService


def _setup_tasks():
    with DownloadTaskDao() as dao:
        dao.session.query(DownloadTask).delete()
        for i, s in enumerate([
            TaskStatus.PENDING, TaskStatus.DOWNLOADING, TaskStatus.PAUSED,
            TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED,
        ]):
            dao.create(task_id=f"svc-{i}", image_id=10000 + i, file_name=f"svc{i}.jpg")
            rec = dao.get_by_id(f"svc-{i}")
            rec.status = s


def test_service_get_tasks_accepts_status_list():
    _setup_tasks()
    tasks, total = DownloadService.get_tasks(
        status_list=[TaskStatus.PENDING, TaskStatus.DOWNLOADING]
    )
    assert total == 2


def test_service_get_tasks_default_sort():
    _setup_tasks()
    tasks, _ = DownloadService.get_tasks()
    assert len(tasks) > 0


def test_service_get_status_counts_returns_full_dict():
    _setup_tasks()
    counts = DownloadService.get_status_counts()
    assert set(counts.keys()) == {
        "pending", "downloading", "paused",
        "completed", "failed", "cancelled",
    }
    assert counts["completed"] >= 1
    assert counts["failed"] >= 1
