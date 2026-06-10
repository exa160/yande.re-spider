import asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from src.dao.database import _get_session_factory
from src.dao.favorite_dao import favorite_dao
from src.models.database.yande import FavoriteFolder, YandeData


@pytest.fixture(autouse=True)
def _isolate_event_loop():
    import asyncio
    from src.infrastructure.scheduler import schedule_manager

    policy = asyncio.DefaultEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    schedule_manager._scheduler = None
    schedule_manager._job_folder_map = {}
    yield
    schedule_manager._scheduler = None
    schedule_manager._job_folder_map = {}
    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if loop and not loop.is_closed():
            loop.close()
    except Exception:
        pass
    asyncio.set_event_loop_policy(None)
    asyncio.set_event_loop(None)


@pytest.fixture
def folder_with_data():
    session = _get_session_factory()()
    session.query(FavoriteFolder).filter(FavoriteFolder.name == "test_sched").delete()
    session.query(YandeData).filter(YandeData.tags.contains("test_sched_unique_tag_zzz")).delete()
    session.commit()
    session.close()

    folder = favorite_dao.create(
        name="test_sched",
        tags="test_sched_unique_tag_zzz",
        schedule_enabled=True,
        schedule_cron="* * * * *",
        schedule_mode="last_id",
        schedule_max_images=10,
    )
    session = _get_session_factory()()
    data = YandeData(
        id=5000,
        down_flag=True,
        tags="test_sched_unique_tag_zzz other",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        creator_id=0, author="test", change=0, source="", score=0,
        md5="x" * 32, file_size=0, file_ext="jpg", file_url="",
        is_shown_in_index=False, preview_url="", preview_width=0, preview_height=0,
        actual_preview_width=0, actual_preview_height=0,
        sample_url="", sample_width=0, sample_height=0, sample_file_size=0,
        jpeg_url="", jpeg_width=0, jpeg_height=0, jpeg_file_size=0,
        rating="s", is_rating_locked=False, has_children=False, parent_id=None,
        status="active", is_pending=False, width=0, height=0, is_held=False,
        is_note_locked=False, last_noted_at=0, last_commented_at=0,
    )
    session.add(data)
    session.commit()
    session.close()

    yield folder

    session = _get_session_factory()()
    session.query(FavoriteFolder).filter(FavoriteFolder.name == "test_sched").delete()
    session.query(YandeData).filter(YandeData.tags.contains("test_sched_unique_tag_zzz")).delete()
    session.commit()
    session.close()


def test_run_folder_schedule_disabled_skips():
    folder = favorite_dao.create(name="test_disabled", tags="x", schedule_enabled=False)
    try:
        from src.services.favorite_scheduler import run_folder_schedule
        result = asyncio.run(run_folder_schedule(folder.id))
        assert result.get("skipped") is True
    finally:
        favorite_dao.delete(folder.id)


def test_run_folder_schedule_last_id_stops(folder_with_data):
    folder = folder_with_data

    item_5001 = MagicMock(id=5001, tags="test_sched_unique_tag_zzz")
    item_5002 = MagicMock(id=5002, tags="test_sched_unique_tag_zzz")
    item_3000 = MagicMock(id=3000, tags="test_sched_unique_tag_zzz")
    mock_response = MagicMock()
    mock_response.root = [item_5001, item_5002, item_3000]

    with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
        mock_api.return_value.get_ranking.return_value = mock_response
        with patch("src.services.favorite_scheduler.DownloadService.create_task") as mock_create:
            mock_create.return_value = asyncio.Future()
            mock_create.return_value.set_result("task_id")

            from src.services.favorite_scheduler import run_folder_schedule
            stats = asyncio.run(run_folder_schedule(folder.id))

    assert "errors" in stats
    assert stats["enqueued"] >= 1
    assert stats["enqueued"] <= 2
    assert mock_create.call_count >= 1
    assert mock_create.call_count <= 2


def test_run_folder_schedule_max_images_limit(folder_with_data):
    folder = folder_with_data
    favorite_dao.update(folder.id, schedule_max_images=1)

    item1 = MagicMock(id=6000)
    item2 = MagicMock(id=6001)
    mock_response = MagicMock()
    mock_response.root = [item1, item2]

    with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
        mock_api.return_value.get_ranking.return_value = mock_response
        with patch("src.services.favorite_scheduler.DownloadService.create_task") as mock_create:
            mock_create.return_value = asyncio.Future()
            mock_create.return_value.set_result("task_id")

            from src.services.favorite_scheduler import run_folder_schedule
            stats = asyncio.run(run_folder_schedule(folder.id))

    assert stats["enqueued"] == 1


def test_yande_api_failure_sets_failed_status():
    folder = favorite_dao.create(
        name="test_api_fail",
        tags="x",
        schedule_enabled=True,
        schedule_cron="0 3 * * *",
    )
    try:
        with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
            mock_api.return_value.get_ranking.side_effect = Exception("api boom")
            from src.services.favorite_scheduler import run_folder_schedule
            stats = asyncio.run(run_folder_schedule(folder.id))

        assert any("api boom" in e for e in stats.get("errors", []))
        reloaded = favorite_dao.get_by_id(folder.id)
        assert reloaded.last_schedule_status == "failed"
    finally:
        favorite_dao.delete(folder.id)


def test_concurrent_folder_limit():
    from src.common.settings import config
    from src.services.favorite_scheduler import _schedule_semaphore

    n = config.scheduler.max_concurrent_schedules
    assert _schedule_semaphore._value == n


def test_run_folder_schedule_not_found():
    from src.services.favorite_scheduler import run_folder_schedule
    result = asyncio.run(run_folder_schedule(99999999))
    assert result == {"skipped": True, "reason": "not_found"}


def test_run_folder_schedule_pagination_stops_on_empty():
    folder = favorite_dao.create(
        name="test_empty",
        tags="x",
        schedule_enabled=True,
        schedule_cron="0 3 * * *",
    )
    try:
        mock_response = MagicMock()
        mock_response.root = []
        with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
            mock_api.return_value.get_ranking.return_value = mock_response
            with patch("src.services.favorite_scheduler.DownloadService.create_task") as mock_create:
                from src.services.favorite_scheduler import run_folder_schedule
                stats = asyncio.run(run_folder_schedule(folder.id))

        assert stats["enqueued"] == 0
        assert mock_create.call_count == 0
        reloaded = favorite_dao.get_by_id(folder.id)
        assert reloaded.last_schedule_status == "success"
    finally:
        favorite_dao.delete(folder.id)
