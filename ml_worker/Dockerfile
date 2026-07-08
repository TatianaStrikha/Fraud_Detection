FROM python:3.11

#Устанавливаем системные зависимости, необходимые для сборки CatBoost в Linux
# Флаг --no-install-recommends исключает загрузку лишнего мусора в контейнер
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /ml_worker

# Копируем только файл зависимостей, чтобы эффективно использовать кэш Docker-слоев
COPY requirements.txt .

# Обновляем pip и устанавливаем ML-библиотеки без сохранения локального кэша
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем исходный код самого воркера в рабочую папку
COPY ml_worker/main.py .

# Запускаем бесконечный асинхронный конвейер воркера
CMD ["python", "main.py"]