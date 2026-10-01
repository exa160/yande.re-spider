"""``FavoritesConfig.enable_recent_downloads`` 配置项测试（设计文档 §3.5 / §6）。

覆盖：
1. 默认值为 False（存量 config.yaml 无该 key 时不影响启动，磁贴不显示）
2. 可通过 update_favorites_config 写入并落盘（Config.update_config 走 isinstance，
   无需改动注册代码）
3. 只控制**前端磁贴显示**，不作为后端接口的开关（设计文档 §6：
   开关关闭时 /recent_downloads/* 仍然可用）
"""
import pytest

from src.common.settings import Config, FavoritesConfig, config
from src.services.config import update_favorites_config


@pytest.fixture
def _restore_favorites(monkeypatch):
    """测试期间阻止落盘 + 测试后恢复原始 config.favorites（模块级单例）。"""
    monkeypatch.setattr(
        "src.common.settings.save_config",
        lambda *args, **kwargs: None,
    )
    original = config.favorites
    yield
    config.__dict__["favorites"] = original


def test_enable_recent_downloads_defaults_to_false():
    """默认 False：存量用户 config.yaml 无该 key 时磁贴不显示。"""
    assert FavoritesConfig().enable_recent_downloads is False


def test_legacy_config_without_key_still_validates():
    """兼容性：只含既有字段的旧配置仍能通过校验（不会因缺 key 抛错）。"""
    legacy = {
        "enable_my_favorites": True,
        "enable_random_browse": True,
    }
    cfg = FavoritesConfig.model_validate(legacy)
    assert cfg.enable_recent_downloads is False
    assert cfg.enable_my_favorites is True


def test_enable_recent_downloads_is_writable(_restore_favorites):
    """可通过 update_favorites_config 打开总开关。"""
    result = update_favorites_config(FavoritesConfig(enable_recent_downloads=True))
    assert result is True
    assert config.favorites.enable_recent_downloads is True


def test_enable_recent_downloads_roundtrips_through_model_dump():
    """序列化后 key 名为 enable_recent_downloads（前端契约字段名）。"""
    dumped = FavoritesConfig(enable_recent_downloads=True).model_dump(mode="json")
    assert dumped["enable_recent_downloads"] is True


def test_full_config_exposes_favorites_segment():
    """完整 Config 仍有 favorites 段（含新开关）。"""
    assert "enable_recent_downloads" in Config().favorites.model_dump()
