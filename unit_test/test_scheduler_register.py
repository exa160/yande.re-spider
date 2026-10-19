"""register_folder 的签名与校验守卫。

设计文档 §4.2：`mode` / `max_images` 两个旋钮已下线，`register_folder`
现在只接受 `(folder_id, cron)`，非法 cron 仍然抛 ValueError。
"""
import inspect

import pytest

from src.infrastructure.scheduler import schedule_manager


def test_register_unregister_folder():
    schedule_manager.register_folder(
        folder_id=999,
        cron="0 3 * * *",
    )
    jobs = schedule_manager.get_all_jobs()
    assert any(j["folder_id"] == 999 for j in jobs)

    schedule_manager.unregister_folder(999)
    jobs = schedule_manager.get_all_jobs()
    assert not any(j["folder_id"] == 999 for j in jobs)


def test_invalid_cron_raises():
    with pytest.raises(ValueError):
        schedule_manager.register_folder(
            folder_id=998,
            cron="invalid cron",
        )
    schedule_manager.unregister_folder(998)


def test_empty_cron_raises():
    with pytest.raises(ValueError):
        schedule_manager.register_folder(
            folder_id=997,
            cron="",
        )


def test_register_folder_signature_has_only_folder_id_and_cron():
    """§4.2：`mode` / `max_images` 已下线，签名里不允许再出现这两个形参。"""
    params = inspect.signature(schedule_manager.register_folder).parameters

    assert list(params) == ["folder_id", "cron"], (
        f"register_folder 签名应恰为 (folder_id, cron)，实际为 {list(params)}"
    )
    assert "mode" not in params
    assert "max_images" not in params

    # 且调用方不可能再传这两个 kwarg（传了直接 TypeError）
    with pytest.raises(TypeError):
        schedule_manager.register_folder(
            folder_id=996,
            cron="0 3 * * *",
            mode="invalid_mode",  # type: ignore[call-arg]
            max_images=100,  # type: ignore[call-arg]
        )
