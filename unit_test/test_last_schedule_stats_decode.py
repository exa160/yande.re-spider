import json

from src.dao.database import _get_session_factory
from src.dao.favorite_dao import favorite_dao
from src.models.database.yande import FavoriteFolder
from src.services.favorites import FavoritesService


def test_get_all_folders_returns_dict_for_last_schedule_stats():
    session = _get_session_factory()()
    try:
        session.query(FavoriteFolder).filter(FavoriteFolder.name == "test_lss_str").delete()
        session.commit()
    finally:
        session.close()

    raw_stats = json.dumps({"new_images": 5, "enqueued": 5, "errors": []})
    folder = favorite_dao.create(name="test_lss_str", tags="catgirl")
    favorite_dao.update(folder.id, last_schedule_stats=raw_stats)

    try:
        folders = FavoritesService.get_all_folders()
        target = next(f for f in folders if f.id == folder.id)
        assert target.last_schedule_stats is not None
        assert isinstance(target.last_schedule_stats, dict), (
            f"expected dict, got {type(target.last_schedule_stats).__name__}"
        )
        assert target.last_schedule_stats["new_images"] == 5
    finally:
        favorite_dao.delete(folder.id)


def test_get_folders_with_preview_returns_dict_for_last_schedule_stats():
    session = _get_session_factory()()
    try:
        session.query(FavoriteFolder).filter(FavoriteFolder.name == "test_lss_preview").delete()
        session.commit()
    finally:
        session.close()

    raw_stats = json.dumps({"new_images": 1, "enqueued": 1, "errors": []})
    folder = favorite_dao.create(name="test_lss_preview", tags="catgirl")
    favorite_dao.update(folder.id, last_schedule_stats=raw_stats)

    try:
        folders = FavoritesService.get_folders_with_preview()
        target = next(f for f in folders if f.id == folder.id)
        assert isinstance(target.last_schedule_stats, dict), (
            f"expected dict, got {type(target.last_schedule_stats).__name__}"
        )
    finally:
        favorite_dao.delete(folder.id)


def test_get_folder_returns_dict_for_last_schedule_stats():
    session = _get_session_factory()()
    try:
        session.query(FavoriteFolder).filter(FavoriteFolder.name == "test_lss_single").delete()
        session.commit()
    finally:
        session.close()

    raw_stats = json.dumps({"new_images": 0, "enqueued": 0, "errors": []})
    folder = favorite_dao.create(name="test_lss_single", tags="catgirl")
    favorite_dao.update(folder.id, last_schedule_stats=raw_stats)

    try:
        result = FavoritesService.get_folder(folder.id)
        assert result is not None
        assert isinstance(result.last_schedule_stats, dict)
    finally:
        favorite_dao.delete(folder.id)
