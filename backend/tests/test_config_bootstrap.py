from pathlib import Path

from src.common.config_bootstrap import write_default_user_config


def test_write_default_user_config_creates_file(tmp_path):
    target = tmp_path / "config.yaml"
    write_default_user_config(target)
    content = target.read_text(encoding="utf-8")
    assert "password: ''" in content
    assert "proxy_enable: false" in content
    assert "yande_api" in content
    assert "downloader" in content


def test_write_default_user_config_idempotent(tmp_path):
    target = tmp_path / "config.yaml"
    target.write_text("database:\n  enable: true\n", encoding="utf-8")
    write_default_user_config(target)
    assert target.read_text(encoding="utf-8") == "database:\n  enable: true\n"
