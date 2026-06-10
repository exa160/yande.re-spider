import pytest

from src.infrastructure.scheduler import schedule_manager


def test_register_unregister_folder():
    schedule_manager.register_folder(
        folder_id=999,
        cron="0 3 * * *",
        mode="last_id",
        max_images=100,
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
            mode="last_id",
            max_images=100,
        )
    schedule_manager.unregister_folder(998)


def test_empty_cron_raises():
    with pytest.raises(ValueError):
        schedule_manager.register_folder(
            folder_id=997,
            cron="",
            mode="last_id",
            max_images=100,
        )


def test_invalid_mode_raises():
    with pytest.raises(ValueError):
        schedule_manager.register_folder(
            folder_id=996,
            cron="0 3 * * *",
            mode="invalid_mode",
            max_images=100,
        )
    schedule_manager.unregister_folder(996)
