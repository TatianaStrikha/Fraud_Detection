# =============================================
# Инициализация БД
# =============================================
from config import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from config import get_settings
from app.db_models.registry import metadata

# Фабрика движка
def get_engine():
    """
    Возвращает один и тот же экземпляр движка.
    Создаётся при первом вызове.
    """
    if not hasattr(get_engine, "_engine"):
        settings = get_settings()
        get_engine._engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
    return get_engine._engine


# Фабрика сессий
def get_session_local():
    """
    Возвращает один и тот же экземпляр async_sessionmaker.
    Создаётся при первом вызове.
    """
    if not hasattr(get_session_local, "_sessionmaker"):
        get_session_local._sessionmaker = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False
        )
    return get_session_local._sessionmaker


# Генератор сессии для FastAPI зависимостей
async def get_session():
    """
    Генератор сессии для использования в FastAPI зависимостях.
    Автоматически коммитит при успехе, откатывает при ошибке, закрывает в любом случае.
    """
    session = get_session_local()()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


# Инициализация БД
async def init_db(drop_all: bool = False, engine=None):
    """
    Инициализация базы данных антифрода:
    Создание или удаление таблиц card_profiles и transactions.
    """
    # Локальный импорт моделей из папки db_models для избежания цикличности
    from app.db_models.models import CardProfile, Transaction

    engine = engine or get_engine()

    async with engine.begin() as conn:
        # удаление таблиц и создание пустых (для тестов или перезапуска демонстрации)
        if drop_all:
            logger.info("Удаляем все существующие таблицы антифрода...")
            await conn.execute(text("SET session_replication_role = 'replica'"))
            await conn.run_sync(metadata.drop_all)
            await conn.execute(text("SET session_replication_role = 'origin'"))
            logger.info("Все таблицы удалены.")
            logger.info("Создаём новые пустые таблицы...")

        # Автоматически находит CardProfile и Transaction в metadata и создает их в PostgreSQL
        await conn.run_sync(metadata.create_all)

    logger.info("БД антифрода успешно инициализирована.")

