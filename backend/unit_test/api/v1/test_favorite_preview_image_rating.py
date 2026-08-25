"""验证 /favorites/with-preview 响应的 preview_images 包含 rating 字段，且序列化输出使用 display 格式。

Task 1 brief: 前端 Gallery 收藏夹模式需要 rating 字段以决定是否应用 safeMode 模糊。
ORM 全字段加载已经返回 rating 字符串，model_validate 应透传到 response。

Task 2 brief（回归测试）: 序列化输出必须是 Rating.display（'Safe'/'Questionable'/'Explicit'），
而非数据库原值（'s'/'q'/'e'）。否则前端 FolderTile.vue 的 !== 'Safe' 判断失效，
导致安全模式下整个收藏夹预览图全模糊。
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


def _seed_folder_with_yande(sess, rating: Rating, image_id: int = 9000) -> int:
    """种一个 folder + 1 张 YandeData，返回 folder.id。

    image_id 参数用于参数化测试避免 unique 冲突。
    """
    f = favorite_dao.create(name="t", tags="sample")
    folder_id = f.id
    favorite_dao.update(folder_id, local_count=10)  # 触发预览生成
    rec = YandeData(
        id=image_id,
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
    """FavoritesService.get_folders_with_preview 返回的 FolderPreviewImageMinimal 必须含 rating。

    Python 层访问 img.rating 由于 Rating 是 str Enum，仍然 == "q"（value），
    但序列化（model_dump / JSON 响应）后变成 'Questionable'（display）。
    """
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


@pytest.mark.parametrize("db_rating, expected_display, image_id", [
    (Rating.S, "Safe", 9001),
    (Rating.R15, "Questionable", 9002),
    (Rating.R18, "Explicit", 9003),
])
def test_preview_image_rating_serializes_to_display(
    in_memory_session, db_rating, expected_display, image_id
):
    """回归测试：序列化输出必须是 Rating.display，而非数据库原值。

    前端 FolderTile.vue 的 safeMode 模糊判断是按 'Safe' 比较的（与主视图 ImageDetail 对齐）：
        img.rating !== 'Safe'  →  模糊
    如果接口返回数据库原值 's'，则永远 !== 'Safe' → 全模糊。

    Rating 是 str Enum，所以 Python 层 img.rating == "q" 仍成立（Rating.R15.value），
    但 model_dump() / JSON 序列化后变成 display 'Questionable'。
    """
    sess, _ = in_memory_session
    _seed_folder_with_yande(sess, rating=db_rating, image_id=image_id)
    items, _, _ = FavoritesService.get_folders_with_preview(page=1, page_size=20)
    img_dict = items[0].preview_images[0].model_dump()
    assert img_dict["rating"] == expected_display, (
        f"db rating={db_rating.value!r} 应序列化为 display={expected_display!r}，"
        f"实际 {img_dict['rating']!r}。"
        f"如果实际值是 's'/'q'/'e'，说明 FolderPreviewImageMinimal 的 serializer 被回退。"
    )


def test_preview_image_rating_serializer_matches_main_view():
    """跨接口契约：收藏夹预览的 rating 序列化格式必须与主视图 ImageDetail 一致。

    主视图（gallery.ImageDetail）通过 @field_serializer 返回 v.display。
    收藏夹预览（favorites.FolderPreviewImageMinimal）必须保持同一契约，
    否则前端一处 'Safe' 一处 's' 会导致 safeMode 行为分裂。
    """
    from src.models.response.gallery import ImageDetail
    from src.models.response.favorites import FolderPreviewImageMinimal

    # 模拟 ORM 对象：rating 字段是字符串（数据库原值）
    fake_orm = type("Fake", (), {"id": 1, "rating": "s"})()

    img_detail_dict = ImageDetail(
        id=1, tags=[], width=100, height=100, rating=Rating.S,
        file_url="", preview_url="", file_size=0, file_ext="jpg",
        author="t", created_at=datetime(2024, 1, 1), md5="m", score=None, down_flag=True,
    ).model_dump()
    folder_minimal_dict = FolderPreviewImageMinimal.model_validate(fake_orm).model_dump()

    assert img_detail_dict["rating"] == "Safe"
    assert folder_minimal_dict["rating"] == "Safe", (
        "FolderPreviewImageMinimal.rating 应与 ImageDetail.rating 序列化格式一致（都是 display）。"
    )


def test_preview_image_rating_handles_unknown_value(in_memory_session):
    """防御性：未知 rating 值（如 'xxx'）应降级为 Rating.R15（q）而非崩溃。

    主视图 ImageDetail.coerce_rating 已实现此容错，收藏夹预览必须保持一致。
    """
    from src.models.response.favorites import FolderPreviewImageMinimal

    # 直接测试 validator：传入未知字符串
    fake_orm = type("Fake", (), {"id": 1, "rating": "xxx"})()
    img = FolderPreviewImageMinimal.model_validate(fake_orm)
    img_dict = img.model_dump()
    assert img_dict["rating"] == "Questionable", (
        f"未知 rating 值应降级为 display 'Questionable'，实际 {img_dict['rating']!r}"
    )


def test_preview_image_rating_handles_none(in_memory_session):
    """边界：rating 为 None / 空字符串时序列化输出也应是 None。"""
    from src.models.response.favorites import FolderPreviewImageMinimal

    for null_val in [None, ""]:
        fake_orm = type("Fake", (), {"id": 1, "rating": null_val})()
        img_dict = FolderPreviewImageMinimal.model_validate(fake_orm).model_dump()
        assert img_dict["rating"] is None, (
            f"rating={null_val!r} 应序列化为 None，实际 {img_dict['rating']!r}"
        )
