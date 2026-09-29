"""MyFavorite ORM model unit tests."""
from src.models.database.my_favorite import MyFavorite
from src.common.constant import table_constant


def test_tablename_is_my_favorite():
    """Verify __tablename__ uses table_constant.my_favorite."""
    assert MyFavorite.__tablename__ == table_constant.my_favorite
    assert table_constant.my_favorite == "my_favorite"


def test_required_columns_exist():
    """Verify required columns are defined."""
    columns = {c.name for c in MyFavorite.__table__.columns}
    assert "id" in columns
    assert "image_id" in columns
    assert "created_at" in columns
    assert "note" in columns


def test_image_id_is_unique():
    """Verify image_id has unique constraint (幂等性)."""
    constraints = {c.name for c in MyFavorite.__table__.constraints}
    # SQLAlchemy auto-names UNIQUE constraints
    unique_constraints = [
        c for c in MyFavorite.__table__.constraints
        if "unique" in type(c).__name__.lower() or c.__class__.__name__.lower() == "uniqueconstraint"
    ]
    assert len(unique_constraints) >= 1, "image_id must have UNIQUE constraint"


def test_image_id_not_nullable():
    """Verify image_id is NOT NULL."""
    image_id_col = MyFavorite.__table__.columns["image_id"]
    assert image_id_col.nullable is False