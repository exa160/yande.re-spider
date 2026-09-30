"""标签缓存定时增量刷新（config.tag_cache + APScheduler job）

背景：标签面板的「/ yande M」来自 yande_tags.count（yande.re 远端数据），
此前只能靠 Config.vue 手动刷新，没有任何自动保鲜。本组测试锁定：

1. TagCacheConfig：默认值 + cron 校验（非法表达式写不进配置）
2. ScheduleManager：注册/卸载/幂等替换，非法 cron 抛 ValueError
3. SchedulerLifecycle.reload_tag_cache_schedule：按开关挂载，幂等，异常不炸
4. 触发入口 _on_tag_cache_trigger：走增量分支、开关关闭时跳过并清 job、失败不抛
"""
import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.common.settings import TagCacheConfig
from src.infrastructure.scheduler import ScheduleManager


# ============================================================
# Config
# ============================================================


def test_tag_cache_defaults():
    cfg = TagCacheConfig()
    assert cfg.enable_daily_refresh is True
    assert cfg.refresh_cron == "17 4 * * *"
    assert cfg.batch_limit == 100


def test_config_exposes_tag_cache_section():
    from src.common.settings import Config

    assert isinstance(Config().tag_cache, TagCacheConfig)


@pytest.mark.parametrize("bad", ["", "   ", "not a cron", "1 2 3", "99 99 99 99 99"])
def test_invalid_cron_rejected(bad):
    with pytest.raises(ValueError):
        TagCacheConfig(refresh_cron=bad)


def test_cron_is_stripped():
    assert TagCacheConfig(refresh_cron="  30 5 * * *  ").refresh_cron == "30 5 * * *"


@pytest.mark.parametrize("bad_limit", [0, -1, 1001])
def test_batch_limit_bounds(bad_limit):
    with pytest.raises(ValueError):
        TagCacheConfig(batch_limit=bad_limit)


# ============================================================
# ScheduleManager
# ============================================================


@pytest.fixture
def manager():
    """未 start 的 ScheduleManager。

    AsyncIOScheduler.start() 需要事件循环，同步 fixture 起不来；不 start 反而
    更好：此时 APScheduler 会把 job 放进 _pending_jobs，正是 replace_existing
    去重失效的场景 —— 用例锁的是「无论是否已 start 都不重复注册」这条保证。
    """
    mgr = ScheduleManager()
    yield mgr
    mgr.shutdown(wait=False)


def test_register_tag_cache_refresh_adds_job(manager):
    manager.register_tag_cache_refresh("17 4 * * *", batch_limit=200)
    assert manager.has_tag_cache_refresh()
    jobs = [j for j in manager.get_all_jobs() if j["job_id"] == ScheduleManager.TAG_CACHE_JOB_ID]
    assert len(jobs) == 1
    # 收藏夹 job 的命名空间不被污染
    assert jobs[0]["folder_id"] is None


def test_register_is_idempotent_replace_existing(manager):
    manager.register_tag_cache_refresh("17 4 * * *")
    manager.register_tag_cache_refresh("30 5 * * *")
    jobs = [j for j in manager.get_all_jobs() if j["job_id"] == ScheduleManager.TAG_CACHE_JOB_ID]
    assert len(jobs) == 1
    # 第二次注册的 cron 生效（不是仍停在第一次的 04:17）
    assert "hour='5'" in jobs[0]["trigger"] and "minute='30'" in jobs[0]["trigger"]


def test_unregister_tag_cache_refresh(manager):
    manager.register_tag_cache_refresh("17 4 * * *")
    assert manager.unregister_tag_cache_refresh() is True
    assert not manager.has_tag_cache_refresh()


def test_unregister_when_absent_is_false_not_crash(manager):
    assert manager.unregister_tag_cache_refresh() is False


def test_register_rejects_invalid_cron(manager):
    with pytest.raises(ValueError):
        manager.register_tag_cache_refresh("nope")


def test_register_rejects_non_positive_batch_limit(manager):
    with pytest.raises(ValueError):
        manager.register_tag_cache_refresh("17 4 * * *", batch_limit=0)


# ============================================================
# SchedulerLifecycle.reload_tag_cache_schedule
# ============================================================


def _cfg(enabled: bool, cron: str = "17 4 * * *", limit: int = 100):
    return TagCacheConfig(
        enable_daily_refresh=enabled, refresh_cron=cron, batch_limit=limit
    )


