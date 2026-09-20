"""Gallery load random tests.

覆盖 GalleryService.query_local_database 在 random=True 时的两个关键不变量：
1. DISTINCT image_id：即便 LEFT JOIN 后（理论上）会产生重复行，
   ORDER BY RANDOM() + DISTINCT(YandeData.id) 必须保证返回的 image_id 互不相同
2. page_size limit：随机模式也必须尊重 page_size，不超过

实现说明：
- in-memory sqlite + ContextVar session + monkeypatch _get_session_factory，
  与 test_my_favorites_service.py / test_favorite_with_preview_optimizations.py 同款
- 用 page_size=5/20 验证上限
- random 不依赖 env var，固定传 random=True
"""
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating
from src.dao.database import Base
from src.middleware.session import _request_session
from src.models.database.yande import YandeData
from src.models.request.gallery import GalleryLoadRequest


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session。"""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    token = _request_session.set(session)
    monkeypatch.setattr(
        "src.dao.database._get_session_factory",
        lambda: TestSession,
    )
    try:
        yield session
    finally:
        _request_session.reset(token)
        session.close()


def _seed_yande(sess, image_id: int, tags: str = "rating:s") -> YandeData:
    rec = YandeData(
        id=image_id,
        tags=tags,
        width=100,
        height=100,
        file_ext="jpg",
        file_size=1024,
        file_url=f"http://a/{image_id}.jpg",
        preview_url=f"http://pa/{image_id}.jpg",
        md5=f"m{image_id}",
        author="t",
        created_at=datetime(2024, 1, 1),
        down_flag=True,
        rating=Rating.S,
    )
    sess.add(rec)
    return rec


@pytest.fixture
def session_with_data(in_memory_session):
    """10 张已下载图片（id 1..10）。"""
    for i in range(1, 11):
        _seed_yande(in_memory_session, i)
    in_memory_session.commit()
    return in_memory_session


def _make_request(**overrides) -> GalleryLoadRequest:
    defaults = {
        "page": 1,
        "page_size": 20,
        "include_favorite_status": False,
        "random": False,
    }
    defaults.update(overrides)
    return GalleryLoadRequest(**defaults)


# ============================================================
# 关键不变量 1：random=True 返回 DISTINCT image_id
# ============================================================


def test_random_returns_distinct_ids(session_with_data):
    """random=True 时 image_id 互不相同（不出现重复）。

    关键 SQL：ORDER BY RANDOM() + DISTINCT(YandeData.id)
    """
    from src.services.gallery import GalleryService

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False
        images, _ = GalleryService.query_local_database(
            _make_request(random=True, page_size=20)
        )

    ids = [img.id for img in images]
    assert len(ids) == len(set(ids)), f"Duplicate ids found: {ids}"
    # 10 张图 page_size=20 全部返回
    assert len(ids) == 10


# ============================================================
# 关键不变量 2：random=True 遵守 page_size 上限
# ============================================================


def test_random_returns_correct_count(session_with_data):
    """random=True 时返回条数严格等于 page_size（不超过、不少于）。"""
    from src.services.gallery import GalleryService

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False
        images, _ = GalleryService.query_local_database(
            _make_request(random=True, page_size=5)
        )

    assert len(images) == 5