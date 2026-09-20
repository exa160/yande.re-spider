"""Gallery detail include_favorite_status tests.

覆盖 GalleryService.get_image_detail 在 3 个分支下的双判断行为：
1. include_favorite_status=False：service 不连表，is_favorited=None
2. include_favorite_status=True 但 config.favorites.enable_my_favorites=False：
   后端总开关关闭，service 强制不连表，is_favorited=None
3. include_favorite_status=True 且 config.favorites.enable_my_favorites=True：
   service 查询 my_favorite，is_favorited=True（已收藏）/False（未收藏）

实现说明：
- in-memory sqlite + ContextVar session + monkeypatch _get_session_factory，
  与 test_gallery_load_include_favorite.py / test_my_favorites_service.py 同款
- patch src.services.gallery.config：覆盖后端总开关数据源
- 直接调用 GalleryService.get_image_detail（service-level 集成测试，
  覆盖双判断逻辑而非仅 route schema 校验）

API 行为契约（来自 task-8-brief）：
- is_favorited 默认 None（与 ImageDetail 字段定义一致）
- 当 effective_include_favorite=True 时，is_favorited 在 ImageDetail 上是
  Python bool（True/False）
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
from src.models.database.my_favorite import MyFavorite
from src.models.database.yande import YandeData


@pytest.fixture
def in_memory_session(monkeypatch):
    """干净的 in-memory sqlite + ContextVar session，与现有测试同款。"""
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
    """种一条最小可用的 YandeData 记录。"""
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
    """1 张已下载图片（id=42）+ MyFavorite(image_id=42)。"""
    _seed_yande(in_memory_session, 42)
    in_memory_session.add(MyFavorite(image_id=42))
    in_memory_session.commit()
    return in_memory_session


@pytest.fixture
def session_with_image_only(in_memory_session):
    """1 张已下载图片（id=99），无收藏记录（用于 False 分支回归）。"""
    _seed_yande(in_memory_session, 99)
    in_memory_session.commit()
    return in_memory_session


# ============================================================
# 双判断分支 1：include_favorite_status=False → 不连表
# ============================================================


def test_detail_with_include_false_returns_none(session_with_image_only):
    """include_favorite_status=False 时，service 不连表，is_favorited=None。

    即便数据本身已收藏（这里没收藏，但即便有也不影响），前端没请求就不返回。
    """
    from src.services.gallery import GalleryService

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True  # 总开关即便开也不连表
        detail = GalleryService.get_image_detail(
            image_id=99, include_favorite_status=False
        )

    assert detail is not None
    assert detail.id == 99
    assert detail.is_favorited is None


# ============================================================
# 双判断分支 2：include_favorite_status=True 但 enable_my_favorites=False → 强制不连表
# ============================================================


def test_detail_with_include_true_and_switch_off_returns_none(session_with_data):
    """include_favorite_status=True 但总开关关闭，service 强制不连表，is_favorited=None。

    关键场景：前端主动请求但后端开关关闭 → 仍按"无收藏状态"返回
    （保护隐私/避免性能浪费）。
    """
    from src.services.gallery import GalleryService

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False  # 总开关关闭
        detail = GalleryService.get_image_detail(
            image_id=42, include_favorite_status=True
        )

    assert detail is not None
    assert detail.id == 42
    assert detail.is_favorited is None


# ============================================================
# 双判断分支 3：include_favorite_status=True 且 enable_my_favorites=True → 真连表
# ============================================================


def test_detail_with_include_true_and_switch_on_returns_true(session_with_data):
    """include_favorite_status=True 且总开关开启，is_favorited=True（已收藏）。"""
    from src.services.gallery import GalleryService

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        detail = GalleryService.get_image_detail(
            image_id=42, include_favorite_status=True
        )

    assert detail is not None
    assert detail.id == 42
    assert detail.is_favorited is True


# ============================================================
# 回归保护：未收藏图 + 双开关开 → is_favorited=False（非 None）
# ============================================================


def test_detail_with_include_true_and_switch_on_not_favorited_returns_false(
    session_with_image_only,
):
    """未收藏的图，双开关都开时返回 is_favorited=False（不是 None 也不是缺字段）。"""
    from src.services.gallery import GalleryService

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        detail = GalleryService.get_image_detail(
            image_id=99, include_favorite_status=True
        )

    assert detail is not None
    assert detail.id == 99
    assert detail.is_favorited is False