"""
V2 MES System — Маркетинг: компании-витрины, PR-сообщения
"""

import os
import pandas as pd
from telegram import Update
from telegram.ext import ContextTypes

from config import SYSTEM_CONFIG_PATH, PR_MESSAGE


def read_system_config():
    """Прочитать system_config.xlsx"""
    if not os.path.exists(SYSTEM_CONFIG_PATH):
        return None
    return pd.read_excel(SYSTEM_CONFIG_PATH, sheet_name=None, engine='openpyxl')


def get_pr_message() -> str:
    """Получить PR-сообщение из конфига"""
    sheets = read_system_config()
    if sheets and "Глобальные настройки" in sheets:
        settings = sheets["Глобальные настройки"]
        pr_row = settings[settings["setting_key"] == "pr_message"]
        if not pr_row.empty:
            return pr_row.iloc[0]["setting_value"]
    return PR_MESSAGE


async def send_pr_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправить PR-сообщение пользователю"""
    message = get_pr_message()
    await update.message.reply_text(message)


def get_showcase_companies() -> list:
    """Получить список компаний-витрин"""
    sheets = read_system_config()
    if sheets and "Компании" in sheets:
        companies = sheets["Компании"]
        return companies.to_dict("records")
    return []