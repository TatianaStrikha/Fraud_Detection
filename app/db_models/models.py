# =============================================
# ORM таблицы
# =============================================
from app.db_models.registry import mapper_registry
from sqlalchemy import Column, Integer, BigInteger, Numeric, Float, String


@mapper_registry.mapped
class CardProfile:
     """
     Оперативный профиль карты для  расчета дельты времени (time_diff_card_uid).
     Используется воркером для отслеживания аномальной плотности транзакций.
     """
     __tablename__ = "card_profiles"

     # card_uid — склейка card1-card6, первичный ключ (индекс создается автоматически)
     card_uid = Column(String(255), primary_key=True)
     # Последний зафиксированный таймстемп транзакции в секундах (TransactionDT)
     last_transaction_dt = Column(BigInteger, nullable=False)


@mapper_registry.mapped
class Transaction:
     """
     Исторический лог транзакций для аналитики.
     Сюда бэкенд пакетно заливает фичи, а воркер дописывает скор модели CatBoost.
     """
     __tablename__ = "transactions"

     transaction_id = Column(BigInteger, primary_key=True)
     transaction_dt = Column(BigInteger, nullable=False)
     transaction_amt = Column(Numeric(precision=10, scale=2), nullable=False)
     product_cd = Column(String(10), index=True, nullable=False)
     card_uid = Column(String(255), nullable=False)

     # Результаты работы асинхронного воркера и модели CatBoost
     fraud_score = Column(Float, nullable=True)  # Вероятность фрода от 0.0 до 1.0
     verdict = Column(String(10), nullable=True)  # Текстовый вердикт: "Fraud" или "Legit"
     status = Column(String(20), default="PROCESSING")  # Статус: "PROCESSING" или "COMPLETED"

     # Истинная метка из демо-таргета (0 или 1), догружаемая на Этапе 2 для Error Analysis
     is_fraud_real = Column(Integer, nullable=True)


