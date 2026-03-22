import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    """Ensure tests always use fixed credentials regardless of env vars."""
    monkeypatch.setattr(settings, "MY_ID", "admin")
    monkeypatch.setattr(settings, "MY_PW", "admin")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key-for-testing")


@pytest.fixture(autouse=True)
async def init_test_db():
    """Ensure DB tables exist for every test."""
    from app.database import Base, engine
    from app.models.download import Download  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
