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
    assert c.folder_page_size == 20
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


def test_invalid_folder_page_size_raises():
    """Verify invalid folder_page_size is rejected."""
    with pytest.raises(ValidationError):
        FavoritesConfig(folder_page_size=10)


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


def test_valid_folder_page_sizes():
    """Verify all valid folder_page_size values accepted."""
    for v in (8, 12, 20):
        c = FavoritesConfig(folder_page_size=v)
        assert c.folder_page_size == v
