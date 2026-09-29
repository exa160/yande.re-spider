"""MyFavoriteDao unit tests."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.dao.database import Base
from src.dao.my_favorite_dao import MyFavoriteDao
from src.models.database.my_favorite import MyFavorite


@pytest.fixture
def session():
    """In-memory SQLite session with Base metadata."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    s = Session()
    yield s
    s.close()


def test_add_inserts_row(session):
    """Verify add() inserts a new row."""
    MyFavoriteDao.add(session, image_id=42)
    rows = session.query(MyFavorite).all()
    assert len(rows) == 1
    assert rows[0].image_id == 42


def test_add_is_idempotent(session):
    """Verify add() with same image_id does not raise (UNIQUE constraint)."""
    MyFavoriteDao.add(session, image_id=42)
    MyFavoriteDao.add(session, image_id=42)  # 二次调用
    rows = session.query(MyFavorite).all()
    assert len(rows) == 1


def test_count_returns_zero_when_empty(session):
    """Verify count() returns 0 when no records."""
    assert MyFavoriteDao.count(session) == 0


def test_count_returns_correct_count(session):
    """Verify count() returns correct number."""
    MyFavoriteDao.add(session, image_id=1)
    MyFavoriteDao.add(session, image_id=2)
    MyFavoriteDao.add(session, image_id=3)
    assert MyFavoriteDao.count(session) == 3


def test_remove_deletes_row(session):
    """Verify remove() deletes the row."""
    MyFavoriteDao.add(session, image_id=42)
    MyFavoriteDao.remove(session, image_id=42)
    assert MyFavoriteDao.count(session) == 0


def test_remove_is_idempotent(session):
    """Verify remove() on non-existent image_id does not raise."""
    MyFavoriteDao.remove(session, image_id=999)  # 不存在
    assert MyFavoriteDao.count(session) == 0


def test_list_paginated_returns_records_in_desc_order(session):
    """Verify list_paginated returns records ordered by created_at DESC."""
    import time
    MyFavoriteDao.add(session, image_id=1)
    time.sleep(0.01)
    MyFavoriteDao.add(session, image_id=2)
    time.sleep(0.01)
    MyFavoriteDao.add(session, image_id=3)

    rows = MyFavoriteDao.list_paginated(session, page=1, page_size=10)
    assert [r.image_id for r in rows] == [3, 2, 1]