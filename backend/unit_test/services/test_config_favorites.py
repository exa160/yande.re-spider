"""ConfigService favorites methods tests.

覆盖：
1. get_favorites_config(): 返回 config.favorites 实例
2. update_favorites_config(): 修改 config.favorites 并落盘

实现说明：
- update 会触发 save_config(self, path_constant.config_file) 写盘，本地默认
  路径是 ~/.config/yande-spider/config/config.yaml。为避免污染用户配置，
  monkeypatch save_config 为 no-op，测试结束后自动还原。
- 测试结束时显式恢复 config.favorites 到原值，避免污染同进程后续测试
  (Config 是模块级单例)。
"""
import pytest

from src.common.settings import FavoritesConfig, config
from src.services.config import update_favorites_config


@pytest.fixture
def _restore_favorites(monkeypatch):
    """测试期间阻止落盘 + 测试后恢复原始 config.favorites。
    
    monkeypatch.setattr 在 fixture 结束时自动还原。
    """
    # 阻止真实写盘到 ~/.config/yande-spider/config/config.yaml
    monkeypatch.setattr(
        "src.common.settings.save_config",
        lambda *args, **kwargs: None,
    )
    # 备份当前 favorites，跑完后恢复
    original = config.favorites
    yield
    config.__dict__["favorites"] = original


def test_get_favorites_config_returns_config():
    """Verify get_favorites_config returns the config.favorites instance."""
    from src.services.config import get_favorites_config

    cfg = get_favorites_config()
    assert isinstance(cfg, FavoritesConfig)
    assert cfg is config.favorites


def test_update_favorites_config_succeeds(_restore_favorites):
    """Verify update_favorites_config writes successfully."""
    new_cfg = FavoritesConfig(enable_my_favorites=True)
    result = update_favorites_config(new_cfg)
    assert result is True
    assert config.favorites.enable_my_favorites is True
