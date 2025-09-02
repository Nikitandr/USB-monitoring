FROM python:3.11-slim

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Создание рабочей директории
WORKDIR /app

# Копирование requirements и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование серверного кода
COPY . .

# Создание директории для базы данных
RUN mkdir -p /app/data

# Создание пользователя для безопасности
RUN groupadd -r appuser && useradd -r -g appuser appuser
RUN chown -R appuser:appuser /app
USER appuser

# Открытие порта для HTTPS
EXPOSE 443

# Переменные окружения
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV DATABASE_PATH=/app/data/usb_monitor.db
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV SSL_ENABLED=true
ENV SSL_CERT_PATH=/app/certs/server.crt
ENV SSL_KEY_PATH=/app/certs/server.key

# Проверка здоровья контейнера (отключаем SSL проверку для самоподписанных сертификатов)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('https://localhost:443/', timeout=5, verify=False)" || exit 1

# Запуск приложения
CMD ["python", "app.py"]
