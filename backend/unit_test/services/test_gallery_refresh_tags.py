"""GalleryService.refresh_image_tags — 从 yande.re 更新本地标签。

覆盖：
1. 本地图片不存在 → 404
2. 本地 tags 不含 tagme → 400（唯一入口约束）
3. 远端不存在 → 404
4. 成功：远端 tags 整串覆盖本地，返回 added/removed；已下载图片同步本地统计
5. 远端 tags 与本地集合相同 → changed=False，不写库
6. 远端仍是 tagme → still_tagme=True，便于前端提示
"""
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.common.constant import ErrMsg, Rating
from src.dao.database import Base
from src.middleware.errors import APIException
from src.middleware.session import _request_session
from src.models.database.yande import TagLocalStats, YandeData, YandeTag
from src.services.gallery import GalleryService


@pytest.fixture
def in_memory_session(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, expire_on_commit=False)
    session = TestSession()
    token = _request_session.set(session)
    monkeypatch.setattr("src.dao.database._get_session_factory", lambda: TestSession)
    try:
        yield session
    finally:
        _request_session.reset(token)
        session.close()


def _seed_image(sess, image_id=42, tags="tagme old", down_flag=True):
    record = YandeData(
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
        updated_at=datetime(2024, 1, 1),
        down_flag=down_flag,
        rating=Rating.S,
    )
    sess.add(record)
    return record


def _mock_remote(monkeypatch, tags, updated_at=datetime(2026, 1, 2)):
    post = SimpleNamespace(tags=tags, updated_at=updated_at)
    monkeypatch.setattr(
        "src.services.gallery.YandeApi.get_post_by_id",
        lambda self, image_id: post,
    )
    return post


def test_refresh_rejects_missing_local_image(in_memory_session):
    with pytest.raises(APIException) as exc:
        GalleryService.refresh_image_tags(404)
    assert exc.value.err_code == ErrMsg.IMAGE_TAG_REFRESH_NOT_FOUND.code


def test_refresh_rejects_image_without_tagme(in_memory_session):
    _seed_image(in_memory_session, tags="foo bar")
    with pytest.raises(APIException) as exc:
        GalleryService.refresh_image_tags(42)
    assert exc.value.err_code == ErrMsg.IMAGE_TAG_REFRESH_NOT_ALLOWED.code


def test_refresh_reports_remote_missing(in_memory_session, monkeypatch):
    _seed_image(in_memory_session)
    monkeypatch.setattr(
        "src.services.gallery.YandeApi.get_post_by_id",
        lambda self, image_id: None,
    )
    with pytest.raises(APIException) as exc:
        GalleryService.refresh_image_tags(42)
    assert exc.value.err_code == ErrMsg.REMOTE_IMAGE_NOT_FOUND.code


def test_refresh_overwrites_tags_and_updates_local_stats(in_memory_session, monkeypatch):
    record = _seed_image(in_memory_session, tags="tagme old")
    remote = _mock_remote(monkeypatch, "new old other")

    # 本地标签缓存：tagme / old 有统计；new 有缓存但无统计；other 不在缓存
    in_memory_session.add_all([
        YandeTag(id=1, name="tagme", count=10, type=0),
        YandeTag(id=2, name="old", count=10, type=0),
        YandeTag(id=3, name="new", count=10, type=0),
    ])
    in_memory_session.add_all([
        TagLocalStats(tag_id=1, local_count=3),
        TagLocalStats(tag_id=2, local_count=5),
    ])
    in_memory_session.flush()

    result = GalleryService.refresh_image_tags(42)

    assert record.tags == "new old other"
    assert record.updated_at == remote.updated_at
    assert result == {
        "image_id": 42,
        "tags": ["new", "old", "other"],
        "added": ["new", "other"],
        "removed": ["tagme"],
        "changed": True,
        "still_tagme": False,
    }

    stats = {
        row.tag_id: row.local_count
        for row in in_memory_session.execute(select(TagLocalStats)).scalars().all()
    }
    assert stats[1] == 2  # tagme 3 → 2
    assert stats[2] == 5  # old 不变
    assert stats[3] == 1  # new 新建统计


def test_refresh_unchanged_tags_does_not_write(in_memory_session, monkeypatch):
    record = _seed_image(in_memory_session, tags="tagme old")
    _mock_remote(monkeypatch, "old tagme")  # 集合相同，仅顺序不同

    result = GalleryService.refresh_image_tags(42)

    assert result["changed"] is False
    assert result["added"] == []
    assert result["removed"] == []
    assert record.tags == "tagme old"
    assert record.updated_at == datetime(2024, 1, 1)


def test_refresh_reports_still_tagme(in_memory_session, monkeypatch):
    _seed_image(in_memory_session, tags="tagme old")
    _mock_remote(monkeypatch, "tagme old new")

    result = GalleryService.refresh_image_tags(42)

    assert result["still_tagme"] is True
    assert result["added"] == ["new"]
