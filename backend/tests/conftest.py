import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    """Ensure tests always use fixed credentials regardless of env vars."""
    monkeypatch.setattr(settings, "MY_ID", "admin")
    monkeypatch.setattr(settings, "MY_PW", "admin")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key-for-testing")
