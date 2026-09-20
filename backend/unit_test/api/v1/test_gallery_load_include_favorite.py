"""Gallery load include_favorite_status tests.

覆盖 GalleryService.query_local_database 在 3 个分支下的双判断行为：
1. include_favorite_status=False：service 不连表，返回 YandeData 不带 is_favorited
2. include_favorite_status=True 但 config.favorites.enable_my_favorites=False：
   后端总开关关闭，service 强制不连表，不带 is_favorited
3. include_favorite_status=True 且 config.favorites.enable_my_favorites=True：
   service LEFT JOIN my_favorite，每个 YandeData 附带 is_favorited (True/False)

实现说明：
- in-memory sqlite + ContextVar session + monkeypatch _get_session_factory，
  与 test_my_favorites_service.py / test_favorite_with_preview_optimizations.py
  同款
- patch src.services.gallery.config：覆盖后端总开关数据源
- 通过构造真实 GalleryLoadRequest 对象传入 service，而非 MagicMock（v2 接口
  是 Pydantic model，MagicMock 字段在 YandeDataQueryParams.model_validate 时
  会失败）

API 行为契约（来自 task-7-brief）：
- is_favorited 默认 None（与 ImageDetail 字段定义一致）
- 当 effective_include_favorite=True 时，is_favorited 在 YandeData 实例上是
  Python bool（True/False），序列化后随 ImageDetail.from_attributes 进入 JSON
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
from src.models.request.gallery import GalleryLoadRequest


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
    """3 张已下载图片 + image_id=2 被收藏。"""
    for i in range(1, 4):
        _seed_yande(in_memory_session, i)
    in_memory_session.add(MyFavorite(image_id=2))
    in_memory_session.commit()
    return in_memory_session


def _make_request(**overrides) -> GalleryLoadRequest:
    """构造 GalleryLoadRequest，覆盖默认 page=1 / page_size=20。"""
    defaults = {
        "page": 1,
        "page_size": 20,
        "include_favorite_status": False,
        "random": False,
    }
    defaults.update(overrides)
    return GalleryLoadRequest(**defaults)


# ============================================================
# 双判断分支 1：include_favorite_status=False → 不连表
# ============================================================


def test_load_with_include_false_does_not_join(session_with_data):
    """include_favorite_status=False 时，service 不连表，每个 YandeData 不带 is_favorited。"""
    from src.services.gallery import GalleryService

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True  # 总开关即便开也不连表
        images, _ = GalleryService.query_local_database(_make_request())

    assert len(images) == 3
    for img in images:
        # YandeData ORM 没有 is_favorited 字段，未挂运行时属性
        assert getattr(img, "is_favorited", None) is None


# ============================================================
# 双判断分支 2：include_favorite_status=True 但 enable_my_favorites=False → 强制不连表
# ============================================================


def test_load_with_include_true_but_switch_off_does_not_join(session_with_data):
    """include_favorite_status=True 但总开关关闭，service 强制不连表。

    关键场景：前端主动请求但后端开关关闭 → 仍按"无收藏状态"返回（保护隐私/避免性能浪费）。
    """
    from src.services.gallery import GalleryService

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = False  # 总开关关闭
        images, _ = GalleryService.query_local_database(
            _make_request(include_favorite_status=True)
        )

    assert len(images) == 3
    for img in images:
        assert getattr(img, "is_favorited", None) is None


# ============================================================
# 双判断分支 3：include_favorite_status=True 且 enable_my_favorites=True → LEFT JOIN
# ============================================================


def test_load_with_include_true_and_switch_on_joins(session_with_data):
    """include_favorite_status=True 且总开关开启，LEFT JOIN 正确标记收藏状态。"""
    from src.services.gallery import GalleryService

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        images, _ = GalleryService.query_local_database(
            _make_request(include_favorite_status=True)
        )

    assert len(images) == 3
    favorited_map = {img.id: img.is_favorited for img in images}
    assert favorited_map[1] is False
    assert favorited_map[2] is True
    assert favorited_map[3] is False


# ============================================================
# 双判断 + random 组合：双开关都为 True 时仍然正确
# ============================================================


def test_random_with_include_favorite_status_combined(in_memory_session):
    """random=True + include_favorite_status=True + enable_my_favorites=True：
    LEFT JOIN 后每个 YandeData 仍挂 is_favorited，且 image_id 互不相同。

    回归保护：MyFavorite.image_id UNIQUE 约束 + .distinct() 全行去重
    保证 LEFT JOIN 不会产生重复 image_id。
    """
    from src.services.gallery import GalleryService

    for i in range(1, 11):
        _seed_yande(in_memory_session, i)
    for fid in (2, 5, 8):
        in_memory_session.add(MyFavorite(image_id=fid))
    in_memory_session.commit()

    with patch("src.services.gallery.config") as mock_config:
        mock_config.favorites.enable_my_favorites = True
        images, _ = GalleryService.query_local_database(
            _make_request(
                include_favorite_status=True, random=True, page_size=10
            )
        )

    assert len(images) == 10
    ids = [img.id for img in images]
    assert len(ids) == len(set(ids)), f"Duplicate ids found: {ids}"
    fav_ids = {img.id for img in images if getattr(img, "is_favorited", None) is True}
    assert fav_ids == {2, 5, 8}, f"Expected favorites {{2,5,8}}, got {fav_ids}"