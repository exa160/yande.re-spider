"""测试 YandeDataRepository.get_downloaded_ids() 返回 down_flag=True 的 ID 集合"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData


def _setup():
    """插入混合 down_flag 的测试数据"""
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        for i in range(5):
            rec = YandeData(
                id=1000 + i,
                tags=f"test_{i}",
                width=100, height=100,
                file_ext="jpg",
                file_size=1024,
                file_url=f"http://example.com/{i}.jpg",
                preview_url=f"http://example.com/p_{i}.jpg",
                md5=f"md5_{i}",
                author="tester",
                created_at=datetime(2024, 1, 1, 0, 0, 0),
                down_flag=(i % 2 == 0),  # 0, 2, 4 → True；1, 3 → False
            )
            repo.session.add(rec)


def test_get_downloaded_ids_returns_only_true_flags():
    _setup()
    with YandeDataRepository() as repo:
        ids = repo.get_downloaded_ids()
    assert isinstance(ids, set)
    assert ids == {1000, 1002, 1004}


def test_get_downloaded_ids_empty_when_no_downloads():
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        ids = repo.get_downloaded_ids()
    assert ids == set()