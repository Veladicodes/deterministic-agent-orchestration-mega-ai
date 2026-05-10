import pytest

from shared.settings import Settings


def test_settings_validate_ok(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/mega_ai")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://redis:6379/0")
    monkeypatch.setenv("CELERY_RESULT_BACKEND", "redis://redis:6379/1")

    s = Settings.load()
    # Should not raise
    s.validate()


def test_settings_validate_missing():
    # Ensure missing required setting raises
    monkeypatch = pytest.MonkeyPatch()
    for key in ["DATABASE_URL", "REDIS_URL", "CELERY_BROKER_URL", "CELERY_RESULT_BACKEND"]:
        monkeypatch.delenv(key, raising=False)
    with pytest.raises(Exception):
        Settings.load()
    monkeypatch.undo()
