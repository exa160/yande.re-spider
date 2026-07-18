import pytest

from src.dao.database import _get_session_factory
from src.dao.yande_data_dao import YandeDataRepository
from src.models.database.yande import YandeData
from datetime import datetime


@pytest.fixture
def session():
    s = _get_session_factory()()
    yield s
    s.close()


def _make_data(session, image_id: int, tags: str, down_flag: bool) -> None:
    session.query(YandeData).filter_by(id=image_id).delete()
    session.commit()
    data = YandeData(
        id=image_id,
        down_flag=down_flag,
        tags=tags,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        creator_id=0,
        author="test",
        change=0,
        source="",
        score=0,
        md5="x" * 32,
        file_size=0,
        file_ext="jpg",
        file_url="",
        is_shown_in_index=False,
        preview_url="",
        preview_width=0,
        preview_height=0,
        actual_preview_width=0,
        actual_preview_height=0,
        sample_url="",
        sample_width=0,
        sample_height=0,
        sample_file_size=0,
        jpeg_url="",
        jpeg_width=0,
        jpeg_height=0,
        jpeg_file_size=0,
        rating="s",
        is_rating_locked=False,
        has_children=False,
        parent_id=None,
        status="active",
        is_pending=False,
        width=0,
        height=0,
        is_held=False,
        is_note_locked=False,
        last_noted_at=0,
        last_commented_at=0,
    )
    session.add(data)
    session.commit()


def _cleanup_tag(session, tag: str) -> None:
    session.query(YandeData).filter(YandeData.tags.contains(tag)).delete()
    session.commit()


def test_get_max_id_for_tags_no_match(session):
    repo = YandeDataRepository(session=session)
    result = repo.get_max_id_for_tags("nonexistent_tag_xyz_zzz_exact")
    assert result is None


def test_get_max_id_for_tags_match(session):
    test_id = 99999997
    _make_data(session, test_id, "unique_test_tag_abc_zzz_exact", down_flag=True)
    repo = YandeDataRepository(session=session)
    result = repo.get_max_id_for_tags("unique_test_tag_abc_zzz_exact")
    assert result == test_id
    session.query(YandeData).filter_by(id=test_id).delete()
    session.commit()


def test_get_max_id_for_tags_empty_string(session):
    repo = YandeDataRepository(session=session)
    assert repo.get_max_id_for_tags("") is None
    assert repo.get_max_id_for_tags("   ") is None


def test_get_max_id_for_tags_only_filters_downloaded(session):
    """load 接口缓存的 down_flag=False 记录不应被计入 max(id)，避免污染增量起点。"""
    tag = "test_filter_downloaded_tag_zzz_exact"
    _cleanup_tag(session, tag)
    _make_data(session, 88800001, tag, down_flag=False)
    _make_data(session, 88800002, tag, down_flag=True)
    _make_data(session, 88800003, tag, down_flag=False)
    try:
        repo = YandeDataRepository(session=session)
        result = repo.get_max_id_for_tags(tag)
        assert result == 88800002
    finally:
        _cleanup_tag(session, tag)


def test_get_max_id_for_tags_returns_none_when_all_undownloaded(session):
    """所有匹配记录都是 down_flag=False 时返回 None（兜底为空）。"""
    tag = "test_all_undownloaded_tag_zzz_exact"
    _cleanup_tag(session, tag)
    _make_data(session, 88800010, tag, down_flag=False)
    _make_data(session, 88800011, tag, down_flag=False)
    try:
        repo = YandeDataRepository(session=session)
        result = repo.get_max_id_for_tags(tag)
        assert result is None
    finally:
        _cleanup_tag(session, tag)