def _fake_config(tag_cache: TagCacheConfig):
    """config 是 frozen pydantic model，patch 属性会抛 frozen_instance，
    只能整体替换 src.common.config 这个名字。"""
    return SimpleNamespace(tag_cache=tag_cache)


def test_reload_registers_when_enabled(manager):
    from src.lifecycle.scheduler import SchedulerLifecycle

    with patch("src.lifecycle.scheduler.schedule_manager", manager), patch("src.common.config", _fake_config(_cfg(True, "30 5 * * *", 250))):
        SchedulerLifecycle.reload_tag_cache_schedule()

    assert manager.has_tag_cache_refresh()
    jobs = [j for j in manager.get_all_jobs() if j["job_id"] == ScheduleManager.TAG_CACHE_JOB_ID]
    assert len(jobs) == 1


def test_reload_unregisters_when_disabled(manager):
    from src.lifecycle.scheduler import SchedulerLifecycle

    manager.register_tag_cache_refresh("17 4 * * *")
    with patch("src.lifecycle.scheduler.schedule_manager", manager), patch("src.common.config", _fake_config(_cfg(False))):
        SchedulerLifecycle.reload_tag_cache_schedule()

    assert not manager.has_tag_cache_refresh()


def test_reload_is_idempotent(manager):
    from src.lifecycle.scheduler import SchedulerLifecycle

    with patch("src.lifecycle.scheduler.schedule_manager", manager), patch("src.common.config", _fake_config(_cfg(True))):
        SchedulerLifecycle.reload_tag_cache_schedule()
        SchedulerLifecycle.reload_tag_cache_schedule()

    jobs = [j for j in manager.get_all_jobs() if j["job_id"] == ScheduleManager.TAG_CACHE_JOB_ID]
    assert len(jobs) == 1


def test_reload_survives_invalid_config_cron(manager):
    """配置里的 cron 被改坏（或手工编辑 yaml 写错）时不应抛到调用方。"""
    from src.lifecycle.scheduler import SchedulerLifecycle

    # 直接构造一个绕过 validator 的坏配置（模拟手改 yaml 写进非法 cron）
    bad = _cfg(True)
    object.__setattr__(bad, "refresh_cron", "broken cron")
    with patch("src.lifecycle.scheduler.schedule_manager", manager), patch(
        "src.common.config", _fake_config(bad)
    ):
        SchedulerLifecycle.reload_tag_cache_schedule()  # 不抛即通过

    assert not manager.has_tag_cache_refresh()


# ============================================================
# 触发入口
# ============================================================


def test_trigger_calls_incremental_refresh():
    from src.infrastructure import scheduler as sched

    mock_cls = MagicMock()
    mock_cls.refresh_tags.return_value = {"success": True, "total_updated": 3}
    with patch("src.services.tag_cache.TagCacheService", mock_cls), patch(
        "src.common.config", _fake_config(_cfg(True))
    ):
        asyncio.run(sched._on_tag_cache_trigger(100))

    # full_refresh=False → 增量分支（表空时 service 自己转全量）
    mock_cls.refresh_tags.assert_called_once_with(100, False)


def test_trigger_skips_and_cleans_job_when_disabled(manager):
    from src.infrastructure import scheduler as sched

    manager.register_tag_cache_refresh("17 4 * * *")
    mock_cls = MagicMock()
    with patch("src.infrastructure.scheduler.schedule_manager", manager), patch(
        "src.services.tag_cache.TagCacheService", mock_cls
    ), patch("src.common.config", _fake_config(_cfg(False))):
        asyncio.run(sched._on_tag_cache_trigger(100))

    mock_cls.refresh_tags.assert_not_called()
    assert not manager.has_tag_cache_refresh()  # 残留 job 被清理


def test_trigger_failure_is_swallowed():
    """刷新失败不能把 APScheduler 的 job 掀翻。"""
    from src.infrastructure import scheduler as sched

    mock_cls = MagicMock()
    mock_cls.refresh_tags.side_effect = RuntimeError("yande.re down")
    with patch("src.services.tag_cache.TagCacheService", mock_cls), patch(
        "src.common.config", _fake_config(_cfg(True))
    ):
        asyncio.run(sched._on_tag_cache_trigger(100))  # 不抛即通过
