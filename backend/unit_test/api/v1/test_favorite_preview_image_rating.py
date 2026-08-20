"""验证 /favorites/with-preview 响应的 preview_images 包含 rating 字段。

Task 1 brief: 前端 Gallery 收藏夹模式需要 rating 字段以决定是否应用 safeMode 模糊。
ORM 全字段加载已经返回 rating 字符串，model_validate 应透传到 response。
"""
from datetime import datetime

import pytest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import Rating
from src.dao.favorite_dao import favorite_dao
from src.models.database.yande import Base, YandeData
from src.middleware.session import _request_session
from src.services.favorites import FavoritesService


@pytest.fixture
def in_memory_session(monkeypatch):
    """为该测试注入一个干净的 in-memory sqlite session，并设置 request ContextVar。

    RequestSessionMiddleware 是 Pure ASGI，测试里没有 ASGI 包装层；
    直接用 ContextVar 模拟请求作用域即可。
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    token = _request_session.set(session)
    # YandeDataRepository() 走 _get_session_factory()，必须 patch 到 in-memory sessionmaker
    monkeypatch.setattr(
        "src.dao.database._get_session_factory",
        lambda: TestSession,
    )
    try:
        yield session, engine
    finally:
        _request_session.reset(token)
        session.close()


def _seed_folder_with_yande(sess, rating: Rating) -> int:
    """种一个 folder + 1 张 YandeData，返回 folder.id。"""
    f = favorite_dao.create(name="t", tags="sample")
    folder_id = f.id
    favorite_dao.update(folder_id, local_count=10)  # 触发预览生成
    rec = YandeData(
        id=9000,
        tags="sample",
        width=100,
        height=100,
        file_ext="jpg",
        file_size=1024,
        file_url="http://a.jpg",
        preview_url="http://pa.jpg",
        md5="m",
        author="t",
        created_at=datetime(2024, 1, 1),
        down_flag=True,
        rating=rating,
    )
    sess.add(rec)
    sess.commit()
    return folder_id


def test_preview_images_include_rating(in_memory_session):
    """FavoritesService.get_folders_with_preview 返回的 FolderPreviewImageMinimal 必须含 rating。"""
    sess, _ = in_memory_session
    _seed_folder_with_yande(sess, rating=Rating.R15)
    items, _total, _has_more = FavoritesService.get_folders_with_preview(
        page=1, page_size=20
    )
    assert items, "expected at least one folder in items"
    preview = items[0].preview_images
    assert preview, "expected preview_images to contain at least 1 image"
    img = preview[0]
    assert img.rating == Rating.R15
    assert img.rating == "q"


def test_preview_image_model_has_rating_attribute():
    """显式校验 model schema 暴露 rating 字段（防御 silent 漏改）。"""
    from src.models.response.favorites import FolderPreviewImageMinimal

    assert "rating" in FolderPreviewImageMinimal.model_fields
