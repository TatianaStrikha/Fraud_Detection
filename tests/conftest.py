import asyncio
import pytest
from unittest.mock import AsyncMock
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from httpx import AsyncClient, ASGITransport
from app.api import app
from app.database import get_session
from app.db_models.registry import metadata

# Тестовая БД в оперативной памяти компьютера
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # Сохраняет одну БД на все соединения в тесте
)

TestingSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Создаем глобальный Event Loop для всех сессионных тестов
@pytest.fixture(scope="session")
def event_loop():
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def db_session():
    """
    Фикстура для прямого доступа к тестовой БД в коде тестов.
    """
    async with TestingSessionLocal() as session:
        yield session


# Фикстура для инициализации таблиц перед тестами
@pytest.fixture(autouse=True)
async def init_test_db():
    # Локально импортируем новые ORM-модели, чтобы они зарегистрировались в метаданных
    from app.db_models.models import CardProfile, Transaction

    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)

    yield

    # Очистка после всех тестов
    async with engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)


# Подмена зависимости get_session в FastAPI роутерах
@pytest.fixture(autouse=True)
async def override_get_session():
    async def _get_test_session():
        async with TestingSessionLocal() as session:
            yield session

    # Заменяем реальную сессию на тестовую во всех роутерах антифрода
    app.dependency_overrides[get_session] = _get_test_session
    yield
    # Очищаем подмену после завершения теста
    app.dependency_overrides.clear()


# mocker автоматически перехватит тяжелую сетевую отправку и заменит её на AsyncMock
@pytest.fixture(autouse=True)
def mock_rabbit(mocker):
    return mocker.patch("app.routers.api.push_batch_to_queue", new_callable=AsyncMock)


# Асинхронный клиент для выполнения HTTP-запросов к нашему антифрод API
@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


