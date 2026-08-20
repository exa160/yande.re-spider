"""测试 YandeDataRepository.query_random_for_tags() 随机抽样已下载图片"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]) + "/backend")

from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData


def _seed(n: int = 20) -> None:
    """插入 n 条已下载和 n 条未下载的混合数据，tags 都是 'sample'"""
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        for i in range(n * 2):
            rec = YandeData(
                id=2000 + i,
                tags="sample" if i < n else "other",
                width=100, height=100,
                file_ext="jpg",
                file_size=1024,
                file_url=f"http://example.com/{i}.jpg",
                preview_url=f"http://example.com/p_{i}.jpg",
                md5=f"md5_{i}",
                author="tester",
                created_at=datetime(2024, 1, 1, 0, 0, 0),
                down_flag=(i < n),  # 前 n 条 True，后 n 条 False
            )
            repo.session.add(rec)


def test_query_random_returns_only_downloaded():
    _seed(10)
    with YandeDataRepository() as repo:
        result = repo.query_random_for_tags("sample", limit=5)
    assert len(result) == 5
    assert all(r.down_flag is True for r in result)
    assert all(r.tags == "sample" for r in result)


def test_query_random_respects_limit():
    _seed(20)
    with YandeDataRepository() as repo:
        result = repo.query_random_for_tags("sample", limit=3)
    assert len(result) == 3


def test_query_random_excludes_other_tags():
    _seed(10)
    with YandeDataRepository() as repo:
        result = repo.query_random_for_tags("sample", limit=20)
    assert len(result) == 10
    assert all(r.tags == "sample" for r in result)
    assert all(r.down_flag is True for r in result)


def test_query_random_empty_when_no_match():
    with YandeDataRepository() as repo:
        repo.session.query(YandeData).delete()
        result = repo.query_random_for_tags("nonexistent", limit=5)
    assert result == []