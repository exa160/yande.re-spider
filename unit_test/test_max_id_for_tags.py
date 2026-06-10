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


def test_get_max_id_for_tags_no_match(session):
    repo = YandeDataRepository(session=session)
    result = repo.get_max_id_for_tags("nonexistent_tag_xyz_zzz")
    assert result is None


def test_get_max_id_for_tags_match(session):
    test_id = 99999997
    session.query(YandeData).filter_by(id=test_id).delete()
    session.commit()
    data = YandeData(
        id=test_id,
        down_flag=False,
        tags="unique_test_tag_abc_zzz",
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

    repo = YandeDataRepository(session=session)
    result = repo.get_max_id_for_tags("unique_test_tag_abc_zzz")
    assert result == test_id

    session.query(YandeData).filter_by(id=test_id).delete()
    session.commit()


def test_get_max_id_for_tags_empty_string(session):
    repo = YandeDataRepository(session=session)
    assert repo.get_max_id_for_tags("") is None
    assert repo.get_max_id_for_tags("   ") is None
