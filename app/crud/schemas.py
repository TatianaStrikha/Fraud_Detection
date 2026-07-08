# =============================================
# Pydantic схемы
# =============================================
from pydantic import BaseModel, ConfigDict
from typing import Optional


class CreateSchema(BaseModel):
    """
    ЭТАП 1: Схема для потока сырых транзакций (из demo_test.csv).
    Валидирует 10 обязательных базовых полей для логики СУБД,
    остальные колонки принимает благодаря настройке extra='allow'.
    Поля 'isFraud' здесь физически нет, что гарантирует слепой инференс модели.
    """
    TransactionID: int
    TransactionDT: int
    TransactionAmt: float
    ProductCD: str
    card1: int
    card2: Optional[float] = None
    card3: Optional[float] = None
    card4: Optional[str] = None
    card5: Optional[float] = None
    card6: Optional[str] = None
    model_config = ConfigDict(from_attributes=True, extra='allow')


class UpdateSchema(BaseModel):
    """
    ЭТАП 2: Схема для архивной разметки (из demo_target.csv).
    Принимает только ID и истинную метку мошенничества для симуляции чарджбэков.
    """
    TransactionID: int
    isFraud: int


class AnalyticsSchema(BaseModel):
    """
    ЭТАП 3: Финальная аналитика.
    Возвращает агрегированную СУБД статистику. Поля TP, FP, TN, FN пересчитаются
    и выведутся на экран только после того, как прилетит UpdateSchema.
    """
    total_checked: int  # Всего проверено транзакций (118108)
    total_fraud_detected: int  # Сколько фрода нашла модель (TP + FP)
    total_legit_detected: int  # Сколько честных чеков одобрила модель (TN + FN)

    # Поля для Error Analysis (заполняются только после загрузки разметки)
    true_positives: Optional[int] = 0
    false_positives: Optional[int] = 0
    true_negatives: Optional[int] = 0
    false_negatives: Optional[int] = 0
