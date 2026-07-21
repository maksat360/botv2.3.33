#!/bin/bash

# V2 MES System — Установка на Mac / Linux / Codespaces

echo "🔄 Установка V2 MES System..."

# Проверка Python
PYTHON_VERSION=$(python3 --version 2>/dev/null | cut -d' ' -f2 | cut -d'.' -f1,2)
if [ -z "$PYTHON_VERSION" ]; then
    echo "❌ Python 3 не найден. Установите Python 3.11+"
    exit 1
fi

echo "✅ Python $PYTHON_VERSION найден"

# Создание виртуального окружения
echo "🔄 Создание виртуального окружения..."
python3 -m venv venv
source venv/bin/activate

# Установка зависимостей
echo "🔄 Установка зависимостей..."
pip install --upgrade pip
pip install -r requirements.txt

# Создание папок
echo "🔄 Создание папок..."
mkdir -p data
mkdir -p cloud_storage
mkdir -p cloud_storage/Зарплатные_отчеты
mkdir -p cloud_storage/Фото_партий
mkdir -p cloud_storage/Фото_брака
mkdir -p cloud_storage/Временные
mkdir -p cloud_storage/Отчёты
mkdir -p cloud_storage/backups
mkdir -p fonts

# Скачивание шрифта для PDF (если нет)
if [ ! -f fonts/DejaVuSans.ttf ]; then
    echo "🔄 Скачивание шрифта DejaVu..."
    curl -L -o fonts/DejaVuSans.ttf "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf" 2>/dev/null || \
        echo "⚠️ Не удалось скачать шрифт. PDF с кириллицей может не работать."
fi

echo ""
echo "✅ Установка завершена!"
echo ""
echo "📋 Дальнейшие шаги:"
echo "1. Откройте config.py и вставьте токен от @BotFather"
echo "2. Запустите: ./start.sh"