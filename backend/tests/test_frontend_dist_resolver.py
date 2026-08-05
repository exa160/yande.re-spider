from pathlib import Path
from unittest.mock import patch

from src.middleware.frontend_static import resolve_frontend_dist


def test_resolve_frontend_dist_dev_mode():
    fake = Path("/repo/frontend/dist")
    with patch("src.middleware.frontend_static.path_constant") as mock_pc:
        mock_pc.frontend_dist = fake
        assert resolve_frontend_dist() == fake


def test_resolve_frontend_dist_frozen():
    with patch("sys.frozen", "true", create=True):
        with patch("sys._MEIPASS", "/install/_internal", create=True):
            result = resolve_frontend_dist()
            assert result == Path("/install/_internal/frontend/dist")
