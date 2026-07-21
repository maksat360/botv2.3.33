"""
V2 MES System — Конфигурационный файл
"""

import os
import hashlib

# ===== ТОКЕН БОТА =====
# Получить у @BotFather. ВСТАВЬТЕ СВОЙ ТОКЕН!
BOT_TOKEN = "8922842876:AAGGTNakzY2JsJ0B0Y9gU7bFC5asMXCFL-M"

# ===== ПУТИ =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CLOUD_DIR = os.path.join(BASE_DIR, "cloud_storage")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

# ===== ФАЙЛЫ БАЗЫ ДАННЫХ =====
DB_PATH = os.path.join(DATA_DIR, "bot.db")

# ===== ФАЙЛЫ EXCEL =====
SYSTEM_CONFIG_PATH = os.path.join(CLOUD_DIR, "system_config.xlsx")
USERS_FILE = os.path.join(CLOUD_DIR, "пользователи.xlsx")
PARTIES_FILE = os.path.join(CLOUD_DIR, "партии.xlsx")
TIME_TRACKING_FILE = os.path.join(CLOUD_DIR, "учёт_времени.xlsx")
DEFECTS_FILE = os.path.join(CLOUD_DIR, "брак.xlsx")
CONVEYOR_CONFIG_FILE = os.path.join(CLOUD_DIR, "конвейер_настройки.xlsx")

# ===== ПАПКИ =====
SALARY_REPORTS_DIR = os.path.join(CLOUD_DIR, "Зарплатные_отчеты")
PHOTO_PARTIES_DIR = os.path.join(CLOUD_DIR, "Фото_партий")
PHOTO_DEFECTS_DIR = os.path.join(CLOUD_DIR, "Фото_брака")
TEMP_DIR = os.path.join(CLOUD_DIR, "Временные")
REPORTS_DIR = os.path.join(CLOUD_DIR, "Отчёты")
BACKUPS_DIR = os.path.join(CLOUD_DIR, "backups")

# ===== НАСТРОЙКИ =====
BOT_NAME = "V2 MES System"
DEFAULT_TRIAL_DAYS = 60
TEMP_CLEANUP_MINUTES = 10
PR_MESSAGE = "Извините, нас стало слишком много, сервер не справляется. Мы расширяем мощности. Спасибо за понимание!"

# ===== РОЛИ =====
ROLE_SUPERADMIN = "суперадмин"
ROLE_BOSS = "начальник"
ROLE_TECHNOLOGIST = "технолог"
ROLE_TIMESHEET = "табельщик"
ROLE_ACCOUNTANT = "бухгалтер"
ROLE_EMPLOYEE = "сотрудник"

ALL_ROLES = [
    ROLE_SUPERADMIN,
    ROLE_BOSS,
    ROLE_TECHNOLOGIST,
    ROLE_TIMESHEET,
    ROLE_ACCOUNTANT,
    ROLE_EMPLOYEE,
]

# ===== МЕСЯЦЫ =====
MONTHS_RU = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Окторябрь", "Ноябрь", "Декабрь",
]

MONTHS_RU_GENITIVE = [
    "Января", "Февраля", "Марта", "Апреля", "Мая", "Июня",
    "Июля", "Августа", "Сентября", "Октября", "Ноября", "Декабря",
]


def hash_password(password: str) -> str:
    """Хеширование пароля SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()


def get_month_folder_name(month_num: int) -> str:
    """Получить название папки месяца по номеру (1-12)"""
    return MONTHS_RU[month_num - 1]


def get_salary_filename(month_name: str, year: int, version: int = None) -> str:
    """Сформировать имя файла зарплаты"""
    base = f"зарплата_{month_name}_{year}"
    if version and version > 0:
        return f"{base}_v{version}.xlsx"
    return f"{base}.xlsx"
