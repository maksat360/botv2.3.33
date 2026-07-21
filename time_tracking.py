"""
V2 MES System — Учёт времени
"""

import os
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

from config import TIME_TRACKING_FILE, USERS_FILE, MONTHS_RU, CLOUD_DIR

# Состояния
STATE_SELECT_EMPLOYEE, STATE_ENTER_DATE, STATE_ENTER_HOURS = range(3)


def read_time_tracking():
    """Прочитать учёт времени"""
    if not os.path.exists(TIME_TRACKING_FILE):
        return pd.DataFrame(columns=["дата", "сотрудник", "часы", "проект", "менеджер"])
    return pd.read_excel(TIME_TRACKING_FILE, engine='openpyxl')


def write_time_tracking(df):
    """Записать учёт времени"""
    df.to_excel(TIME_TRACKING_FILE, index=False, engine='openpyxl')


async def time_tracking_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню учёта времени"""
    keyboard = [
        [InlineKeyboardButton("➕ Записать смену", callback_data="add_shift")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("⏱ Учёт времени:", reply_markup=reply_markup)


async def add_shift_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать запись смены — выбор сотрудника"""
    users_df = pd.read_excel(USERS_FILE, engine='openpyxl')

    keyboard = []
    for _, user in users_df.iterrows():
        if user["активен"] == 1:
            keyboard.append([InlineKeyboardButton(
                f"{user['фио']} (@{user['логин']})",
                callback_data=f"shift_emp_{user['логин']}"
            )])

    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = update.message
    if not msg:
        msg = update.callback_query.message
    await msg.reply_text("Выберите сотрудника:", reply_markup=reply_markup)
    return STATE_SELECT_EMPLOYEE


async def select_employee(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор сотрудника"""
    query = update.callback_query
    await query.answer()
    login = query.data.replace("shift_emp_", "")
    context.user_data["shift_employee"] = login

    await query.edit_message_text(
        f"Сотрудник: {login}\n"
        "Введите дату (ДД.ММ.ГГГГ) или отправьте 'сегодня':"
    )
    return STATE_ENTER_DATE


async def enter_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод даты"""
    text = update.message.text.strip()

    if text.lower() == "сегодня":
        date = datetime.now().strftime("%Y-%m-%d")
    else:
        try:
            date = datetime.strptime(text, "%d.%m.%Y").strftime("%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("❌ Неверный формат даты. Используйте ДД.ММ.ГГГГ")
            return STATE_ENTER_DATE

    context.user_data["shift_date"] = date
    await update.message.reply_text(f"Дата: {date}\nВведите количество часов:")
    return STATE_ENTER_HOURS


async def enter_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ввод часов"""
    text = update.message.text.strip()

    try:
        hours = float(text.replace(",", "."))
    except ValueError:
        await update.message.reply_text("❌ Введите число (часы):")
        return STATE_ENTER_HOURS

    employee = context.user_data["shift_employee"]
    date = context.user_data["shift_date"]
    manager = context.user_data.get("login", "")

    # Сохраняем
    time_df = read_time_tracking()
    new_record = pd.DataFrame([{
        "дата": date,
        "сотрудник": employee,
        "часы": hours,
        "проект": "Основной",
        "менеджер": manager,
    }])
    time_df = pd.concat([time_df, new_record], ignore_index=True)
    write_time_tracking(time_df)

    await update.message.reply_text(
        f"✅ Смена записана!\n"
        f"Сотрудник: {employee}\n"
        f"Дата: {date}\n"
        f"Часы: {hours}"
    )

    context.user_data.pop("shift_employee", None)
    context.user_data.pop("shift_date", None)
    return ConversationHandler.END


async def view_my_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр своих часов (сотрудник)"""
    login = context.user_data.get("login")

    keyboard = []
    for i, month in enumerate(MONTHS_RU, 1):
        keyboard.append([InlineKeyboardButton(month, callback_data=f"my_hours_month_{i}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите месяц:", reply_markup=reply_markup)


async def select_my_hours_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор месяца для просмотра часов"""
    query = update.callback_query
    await query.answer()

    month_num = int(query.data.replace("my_hours_month_", ""))
    login = context.user_data.get("login")

    time_df = read_time_tracking()
    if time_df.empty:
        await query.edit_message_text("❌ Нет данных.")
        return

    # Фильтруем по сотруднику и месяцу
    time_df["дата"] = pd.to_datetime(time_df["дата"], errors="coerce")
    month_data = time_df[
        (time_df["сотрудник"] == login) &
        (time_df["дата"].dt.month == month_num)
    ]

    total_hours = month_data["часы"].sum()
    month_name = MONTHS_RU[month_num - 1]

    await query.edit_message_text(
        f"⏱ {month_name}: {total_hours:.1f} часов"
    )


def get_time_tracking_handlers():
    """Получить обработчики для учёта времени"""
    from telegram.ext import ConversationHandler

    shift_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(add_shift_start, pattern="^add_shift$")],
        states={
            STATE_SELECT_EMPLOYEE: [CallbackQueryHandler(select_employee, pattern="^shift_emp_")],
            STATE_ENTER_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_date)],
            STATE_ENTER_HOURS: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_hours)],
        },
        fallbacks=[],
        name="time_tracking",
        persistent=False,
    )

    return [shift_handler]