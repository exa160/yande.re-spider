"""FavoritesConfig Pydantic model tests."""
import pytest
from pydantic import ValidationError

from src.common.settings import FavoritesConfig


def test_default_values():
    """Verify default values match spec."""
    c = FavoritesConfig()
    assert c.button_mode == "shown"
    assert c.tile_size == "adaptive"
    assert c.preview_order == "random"
    assert c.include_online is False
    assert c.enable_my_favorites is False
    assert c.enable_random_browse is False
    assert c.enable_favorite_folder is True
    assert c.enable_favorite_autodownload is True


def test_invalid_button_mode_raises():
    """Verify invalid button_mode is rejected."""
    with pytest.raises(ValidationError):
        FavoritesConfig(button_mode="invalid")


def test_invalid_tile_size_raises():
    """Verify invalid tile_size is rejected."""
    with pytest.raises(ValidationError):
        FavoritesConfig(tile_size="5")


def test_invalid_preview_order_raises():
    """Verify invalid preview_order is rejected."""
    with pytest.raises(ValidationError):
        FavoritesConfig(preview_order="ascending")


def test_valid_button_modes():
    """Verify all valid button_mode values accepted."""
    for v in ("hidden", "shown", "default"):
        c = FavoritesConfig(button_mode=v)
        assert c.button_mode == v


def test_valid_tile_sizes():
    """Verify all valid tile_size values accepted."""
    for v in ("adaptive", "4", "6", "8"):
        c = FavoritesConfig(tile_size=v)
        assert c.tile_size == v



def test_folder_page_size_field_removed():
    """收藏夹「每页个数」已移除：每页条数由前端按列数自动推导。

    后端不再持有该字段（配置里的残留 key 由 pydantic extra='ignore' 静默丢弃）。
    """
    c = FavoritesConfig()
    assert not hasattr(c, "folder_page_size")
    # 旧配置文件里的残留键不应导致校验失败
    c2 = FavoritesConfig(**{"folder_page_size": 20})
    assert not hasattr(c2, "folder_page_size")
