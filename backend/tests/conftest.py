import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.services.download_manager as dm_module
import app.ws.handler as ws_handler_module
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.models.download import Download  # noqa: F401

# In-memory DB with StaticPool so all sessions share the same connection
test_engine = create_async_engine(
    "sqlite+aiosqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = async_sessionmaker(
    bind=test_engine, class_=AsyncSession, expire_on_commit=False,
)


@pytest.fixture(autouse=True)
async def setup_test_db():
    """Create tables in in-memory DB for each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def override_db_dependency():
    """Override get_db and download_manager's session to use test DB."""
    original_dm_session = dm_module.AsyncSessionLocal
    original_ws_session = ws_handler_module.AsyncSessionLocal

    async def _get_test_db():
        async with TestSessionLocal() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = _get_test_db
    dm_module.AsyncSessionLocal = TestSessionLocal
    ws_handler_module.AsyncSessionLocal = TestSessionLocal
    yield
    app.dependency_overrides.clear()
    dm_module.AsyncSessionLocal = original_dm_session
    ws_handler_module.AsyncSessionLocal = original_ws_session


@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    """Fix credentials and secret key for tests."""
    monkeypatch.setattr(settings, "MY_ID", "admin")
    monkeypatch.setattr(settings, "MY_PW", "admin")
    monkeypatch.setattr(settings, "SECRET_KEY", "test-secret-key-for-testing")
