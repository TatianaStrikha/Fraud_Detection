# =============================================
# Логика работы ML-воркера
# =============================================
import asyncio
import io
import json
import os
import pickle
import logging
import pandas as pd
import numpy as np
from catboost import CatBoostClassifier, Pool
import aio_pika
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from config import get_settings

# Настройка локального логирования воркера
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ml_worker")

# Получаем кэшированные настройки
settings = get_settings()
QUEUE_NAME = "antifraud_tasks"

# Инициализируем асинхронный движок SQLAlchemy для записи результатов в СУБД
engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)

# Глобальные переменные для ML-артефактов
model = None
artifacts = None


def load_ml_artifacts():
    """Синхронная загрузка CatBoost модели и чертежа признаков при старте"""
    global model, artifacts
    logger.info("Загрузка ML-компонентов из папки model/...")

    # Пути вычисляются относительно корня, куда мы смонтируем файлы в Докере
    model_path = "/model/antifraud_model.cbm"
    artifacts_path = "/model/artifacts.pkl"

    # 1. Загружаем веса CatBoost
    model = CatBoostClassifier()
    model.load_model(model_path)
    logger.info("Веса CatBoost Classifier успешно загружены в память.")

    # 2. Загружаем чертеж признаков
    with open(artifacts_path, "rb") as f:
        artifacts = pickle.load(f)
    logger.info(f"Артефакты предобработки загружены. Ожидаемая размерность: {len(artifacts['feature_names'])} фич.")


async def process_card_profiles_and_get_deltas(transactions_df: pd.DataFrame) -> pd.DataFrame:
    """
    Финтех-магия: атомарное обновление времени карт в PostgreSQL (Upsert)
    и расчет критического признака time_diff_card_uid для всего батча.
    """
    # Собираем уникальный uid для каждой строки батча (card1_card2_..._card6)
    card_cols = ["card1", "card2", "card3", "card4", "card5", "card6"]
    transactions_df["card_uid"] = transactions_df[card_cols].astype(str).agg("_".join, axis=1)

    # Создаем пустую колонку для дельт времени
    transactions_df["time_diff_card_uid"] = -1.0

    async with engine.begin() as conn:
        # Обходим строки батча. Благодаря пакетной обработке по 1000 строк,
        # накладные расходы на итерации будут незаметны
        for idx, row in transactions_df.iterrows():
            uid = row["card_uid"]
            current_dt = row["TransactionDT"]

            # SQL-конструкция UPSERT: Создает карту, если ее нет. Если есть — обновляет время,
            # но СУБД возвращает нам старый last_transaction_dt до перезаписи
            query = text("""
                INSERT INTO card_profiles (card_uid, last_transaction_dt)
                VALUES (:uid, :current_dt)
                ON CONFLICT (card_uid) 
                DO UPDATE SET last_transaction_dt = EXCLUDED.last_transaction_dt
                RETURNING (
                    SELECT last_transaction_dt FROM card_profiles WHERE card_uid = :uid
                );
            """)

            res = await conn.execute(query, {"uid": uid, "current_dt": current_dt})
            row_data = res.fetchone()

            # Если строка вернулась, значит карта уже платила раньше. Считаем дельту времени.
            if row_data and row_data[0] is not None:
                old_dt = row_data[0]
                transactions_df.at[idx, "time_diff_card_uid"] = float(current_dt - old_dt)

    return transactions_df


async def save_predictions_to_db(ids: list, scores: list, verdicts: list):
    """Пакетное сохранение вынесенных ML-вердиктов обратно в СУБД PostgreSQL"""
    # Формируем структуру словарей для эффективного bulk-апдейта
    update_data = [
        {"t_id": int(i), "score": float(s), "verd": str(v)}
        for i, s, v in zip(ids, scores, verdicts)
    ]

    async with engine.begin() as conn:
        query = text("""
            UPDATE transactions 
            SET fraud_score = :score, verdict = :verd, status = 'COMPLETED' 
            WHERE transaction_id = :t_id
        """)
        await conn.execute(query, update_data)


