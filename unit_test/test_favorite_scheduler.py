import asyncio
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from src.dao.database import _get_session_factory
from src.dao.favorite_dao import favorite_dao, FavoriteDao
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

    with FavoriteDao() as dao:
        folder = dao.create(
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


def test_run_folder_schedule_unenabled_executes_without_skip():
    """未启用 schedule 的 folder 调用 run_folder_schedule 也应执行（不跳过）

    这是 plan 2026-07-19 §3.1 改动 2 的新行为：service 层不再检查 schedule_enabled，
    是否启用 schedule 由调用方（API endpoint 或 _on_folder_trigger 防御性检查）负责。
    手动触发路径应能执行 schedule_enabled=False 的 folder。
    """
    with FavoriteDao() as dao:
        folder = dao.create(name="test_unenabled_executes", tags="x", schedule_enabled=False)
        folder_id = folder.id
    try:
        mock_response = MagicMock()
        mock_response.root = []  # 空结果快速退出 while 循环
        with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
            mock_api.return_value.get_ranking.return_value = mock_response
            from src.services.favorite_scheduler import run_folder_schedule
            stats = asyncio.run(run_folder_schedule(folder_id))

        # 关键断言：未启用 schedule 不应被跳过（这是 Task 2 的核心行为变更）
        assert stats.get("skipped") is not True, (
            f"未启用 schedule 的 folder 不应被 service 层跳过，但 stats={stats}"
        )
        # 验证 stats 正常返回（API 返回空，pages_fetched=1，无 errors）
        assert "errors" in stats
        assert stats["pages_fetched"] == 1
    finally:
        with FavoriteDao() as dao:
            dao.delete(folder_id)


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
    with FavoriteDao() as dao:
        dao.update(folder.id, schedule_max_images=1)

    item1 = MagicMock(id=6000, down_flag=False)
    item2 = MagicMock(id=6001, down_flag=False)
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
    with FavoriteDao() as dao:
        folder = dao.create(
            name="test_api_fail",
            tags="x",
            schedule_enabled=True,
            schedule_cron="0 3 * * *",
        )
        folder_id = folder.id
    try:
        with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
            mock_api.return_value.get_ranking.side_effect = Exception("api boom")
            from src.services.favorite_scheduler import run_folder_schedule
            stats = asyncio.run(run_folder_schedule(folder_id))

        assert any("api boom" in e for e in stats.get("errors", []))
        with FavoriteDao() as dao:
            reloaded = dao.get_by_id(folder_id)
        assert reloaded.last_schedule_status == "failed"
    finally:
        with FavoriteDao() as dao:
            dao.delete(folder_id)


def test_concurrent_folder_limit():
    from src.common.settings import config
    from src.services.favorite_scheduler import _schedule_semaphore

    n = config.scheduler.max_concurrent_schedules
    assert _schedule_semaphore._value == n


def test_run_folder_schedule_not_found():
    from src.services.favorite_scheduler import run_folder_schedule
    result = asyncio.run(run_folder_schedule(99999999))
    assert result == {"skipped": True, "reason": "not_found"}


def test_per_page_limit_used_from_config(folder_with_data):
    """验证 SchedulerConfig.per_page_limit 被正确传递给 yande API"""
    folder = folder_with_data
    from src.infrastructure.yande_api import YandeApi

    captured_params = []

    real_post_rank_params_cls = YandeApi.PostRankQueryParams

    with patch("src.services.favorite_scheduler.YandeApi") as mock_cls:
        mock_cls.PostRankQueryParams = real_post_rank_params_cls

        def spy_get(params):
            captured_params.append(params)
            return MagicMock(root=[])

        mock_cls.return_value.get_ranking.side_effect = spy_get

        with patch("src.services.favorite_scheduler.DownloadService.create_task"):
            from src.common.settings import Config
            from src.services.favorite_scheduler import config as fs_config, run_folder_schedule

            config_dict = fs_config.model_dump()
            config_dict["scheduler"]["per_page_limit"] = 50
            test_config = Config.model_validate(config_dict)
            assert test_config.scheduler.per_page_limit == 50

            with patch("src.services.favorite_scheduler.config", test_config):
                asyncio.run(run_folder_schedule(folder.id))

    assert len(captured_params) >= 1, "Expected get_ranking to be called"
    rank_params = captured_params[0]
    assert rank_params.limit == 50, (
        f"Expected limit=50 from config, got {rank_params.limit}"
    )


def test_run_folder_schedule_pagination_stops_on_empty():
    with FavoriteDao() as dao:
        folder = dao.create(
            name="test_empty",
            tags="x",
            schedule_enabled=True,
            schedule_cron="0 3 * * *",
        )
        folder_id = folder.id
    try:
        mock_response = MagicMock()
        mock_response.root = []
        with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
            mock_api.return_value.get_ranking.return_value = mock_response
            with patch("src.services.favorite_scheduler.DownloadService.create_task") as mock_create:
                from src.services.favorite_scheduler import run_folder_schedule
                stats = asyncio.run(run_folder_schedule(folder_id))

        assert stats["enqueued"] == 0
        assert mock_create.call_count == 0
        with FavoriteDao() as dao:
            reloaded = dao.get_by_id(folder_id)
        assert reloaded.last_schedule_status == "success"
    finally:
        with FavoriteDao() as dao:
            dao.delete(folder_id)


def test_run_folder_schedule_persists_last_synced_id(folder_with_data):
    """成功运行后，folder.last_synced_id 应被更新为本次处理过的最大 item.id。"""
    folder = folder_with_data

    item_5001 = MagicMock(id=5001, tags="test_sched_unique_tag_zzz")
    item_5002 = MagicMock(id=5002, tags="test_sched_unique_tag_zzz")
    mock_response = MagicMock()
    mock_response.root = [item_5002, item_5001]

    with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
        mock_api.return_value.get_ranking.return_value = mock_response
        with patch("src.services.favorite_scheduler.DownloadService.create_task") as mock_create:
            mock_create.return_value = asyncio.Future()
            mock_create.return_value.set_result("task_id")

            from src.services.favorite_scheduler import run_folder_schedule
            asyncio.run(run_folder_schedule(folder.id))

    with FavoriteDao() as dao:
        reloaded = dao.get_by_id(folder.id)
    assert reloaded.last_synced_id == 5002
    assert reloaded.last_schedule_status == "success"


def test_run_folder_schedule_uses_existing_last_synced_id(folder_with_data):
    """已有 last_synced_id 时，本次 run 不应再回退到 get_max_id_for_tags。"""
    folder = folder_with_data
    with FavoriteDao() as dao:
        dao.update(folder.id, last_synced_id=4999)

    item_5001 = MagicMock(id=5001, tags="test_sched_unique_tag_zzz")
    item_5002 = MagicMock(id=5002, tags="test_sched_unique_tag_zzz")
    item_4999 = MagicMock(id=4999, tags="test_sched_unique_tag_zzz")
    mock_response = MagicMock()
    mock_response.root = [item_5002, item_5001, item_4999]

    with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
        mock_api.return_value.get_ranking.return_value = mock_response
        with patch("src.services.favorite_scheduler.DownloadService.create_task") as mock_create:
            mock_create.return_value = asyncio.Future()
            mock_create.return_value.set_result("task_id")

            from src.services.favorite_scheduler import run_folder_schedule
            asyncio.run(run_folder_schedule(folder.id))

    with FavoriteDao() as dao:
        reloaded = dao.get_by_id(folder.id)
    assert reloaded.last_synced_id == 5002


def test_run_folder_schedule_first_run_max_mode_skips_fallback():
    """全量模式首次运行（last_synced_id=NULL）不调用 get_max_id_for_tags。"""
    with FavoriteDao() as dao:
        folder = dao.create(
            name="test_max_first_run",
            tags="test_max_first_run_unique_tag_zzz",
            schedule_enabled=True,
            schedule_cron="0 3 * * *",
            schedule_mode="max",
        )
        folder_id = folder.id
    try:
        with FavoriteDao() as dao:
            assert dao.get_by_id(folder_id).last_synced_id is None

        item_7000 = MagicMock(id=7000, tags="test_max_first_run_unique_tag_zzz")
        item_7001 = MagicMock(id=7001, tags="test_max_first_run_unique_tag_zzz")
        mock_response = MagicMock()
        mock_response.root = [item_7001, item_7000]

        with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
            mock_api.return_value.get_ranking.return_value = mock_response
            with patch("src.services.favorite_scheduler.DownloadService.create_task") as mock_create:
                mock_create.return_value = asyncio.Future()
                mock_create.return_value.set_result("task_id")
                with patch("src.services.favorite_scheduler.YandeDataRepository") as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.get_max_id_for_tags.return_value = None
                    mock_repo_cls.return_value.__enter__.return_value = mock_repo
                    mock_repo_cls.return_value.__exit__.return_value = False

                    from src.services.favorite_scheduler import run_folder_schedule
                    asyncio.run(run_folder_schedule(folder_id))

                    mock_repo.get_max_id_for_tags.assert_not_called()

        with FavoriteDao() as dao:
            reloaded = dao.get_by_id(folder_id)
        assert reloaded.last_synced_id == 7001
    finally:
        with FavoriteDao() as dao:
            dao.delete(folder_id)


def test_run_folder_schedule_first_run_last_id_mode_falls_back_to_max():
    """增量模式首次运行（last_synced_id=NULL）应回退到 get_max_id_for_tags。"""
    with FavoriteDao() as dao:
        folder = dao.create(
            name="test_fallback",
            tags="test_fallback_unique_tag_zzz",
            schedule_enabled=True,
            schedule_cron="0 3 * * *",
            schedule_mode="last_id",
        )
        folder_id = folder.id
    try:
        item_8000 = MagicMock(id=8000, tags="test_fallback_unique_tag_zzz")
        mock_response = MagicMock()
        mock_response.root = [item_8000]

        with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
            mock_api.return_value.get_ranking.return_value = mock_response
            with patch("src.services.favorite_scheduler.DownloadService.create_task") as mock_create:
                mock_create.return_value = asyncio.Future()
                mock_create.return_value.set_result("task_id")
                with patch("src.services.favorite_scheduler.YandeDataRepository") as mock_repo_cls:
                    mock_repo = MagicMock()
                    mock_repo.get_max_id_for_tags.return_value = 7777
                    mock_repo_cls.return_value.__enter__.return_value = mock_repo
                    mock_repo_cls.return_value.__exit__.return_value = False

                    from src.services.favorite_scheduler import run_folder_schedule
                    asyncio.run(run_folder_schedule(folder_id))

                    mock_repo.get_max_id_for_tags.assert_called_once()

        with FavoriteDao() as dao:
            reloaded = dao.get_by_id(folder_id)
        assert reloaded.last_synced_id == 8000
    finally:
        with FavoriteDao() as dao:
            dao.delete(folder_id)


def test_reset_last_synced_id_to_none_clears_value():
    with FavoriteDao() as dao:
        folder = dao.create(name="test_reset_clear", tags="x")
        folder_id = folder.id
    try:
        with FavoriteDao() as dao:
            dao.update(folder_id, last_synced_id=12345)
            assert dao.get_by_id(folder_id).last_synced_id == 12345

        with FavoriteDao() as dao:
            result = dao.reset_last_synced_id(folder_id, None)
        assert result is not None
        assert result.last_synced_id is None
    finally:
        with FavoriteDao() as dao:
            dao.delete(folder_id)


def test_reset_last_synced_id_to_value():
    with FavoriteDao() as dao:
        folder = dao.create(name="test_reset_value", tags="x")
        folder_id = folder.id
    try:
        with FavoriteDao() as dao:
            result = dao.reset_last_synced_id(folder_id, 98765)
        assert result is not None
        assert result.last_synced_id == 98765
    finally:
        with FavoriteDao() as dao:
            dao.delete(folder_id)


def test_run_folder_schedule_failure_does_not_advance_last_synced_id():
    """run 抛异常时，last_synced_id 不应被推进，下次重试从同一位置继续。"""
    with FavoriteDao() as dao:
        folder = dao.create(
            name="test_fail_no_advance",
            tags="x",
            schedule_enabled=True,
            schedule_cron="0 3 * * *",
        )
        folder_id = folder.id
    try:
        with FavoriteDao() as dao:
            dao.update(folder_id, last_synced_id=55555)

        with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
            mock_api.return_value.get_ranking.side_effect = Exception("boom")
            from src.services.favorite_scheduler import run_folder_schedule
            asyncio.run(run_folder_schedule(folder_id))

        with FavoriteDao() as dao:
            reloaded = dao.get_by_id(folder_id)
        assert reloaded.last_synced_id == 55555
        assert reloaded.last_schedule_status == "failed"
    finally:
        with FavoriteDao() as dao:
            dao.delete(folder_id)


def test_run_folder_schedule_max_images_break_advances_last_synced_id(folder_with_data):
    """max_images 限制触发 break 时，last_synced_id 应推进到本次处理过的最大 id。"""
    folder = folder_with_data
    with FavoriteDao() as dao:
        dao.update(folder.id, last_synced_id=4000, schedule_max_images=1)

    item_5001 = MagicMock(id=5001, down_flag=False, tags="test_sched_unique_tag_zzz")
    item_5002 = MagicMock(id=5002, down_flag=False, tags="test_sched_unique_tag_zzz")
    mock_response = MagicMock()
    mock_response.root = [item_5002, item_5001]

    with patch("src.services.favorite_scheduler.YandeApi") as mock_api:
        mock_api.return_value.get_ranking.return_value = mock_response
        with patch("src.services.favorite_scheduler.DownloadService.create_task") as mock_create:
            mock_create.return_value = asyncio.Future()
            mock_create.return_value.set_result("task_id")

            from src.services.favorite_scheduler import run_folder_schedule
            stats = asyncio.run(run_folder_schedule(folder.id))

    assert stats["enqueued"] == 1
    with FavoriteDao() as dao:
        reloaded = dao.get_by_id(folder.id)
    assert reloaded.last_synced_id == 5002
