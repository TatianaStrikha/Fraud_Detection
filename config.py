import logging
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from functools import lru_cache

class Settings(BaseSettings):
    """
    Класс автоматически загружает переменные конфигурации из файла .env
    """
    # Параметры базы данных PostgreSQL
    DB_HOST: Optional[str] = None
    DB_PORT: Optional[int] = None
    DB_USER: Optional[str] = None
    DB_PASS: Optional[str] = None
    DB_NAME: Optional[str] = None

    # Общие параметры приложения FastAPI
    APP_NAME: Optional[str] = None
    APP_DESCRIPTION: Optional[str] = None
    DEBUG: Optional[bool] = None
    API_VERSION: Optional[str] = None

    # Параметры брокера сообщений RabbitMQ
    RABBITMQ_USER: Optional[str] = None
    RABBITMQ_PASS: Optional[str] = None
    RABBITMQ_HOST: Optional[str] = None
    RABBITMQ_PORT: Optional[int] = None

    @property
    def DATABASE_URL(self) -> str:
        """Формирует асинхронную строку подключения для SQLAlchemy (asyncpg)"""
        return f'postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}'

    @property
    def RABBITMQ_URL(self) -> str:
        """Формирует строку подключения для брокера сообщений aio-pika"""
        return f"amqp://{self.RABBITMQ_USER}:{self.RABBITMQ_PASS}@{self.RABBITMQ_HOST}:{self.RABBITMQ_PORT}/"

    # Конфигурация источника данных Pydantic Settings
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"  # Игнорируем лишние переменные окружения, чтобы избежать ошибок
    )

@lru_cache()
def get_settings() -> Settings:
    """Получение кэшированного экземпляра настроек приложения"""
    return Settings()


# глобальный логгер
logger = logging.getLogger("uvicorn.error")
