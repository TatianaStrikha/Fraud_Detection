FROM python:3.11

# Устанавливаем системные зависимости для работы с сетью и PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /workspace

# Копируем файл зависимостей основного приложения
COPY requirements.txt .

# Обновляем pip и устанавливаем библиотеки без сохранения локального кэша
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем исходный код приложения и конфигурационные файлы
COPY app/ ./app/
COPY config.py .

# Открываем порт 8080 для веб-трафика
EXPOSE 8080

# Запускаем сервер Uvicorn через встроенный модуль Python
# Настройки хоста 0.0.0.0 обязательны, чтобы контейнер принимал запросы снаружи
CMD ["python", "-m", "uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8080"]