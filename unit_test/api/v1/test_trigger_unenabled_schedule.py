"""验证 trigger_folder_schedule 解除 schedule_enabled 限制后的行为 + _on_folder_trigger 防御性清理残留 job

测试覆盖（plan 2026-07-19 §4 AC-13/14 + §5）：
- AC-13: 未启用 schedule 的 folder 也能触发（不再被 SCHEDULE_DISABLED 拒绝）
- AC-14: 不存在的 folder 仍抛 FAVORITE_FOLDER_NOT_FOUND
- 残留 job 防御性清理：定时入口对 schedule_enabled=False / 已删除 folder 自动 unregister
"""
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[3] / "backend"
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from src.api.v1.favorites import trigger_folder_schedule
from src.common.constant import ErrMsg
from src.dao.favorite_dao import FavoriteDao
from src.infrastructure.scheduler import _on_folder_trigger, schedule_manager
from src.middleware.errors import APIException


@pytest.fixture(autouse=True)
def _isolate_event_loop():
    """每个测试前后重置 schedule_manager 与 event loop 状态（与 test_favorite_scheduler.py 同款）"""
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


def _create_test_folder(name: str, schedule_enabled: bool = False, tags: str = "cat") -> int:
    """创建测试用收藏夹，返回 id"""
    with FavoriteDao() as dao:
        folder = dao.create(
            name=name,
            tags=tags,
            color="#409EFF",
            icon="folder",
            sort_order=999,
            schedule_enabled=schedule_enabled,
            schedule_cron="",
            schedule_mode="last_id",
            schedule_max_images=None,
        )
        return folder.id


def _delete_test_folder(folder_id: int) -> None:
    """清理测试用收藏夹"""
    with FavoriteDao() as dao:
        dao.delete(folder_id)


class TestTriggerScheduleDisabled:
    """未启用 schedule 的 folder 也能触发（不再被 SCHEDULE_DISABLED 拒绝）"""

    def test_trigger_unenabled_schedule_does_not_raise_schedule_disabled(self):
        """核心：未启用 schedule 的 folder 触发不应抛 SCHEDULE_DISABLED（plan §4 AC-13）

        之前 API 路径会抛 APIException(ErrMsg.SCHEDULE_DISABLED)，
        Task 1 解除了该限制，未启用 schedule 的 folder 也允许手动触发。
        """
        folder_id = _create_test_folder("test_unenabled", schedule_enabled=False)
        try:
            # trigger_folder_schedule 内部用 `from src.services.favorite_scheduler import run_folder_schedule`
            # 每次调用都会重新查表，因此 patch 模块属性在下次调用时即可生效
            with patch(
                "src.services.favorite_scheduler.run_folder_schedule",
                new_callable=AsyncMock,
            ) as mock_run:
                result = asyncio.run(trigger_folder_schedule(folder_id))

            assert result is not None
            assert result.data.status == "queued"
            mock_run.assert_called_once_with(folder_id)
        finally:
            _delete_test_folder(folder_id)

    def test_trigger_not_found_still_raises(self):
        """不存在的 folder 仍应抛 FAVORITE_FOLDER_NOT_FOUND（plan §4 AC-14）

        解除 SCHEDULE_DISABLED 限制不等于吞掉所有错误，
        对不存在的 folder_id 必须仍返回 2404 FAVORITE_FOLDER_NOT_FOUND。
        """
        with pytest.raises(APIException) as exc_info:
            asyncio.run(trigger_folder_schedule(99999999))

        # APIException.err_msg 是字符串（来自 ErrMsg.msg），不是枚举本身
        assert exc_info.value.err_msg == ErrMsg.FAVORITE_FOLDER_NOT_FOUND.msg
        assert exc_info.value.err_code == ErrMsg.FAVORITE_FOLDER_NOT_FOUND.code


class TestOnFolderTriggerDefense:
    """_on_folder_trigger 定时入口防御性检查（残留 job 清理）"""

    def test_on_folder_trigger_skips_disabled_folder(self):
        """残留 job 触发 schedule_enabled=False 的 folder 时跳过并清理（plan §5）

        模拟场景：用户在 UI 禁用了 schedule，但 APScheduler 中仍有遗留 job，
        触发时应跳过并清理残留 job，避免无限循环触发已禁用的 folder。
        """
        folder_id = _create_test_folder("test_residual", schedule_enabled=False)
        try:
            schedule_manager.register_folder(
                folder_id=folder_id,
                cron="0 3 * * *",
                mode="last_id",
                max_images=None,
            )
            assert folder_id in schedule_manager._job_folder_map.values()

            asyncio.run(_on_folder_trigger(folder_id))

            assert folder_id not in schedule_manager._job_folder_map.values(), (
                "残留 job 应被清理，但仍然存在"
            )
        finally:
            # 防御性清理：unregister_folder 对不存在的 job 是幂等的
            schedule_manager.unregister_folder(folder_id)
            _delete_test_folder(folder_id)

    def test_on_folder_trigger_skips_nonexistent_folder(self):
        """残留 job 指向已删除的 folder 时跳过并清理（plan §5）

        模拟场景：folder 在 DB 中已被删除，但 APScheduler 中仍有遗留 job，
        触发时应跳过并清理残留 job。
        """
        nonexistent_id = 99999998
        schedule_manager.register_folder(
            folder_id=nonexistent_id,
            cron="0 3 * * *",
            mode="last_id",
            max_images=None,
        )
        assert nonexistent_id in schedule_manager._job_folder_map.values()

        asyncio.run(_on_folder_trigger(nonexistent_id))

        assert nonexistent_id not in schedule_manager._job_folder_map.values(), (
            "残留 job 应被清理，但仍然存在"
        )
        schedule_manager.unregister_folder(nonexistent_id)