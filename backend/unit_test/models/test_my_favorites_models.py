"""MyFavorites request/response Pydantic models tests."""
from src.models.response.my_favorites import (
    MyFavoritesListResponse,
    MyFavoriteCountResponse,
    MyFavoritePreviewResponse,
)


def test_count_response_has_count_field():
    """Verify MyFavoriteCountResponse has count field."""
    resp = MyFavoriteCountResponse(count=10)
    assert resp.count == 10


def test_list_response_has_required_fields():
    """Verify MyFavoritesListResponse has total/page/page_size/data."""
    resp = MyFavoritesListResponse(total=0, page=1, page_size=20, data=[])
    assert resp.total == 0
    assert resp.page == 1
    assert resp.page_size == 20
    assert resp.data == []


def test_preview_response_has_images_field():
    """Verify MyFavoritePreviewResponse has images field."""
    resp = MyFavoritePreviewResponse(images=[])
    assert resp.images == []
