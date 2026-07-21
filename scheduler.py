"""
V2 MES System — Фоновые задачи
"""

import os
import shutil
import schedule
import time
import threading
import logging
from datetime import datetime

from config import TEMP_DIR, BACKUPS_DIR, CLOUD_DIR, SYSTEM_CONFIG_PATH

logger = logging.getLogger(__name__)


def cleanup_temp():
    """Очистка временных файлов"""
    if not os.path.exists(TEMP_DIR):
        return

    count = 0
    for f in os.listdir(TEMP_DIR):
        file_path = os.path.join(TEMP_DIR, f)
        try:
            if os.path.isfile(file_path):
                os.remove(file_path)
                count += 1
        except Exception as e:
            logger.error(f"Ошибка удаления {file_path}: {e}")

    if count > 0:
        logger.info(f"Очищено {count} временных файлов")


def backup_system_config():
    """Создать резервную копию system_config.xlsx"""
    if not os.path.exists(SYSTEM_CONFIG_PATH):
        return

    os.makedirs(BACKUPS_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"system_config_{timestamp}.xlsx"
    backup_path = os.path.join(BACKUPS_DIR, backup_name)

    try:
        shutil.copy2(SYSTEM_CONFIG_PATH, backup_path)
        logger.info(f"Создана резервная копия: {backup_name}")
    except Exception as e:
        logger.error(f"Ошибка создания резервной копии: {e}")


def setup_scheduler():
    """Настроить фоновые задачи"""
    # Очистка временных файлов каждые 10 минут
    schedule.every(10).minutes.do(cleanup_temp)

    # Резервное копирование каждый час
    schedule.every(1).hour.do(backup_system_config)

    logger.info("Фоновые задачи запущены")


def run_scheduler():
    """Запустить фоновые задачи в отдельном потоке"""
    setup_scheduler()

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Ошибка в планировщике: {e}")
            time.sleep(10)


def start_scheduler():
    """Запустить планировщик в фоновом потоке"""
    thread = threading.Thread(target=run_scheduler, daemon=True)
    thread.start()
    logger.info("Планировщик запущен в фоновом потоке")