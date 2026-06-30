from datetime import datetime

import pytest

from src.common.constant import Rating
from src.models.response.gallery import ImageDetail


def _make_detail(**overrides):
    base = dict(
        id=1,
        tags=["tag1"],
        width=100,
        height=100,
        rating="q",
        file_url="http://x/1.jpg",
        preview_url="http://x/p_1.jpg",
        file_size=1000,
        file_ext="jpg",
        author="alice",
        created_at=datetime(2024, 1, 1),
        md5="abc123",
        score=None,
        down_flag=True,
    )
    base.update(overrides)
    return ImageDetail(**base)


class TestImageDetailRating:
    @pytest.mark.parametrize("raw,expected", [
        ("s", Rating.S),
        ("q", Rating.R15),
        ("e", Rating.R18),
    ])
    def test_known_rating(self, raw, expected):
        assert _make_detail(rating=raw).rating == expected

    def test_rating_none_accepted(self):
        assert _make_detail(rating=None).rating is None

    def test_rating_empty_string_accepted(self):
        assert _make_detail(rating="").rating is None

    def test_unknown_rating_defaults_to_r15(self):
        assert _make_detail(rating="x").rating == Rating.R15