async def on_message(message: aio_pika.IncomingMessage):
    """Главный асинхронный конвейер: срабатывает, когда RabbitMQ выдает задачу"""
    async with message.process():
        try:
            # Расшифровываем JSON задачу из байт очереди
            payload = json.loads(message.body.decode())
            session_id = payload["session_id"]
            raw_txs = payload["transactions"]

            logger.info(f"Воркер: Взят в обработку пакет из {len(raw_txs)} строк (Сессия: {session_id})")

            # Превращаем пакет в DataFrame для векторных ML-вычислений
            df = pd.DataFrame(raw_txs)
            # Принудительно заменяем все скрытые NoneType объекты на математический np.nan.
            df = df.fillna(value=np.nan)

            # Шаг 1: Идем в СУБД, обновляем профили карт и рассчитываем фичу time_diff_card_uid
            df = await process_card_profiles_and_get_deltas(df)

            # Шаг 2: Feature Engineering «вслепую» на основе 434 пришедших фич Kaggle
            # Расчитываем логарифм и час, как делали на этапе Baseline
            df["Amt_log"] = np.log1p(df["TransactionAmt"])
            df["hour"] = (df["TransactionDT"] / 3600) % 24

            # Генерируем 10 нелинейных признаков OpenFE по математическим формулам из артефактов
            # Внутри artifacts['openfe_formulas'] лежат текстовые инструкции вида: df['card1'] / df['TransactionAmt']
            if "openfe_formulas" in artifacts:
                for f_name, formula_expr in artifacts["openfe_formulas"].items():
                    try:
                        df[f_name] = eval(formula_expr)
                    except Exception:
                        df[f_name] = np.nan
            # Перебираем все 111 фич, которые ожидает модель CatBoost.
            # Если какой-то авто-фичи (например, autoFE_f_0) нет в текущем DataFrame,
            # мы принудительно создаем её и заполняем NaN.
            for feature in artifacts["feature_names"]:
                if feature not in df.columns:
                    df[feature] = np.nan

            # Шаг 3: Сверхбыстрая фильтрация избыточности и выравнивание порядка колонок
            # Pandas оставляет строго те 111 фич, на которых учился CatBoost, отсекая лишние 300+
            final_features_df = df[artifacts["feature_names"]].copy()

            # Шаг 4: Заполнение реальных пропусков (NaN) историческими константами из Train
            final_features_df.fillna(artifacts["global_constants"], inplace=True)

            # Шаг 5: Оптимизированный инференс CatBoost с эталонной защитой типов
            # 1. Извлекаем из самой модели точные имена категориальных фич, на которых она училась
            # Это на 100% исключает ошибку "Feature is Float in model but marked different"
            cat_indices = model.get_cat_feature_indices()
            all_feature_names = model.feature_names_
            cat_features_names = [all_feature_names[idx] for idx in cat_indices if all_feature_names[idx] in final_features_df.columns]

            # 2. Очищаем категориальные колонки: переводим их в текст и заполняем пропуски строкой 'nan'
            for col in cat_features_names:
                final_features_df[col] = final_features_df[col].astype(str).replace(['nan', 'None', '<NA>', 'NaN'], 'nan')

            # 3. Очищаем числовые колонки: принудительно переводим их в float,
            # чтобы текстовые опечатки (если они есть) не ломали ядро CatBoost
            for col in final_features_df.columns:
                if col not in cat_features_names:
                    final_features_df[col] = pd.to_numeric(final_features_df[col], errors='coerce')

            # Передаем в Pool эталонную матрицу данных и список имен категориальных фич
            data_pool = Pool(data=final_features_df, cat_features=cat_features_names)

            # Предсказываем вероятности фрода (берем колонку класса 1)
            probabilities = model.predict_proba(data_pool)[:, 1]

            # Применяем оптимальный порог отсечения (Threshold) из эксперимента №5
            threshold = artifacts.get("optimal_threshold", 0.3422)
            verdicts = ["Fraud" if score >= threshold else "Legit" for score in probabilities]

            # Шаг 6: Сохраняем пачку вердиктов в PostgreSQL за один асинхронный запрос
            tx_ids = df["TransactionID"].tolist()
            await save_predictions_to_db(tx_ids, probabilities, verdicts)

            logger.info(f"Воркер: Пакет из {len(raw_txs)} строк успешно рассчитан и сохранен в СУБД.")

        except Exception as e:
            logger.error(f"Критическая ошибка в работе воркера: {e}", exc_info=True)


async def main():
    """Инициализация и бесконечное асинхронное прослушивание брокера RabbitMQ"""
    # 1. Сначала загружаем ML-артефакты в память воркера
    load_ml_artifacts()

    logger.info("Подключение к RabbitMQ...")
    # Строка подключения к брокеру берется из настроек
    connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)

    async with connection:
        channel = await connection.channel()
        # Выравниваем нагрузку: один воркер берет из очереди не более 1 пакета за раз
        await channel.set_qos(prefetch_count=1)
        queue = await channel.declare_queue(QUEUE_NAME, durable=True)
        logger.info(f"Воркер успешно запущен. Ожидание задач в очереди '{QUEUE_NAME}'...")

        # Зацикливаем чтение очереди задач
        await queue.consume(on_message)
        # Держим поток активным бесконечно
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Воркер принудительно остановлен пользователем.")


