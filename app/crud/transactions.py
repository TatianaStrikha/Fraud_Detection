# =============================================
# CRUD - функции
# =============================================
from config import logger
from typing import List, Dict, Any
from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db_models.models import Transaction  # Импортируем ORM-модель

class TransactionCRUD:

    @staticmethod
    async def create(session: AsyncSession, batch_data: List[Dict[str, Any]]):
        """
        ЭТАП 1: Пакетная вставка сырых фич из demo_test.csv.
        Заливает данные в PostgreSQL со статусом PROCESSING.
        """
        if not batch_data:
            return

        # Используем оптимизированный синтаксис пакетной вставки SQLAlchemy Core
        query = text("""
            INSERT INTO transactions (
                transaction_id, transaction_dt, transaction_amt, product_cd, card_uid, status
            ) VALUES (
                :TransactionID, :TransactionDT, :TransactionAmt, :ProductCD, :card_uid, 'PROCESSING'
            ) ON CONFLICT (transaction_id) DO NOTHING
        """)

        await session.execute(query, batch_data)
        logger.info(f"База данных: Пакет из {len(batch_data)} строк успешно сохранен в PostgreSQL.")

    @staticmethod
    async def update(session: AsyncSession, feedback_data: List[Dict[str, Any]]):
        """
        ЭТАП 2: Догрузка разметки истины из demo_target.csv (Симуляция чарджбэков).
        Точечно обновляет поле is_fraud_real по ID транзакции.
        """
        if not feedback_data:
            return

        query = text("""
            UPDATE transactions 
            SET is_fraud_real = :isFraud 
            WHERE transaction_id = :TransactionID
        """)

        await session.execute(query, feedback_data)
        logger.info(f"База данных: Разметка для {len(feedback_data)} строк успешно добавлена.")

    @staticmethod
    async def analytics(session: AsyncSession) -> Dict[str, Any]:
        """
        Расчет агрегированной бизнес-статистики и матрицы ошибок для AnalyticsSchema.
        """
        # 1. Считаем общие базовые метрики (Всего, Фрод, Честные)
        base_query = select(
            func.count(Transaction.transaction_id).label("total"),
            func.count(func.nullif(Transaction.verdict, 'Legit')).label("fraud_det"),
            func.count(func.nullif(Transaction.verdict, 'Fraud')).label("legit_det")
        )
        res = await session.execute(base_query)
        total, fraud_det, legit_det = res.fetchone()

        # 2. Считаем матрицу ошибок (сравнение вердикта воркера с полем истины is_fraud_real)
        matrix_query = text("""
            SELECT 
                COUNT(CASE WHEN verdict = 'Fraud' AND is_fraud_real = 1 THEN 1 END) as tp,
                COUNT(CASE WHEN verdict = 'Fraud' AND is_fraud_real = 0 THEN 1 END) as fp,
                COUNT(CASE WHEN verdict = 'Legit' AND is_fraud_real = 0 THEN 1 END) as tn,
                COUNT(CASE WHEN verdict = 'Legit' AND is_fraud_real = 1 THEN 1 END) as fn
            FROM transactions
            WHERE is_fraud_real IS NOT NULL
        """)

        matrix_res = await session.execute(matrix_query)
        tp, fp, tn, fn = matrix_res.fetchone()

        # Возвращаем словарь
        return {
            "total_checked": total or 0,
            "total_fraud_detected": fraud_det or 0,
            "total_legit_detected": legit_det or 0,
            "true_positives": tp or 0,
            "false_positives": fp or 0,
            "true_negatives": tn or 0,
            "false_negatives": fn or 0
        }
