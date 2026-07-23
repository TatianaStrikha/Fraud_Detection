import pytest
from app.crud.transactions import TransactionCRUD
from app.routers.api import async_batch_processor # Импортируем фоновый процессор

# Явно включаем асингулярный режим для этого файла
pytestmark = pytest.mark.asyncio


async def test_web_homepage(client):
    """
    1. ТЕСТ WEB-ИНТЕРФЕЙСА: Проверяет рендеринг главной страницы HTML.
    """
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


async def test_antifraud_upload(client, db_session):
    """
    2. ТЕСТ REST API (ЭТАП 1): Проверяет эндпоинт и прямую пакетную вставку в СУБД.
    """
    csv_content = (
        "TransactionID,TransactionDT,TransactionAmt,ProductCD,card1,card2,card3,card4,card5,card6\n"
        "200001,86400,150.0,W,9999,,,visa,,debit\n"
        "200002,86405,500.5,C,8888,,,mastercard,,credit\n"
    )

    # Проверяем, что сам HTTP-эндпоинт работает
    files = {"file": ("demo_test.csv", csv_content, "text/csv")}
    response = await client.post("/api/antifraud/upload", files=files)
    assert response.status_code == 200
    assert response.json()["status"] == "QUEUED"

    # Гарантируем выполнение бизнес-логики: принудительно прогоняем данные
    # через процессор напрямую в тестовую базу db_session
    await async_batch_processor(csv_content.encode('utf-8'), "test_session", db_session)

    # Проверяем, что в базу успешно записались 2 строки
    analytics = await TransactionCRUD.analytics(db_session)
    assert analytics["total_checked"] == 2
    assert analytics["total_fraud_detected"] == 0


async def test_antifraud_feedback(client, db_session):
    """
    3. ТЕСТ REST API (ЭТАП 2): Симулирует догрузку разметки истины
    """
    # 1. Сначала принудительно создаем базовую транзакцию в SQLite
    await TransactionCRUD.create(db_session, [{
        "TransactionID": 300001, "TransactionDT": 90000, "TransactionAmt": 10.0,
        "ProductCD": "W", "card1": 5555, "card_uid": "5555_None"
    }])

    await db_session.commit()

    # 2. Отправляем архивный файл с чарджбэком
    target_csv = "TransactionID,isFraud\n300001,1\n"
    files = {"file": ("demo_target.csv", target_csv, "text/csv")}

    response = await client.post("/api/antifraud/feedback", files=files)
    assert response.status_code == 200
    assert response.json()["status"] == "SUCCESS"

    # Проверяем, что база зафиксировала вставку разметки истины
    analytics = await TransactionCRUD.analytics(db_session)
    assert analytics["total_checked"] == 1




