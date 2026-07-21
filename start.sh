#!/bin/bash

# V2 MES System — Запуск на Mac / Linux / Codespaces

echo "🔄 Запуск V2 MES System..."

# Активация виртуального окружения
if [ -d "venv" ]; then
    source venv/bin/activate
else
    echo "⚠️ Виртуальное окружение не найдено. Запустите install.sh"
    exit 1
fi

# Проверка токена
if grep -q "ВАШ_ТОКЕН_ОТ_BOTFATHER" config.py; then
    echo "❌ Ошибка: Вставьте токен бота в config.py!"
    echo "   BOT_TOKEN = 'ваш_токен_от_BotFather'"
    exit 1
fi

# Запуск бота
echo "✅ Запуск..."
python3 main.py