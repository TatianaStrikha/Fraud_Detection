# =============================================
# REST интерфейс
# =============================================
import io
import json
import uuid
import pandas as pd
import aio_pika
from typing import Dict, Any
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from config import logger, get_settings
from app.database import get_session
from app.crud.transactions import TransactionCRUD
from app.crud.schemas import AnalyticsSchema

api_router = APIRouter(tags=["REST Antifraud API"])

# Глобальное хранилище для прогресс-бара
processing_sessions: Dict[str, float] = {}


async def push_batch_to_queue(rabbitmq_url: str, routing_key: str, payload: dict):
    """Вспомогательная асинхронная функция для отправки батча в RabbitMQ"""
    connection = await aio_pika.connect_robust(rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        queue = await channel.declare_queue(routing_key, durable=True)

        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT
            ),
            routing_key=queue.name
        )


async def async_batch_processor(file_bytes: bytes, session_id: str, db: AsyncSession):
    """Фоновый процессор: нарезает демо-файл, заливает в БД и пушит в RabbitMQ."""
    settings = get_settings()
    df = pd.read_csv(io.BytesIO(file_bytes))
    total_rows = len(df)

    logger.info(f"Начало обработки сессии {session_id}. Всего строк: {total_rows}")
    processing_sessions[session_id] = 0.0

    batch_size = 1000

    for i in range(0, total_rows, batch_size):
        chunk_df = df.iloc[i:i + batch_size].copy()
        card_cols = ["card1", "card2", "card3", "card4", "card5", "card6"]
        chunk_df["card_uid"] = chunk_df[card_cols].astype(str).agg("_".join, axis=1)
        batch_records = chunk_df.where(pd.notnull(chunk_df), None).to_dict(orient="records")
        await TransactionCRUD.create(db, batch_records)

        rabbitmq_payload = {
            "session_id": session_id,
            "transactions": batch_records
        }
        await push_batch_to_queue(settings.RABBITMQ_URL, "antifraud_tasks", rabbitmq_payload)

        current_progress = round(((i + len(chunk_df)) / total_rows) * 100, 1)
        processing_sessions[session_id] = min(current_progress, 99.0)

    logger.info(f"Все {total_rows} строк отправлены в RabbitMQ.")


@api_router.post("/antifraud/upload")
async def upload_live_transactions(
        background_tasks: BackgroundTasks,
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_session)
):
    """ЭТАП 1: Прием сырого потока транзакций (demo_test.csv)."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Допускаются только файлы формата .csv")

    session_id = str(uuid.uuid4())
    file_bytes = await file.read()

    background_tasks.add_task(async_batch_processor, file_bytes, session_id, db)
    return {"status": "QUEUED", "session_id": session_id, "message": "Поток транзакций успешно запущен."}


@api_router.post("/antifraud/feedback")
async def upload_archive_chargebacks(
        file: UploadFile = File(...),
        db: AsyncSession = Depends(get_session)
):
    """ЭТАП 2: Догрузка архивной разметки (demo_target.csv)."""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Допускаются только файлы формата .csv")

    file_bytes = await file.read()
    df = pd.read_csv(io.BytesIO(file_bytes))

    if "TransactionID" not in df.columns or "isFraud" not in df.columns:
        raise HTTPException(status_code=400, detail="Файл разметки должен содержать TransactionID и isFraud")

    batch_size = 5000
    total_rows = len(df)

    for i in range(0, total_rows, batch_size):
        chunk_df = df.iloc[i:i + batch_size].copy()
        feedback_records = chunk_df.to_dict(orient="records")

        await TransactionCRUD.update(db, feedback_records)

    return {"status": "SUCCESS", "message": f"Разметка для {total_rows} строк успешно загружена."}


@api_router.get("/antifraud/progress/{session_id}")
async def get_queue_progress(session_id: str):
    """Эндпоинт для прогресс-бара."""
    progress = processing_sessions.get(session_id, 0.0)
    return {"session_id": session_id, "progress": progress}


@api_router.get("/antifraud/dashboard", response_model=AnalyticsSchema)
async def get_dashboard_data(db: AsyncSession = Depends(get_session)):
    """Эндпоинт дашборда. Возвращает агрегированные метрики."""
    analytics_data = await TransactionCRUD.analytics(db)
    return analytics_data

