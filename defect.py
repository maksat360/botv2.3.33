"""
V2 MES System — Брак и фотофиксация
"""

import os
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import DEFECTS_FILE, PHOTO_DEFECTS_DIR, CLOUD_DIR


def read_defects():
    """Прочитать реестр брака"""
    if not os.path.exists(DEFECTS_FILE):
        return pd.DataFrame(columns=["партия", "процесс", "сотрудник", "фото_ссылка", "дата", "статус", "технолог_статус"])
    return pd.read_excel(DEFECTS_FILE, engine='openpyxl')


def write_defects(df):
    """Записать реестр брака"""
    df.to_excel(DEFECTS_FILE, index=False, engine='openpyxl')


async def report_defect(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Сообщить о браке"""
    context.user_data["defect_step"] = "waiting_party"
    await update.message.reply_text(
        "📸 Введите номер партии, в которой обнаружен брак:"
    )


async def handle_defect_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста при фиксации брака"""
    step = context.user_data.get("defect_step")

    if step == "waiting_party":
        party_num = update.message.text.strip()
        context.user_data["defect_party"] = party_num
        context.user_data["defect_step"] = "waiting_photo"
        await update.message.reply_text(
            f"📸 Партия #{party_num}. Отправьте фото брака:"
        )

    elif step == "waiting_process":
        process = update.message.text.strip()
        context.user_data["defect_process"] = process
        context.user_data["defect_step"] = "waiting_photo"
        await update.message.reply_text("📸 Отправьте фото брака:")


async def handle_defect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото брака"""
    if not update.message.photo:
        await update.message.reply_text("❌ Пожалуйста, отправьте фото.")
        return

    party_num = context.user_data.get("defect_party")
    process = context.user_data.get("defect_process", "Не указан")
    login = context.user_data.get("login", "Неизвестно")

    if not party_num:
        await update.message.reply_text("❌ Ошибка: не указана партия. Начните заново.")
        context.user_data.pop("defect_step", None)
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()

    # Сохраняем фото
    party_dir = os.path.join(PHOTO_DEFECTS_DIR, f"Партия_{party_num}")
    os.makedirs(party_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    photo_name = f"Брак_{timestamp}.jpg"
    photo_path = os.path.join(party_dir, photo_name)
    await file.download_to_drive(photo_path)

    # Добавляем запись в брак.xlsx
    defects_df = read_defects()
    new_record = pd.DataFrame([{
        "партия": party_num,
        "процесс": process,
        "сотрудник": login,
        "фото_ссылка": photo_path,
        "дата": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "статус": "Новый",
        "технолог_статус": "Не обработан",
    }])
    defects_df = pd.concat([defects_df, new_record], ignore_index=True)
    write_defects(defects_df)

    context.user_data.pop("defect_step", None)
    context.user_data.pop("defect_party", None)
    context.user_data.pop("defect_process", None)

    await update.message.reply_text("✅ Брак зафиксирован. Спасибо за сообщение!")


async def view_defects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр брака (для технолога)"""
    role = context.user_data.get("role")
    login = context.user_data.get("login")

    defects_df = read_defects()

    if defects_df.empty:
        await update.message.reply_text("📋 Нет зафиксированного брака.")
        return

    if role == "технолог":
        # Технолог видит все необработанные
        pending = defects_df[defects_df["технолог_статус"] == "Не обработан"]
        if pending.empty:
            await update.message.reply_text("✅ Весь брак обработан.")
            return

        for _, defect in pending.iterrows():
            text = (
                f"📸 Брак\n"
                f"Партия: #{defect['партия']}\n"
                f"Процесс: {defect['процесс']}\n"
                f"Сотрудник: {defect['сотрудник']}\n"
                f"Дата: {defect['дата']}\n"
            )

            keyboard = [
                [InlineKeyboardButton("✅ Принято", callback_data=f"defect_accept_{defect.name}")],
                [InlineKeyboardButton("🔄 Возврат", callback_data=f"defect_return_{defect.name}")],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            # Отправляем фото, если есть
            photo_path = defect.get("фото_ссылка", "")
            if photo_path and os.path.exists(photo_path):
                with open(photo_path, "rb") as f:
                    await update.message.reply_photo(photo=f, caption=text, reply_markup=reply_markup)
            else:
                await update.message.reply_text(text, reply_markup=reply_markup)

    elif role == "начальник":
        # Начальник видит статистику
        await show_defect_statistics(update, context, defects_df)

    else:
        # Сотрудник видит только свой брак
        my_defects = defects_df[defects_df["сотрудник"] == login]
        if my_defects.empty:
            await update.message.reply_text("📋 У вас нет зафиксированного брака.")
            return

        for _, defect in my_defects.iterrows():
            text = (
                f"📸 Брак\n"
                f"Партия: #{defect['партия']}\n"
                f"Процесс: {defect['процесс']}\n"
                f"Статус: {defect['статус']}\n"
                f"Технолог: {defect['технолог_статус']}\n"
            )
            await update.message.reply_text(text)


async def handle_defect_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий технолога над браком"""
    query = update.callback_query
    await query.answer()

    data = query.data
    defects_df = read_defects()

    if data.startswith("defect_accept_"):
        idx = int(data.replace("defect_accept_", ""))
        defects_df.loc[idx, "статус"] = "Принято"
        defects_df.loc[idx, "технолог_статус"] = "Обработан"
        write_defects(defects_df)
        await query.edit_message_caption(caption=query.message.caption + "\n\n✅ Принято")

    elif data.startswith("defect_return_"):
        idx = int(data.replace("defect_return_", ""))
        defects_df.loc[idx, "статус"] = "Возврат"
        defects_df.loc[idx, "технолог_статус"] = "Обработан"
        write_defects(defects_df)
        await query.edit_message_caption(caption=query.message.caption + "\n\n🔄 Возврат")


async def show_defect_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE, defects_df=None):
    """Показать статистику брака для начальника"""
    if defects_df is None:
        defects_df = read_defects()

    if defects_df.empty:
        await update.message.reply_text("📈 Статистика брака: нет данных.")
        return

    # По процессам
    by_process = defects_df.groupby("процесс").size().sort_values(ascending=False)
    # По сотрудникам
    by_employee = defects_df.groupby("сотрудник").size().sort_values(ascending=False)

    lines = ["📈 СТАТИСТИКА БРАКА\n"]

    lines.append("\n📊 По процессам:")
    for process, count in by_process.items():
        lines.append(f"  {process}: {count}")

    lines.append("\n👤 По сотрудникам:")
    for emp, count in by_employee.items():
        lines.append(f"  {emp}: {count}")

    await update.message.reply_text("\n".join(lines))