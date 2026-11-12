# Используем легкий образ Python
FROM python:3.11-slim

# Устанавливаем системные зависимости (нужны для некоторых библиотек, например Pillow)
RUN apt-get update && apt-get install -y \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Сначала копируем только requirements, чтобы использовать кэш Docker
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь остальной код проекта
COPY . .

# Создаем папки для данных и логов, если их нет
RUN mkdir -p data logs

# Команда по умолчанию (запуск бота)
CMD ["python", "main.py"]