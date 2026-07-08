import logging
from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from config import get_settings, logger
from app.database import init_db
from app.routers.web import web_router
from app.routers.api import api_router

settings = get_settings()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Асинхронный менеджер жизненного цикла приложения.
    Срабатывает ровно один раз при старте FastAPI в Докере.
    """
    logger.info("Инициализация БД...")
    logger.info(f"Проверка URL БД: {settings.DATABASE_URL}")  # УДАЛИТЬ
    try:
        # drop_all=True очищает базу от старых логов при перезапуске,
        # позволяя тестировать загрузку 118k строк с чистого листа.
        await init_db(drop_all=False) # ЗАМЕНИТЬ НА True
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {str(e)}")
        raise
    yield

    logger.info("Приложение закрывается...")


def create_application() -> FastAPI:
    """
    Создание и настройка приложения FastAPI
    """
    app = FastAPI(
        title=settings.APP_NAME or "IEEE-CIS Antifraud MVP",
        description=settings.APP_DESCRIPTION or "High-load real-time transaction fraud detection service",
        version=settings.API_VERSION or "1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        lifespan=lifespan
    )

    # Настройка CORS-политик для стабильной работы сетевых запросов
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Регистрация эндпоинтов антифрода
    #  Веб-интерфейс (будет доступен по адресу http://localhost:8080/)
    app.include_router(web_router)

    # REST API
    app.include_router(api_router, prefix="/api")

    return app


app = create_application()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    uvicorn.run(
        'app.api:app',
        host='localhost',
        port=8080,
        reload=True,
        log_level="info"
    )


