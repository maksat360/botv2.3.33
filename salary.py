"""
V2 MES System — Зарплаты: загрузка, просмотр, архив
"""

import os
import shutil
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

from config import (
    SALARY_REPORTS_DIR, USERS_FILE, MONTHS_RU, MONTHS_RU_GENITIVE,
    CLOUD_DIR,
)

# Состояния
(
    STATE_SELECT_SALARY_YEAR,
    STATE_SELECT_SALARY_MONTH,
    STATE_UPLOAD_SALARY_REPORT,
    STATE_CONFIRM_OVERWRITE,
) = range(4)


def get_salary_file_path(company_dir: str, year: int, month_name: str, version: int = None) -> str:
    """Получить путь к файлу зарплаты"""
    year_dir = os.path.join(company_dir or SALARY_REPORTS_DIR, str(year))
    os.makedirs(year_dir, exist_ok=True)

    month_dir = os.path.join(year_dir, month_name)
    os.makedirs(month_dir, exist_ok=True)

    if version and version > 0:
        filename = f"зарплата_{month_name}_{year}_v{version}.xlsx"
    else:
        filename = f"зарплата_{month_name}_{year}.xlsx"

    return os.path.join(month_dir, filename)


def get_existing_versions(company_dir: str, year: int, month_name: str):
    """Получить существующие версии файла зарплаты"""
    base_path = get_salary_file_path(company_dir, year, month_name)
    versions = []

    if os.path.exists(base_path):
        versions.append({"path": base_path, "version": 0, "is_current": True})

    # Ищем старые версии
    year_dir = os.path.join(company_dir or SALARY_REPORTS_DIR, str(year))
    month_dir = os.path.join(year_dir, month_name)
    if os.path.exists(month_dir):
        for f in os.listdir(month_dir):
            if f.endswith(".xlsx") and "_v" in f:
                try:
                    v = int(f.split("_v")[-1].replace(".xlsx", ""))
                    versions.append({
                        "path": os.path.join(month_dir, f),
                        "version": v,
                        "is_current": False,
                    })
                except ValueError:
                    pass

    return sorted(versions, key=lambda x: x["version"])


async def salary_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню зарплат для бухгалтера/начальника"""
    keyboard = [
        [InlineKeyboardButton("📤 Загрузить отчёт", callback_data="upload_report")],
        [InlineKeyboardButton("📥 Архив отчётов", callback_data="archive_reports")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("💰 Зарплаты:", reply_markup=reply_markup)


async def upload_report_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать загрузку отчёта — выбор года"""
    current_year = datetime.now().year
    keyboard = []
    for y in range(current_year - 2, current_year + 1):
        keyboard.append([InlineKeyboardButton(str(y), callback_data=f"salary_year_{y}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = update.message
    if not msg:
        msg = update.callback_query.message
    await msg.reply_text("Выберите год:", reply_markup=reply_markup)
    return STATE_SELECT_SALARY_YEAR


async def select_salary_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор года для зарплаты"""
    query = update.callback_query
    await query.answer()
    year = int(query.data.replace("salary_year_", ""))
    context.user_data["salary_year"] = year

    keyboard = []
    for i, month in enumerate(MONTHS_RU, 1):
        keyboard.append([InlineKeyboardButton(month, callback_data=f"salary_month_{i}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите месяц:", reply_markup=reply_markup)
    return STATE_SELECT_SALARY_MONTH


async def select_salary_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор месяца для зарплаты"""
    query = update.callback_query
    await query.answer()
    month_num = int(query.data.replace("salary_month_", ""))
    month_name = MONTHS_RU[month_num - 1]
    context.user_data["salary_month"] = month_name
    context.user_data["salary_month_num"] = month_num

    await query.edit_message_text(
        f"📤 Отправьте Excel-файл с зарплатой за {month_name} {context.user_data['salary_year']}.\n\n"
        "Обязательные колонки: Логин, Итог\n"
        "Остальные колонки — произвольные."
    )
    return STATE_UPLOAD_SALARY_REPORT


async def handle_salary_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка загрузки файла зарплаты"""
    if not update.message.document:
        await update.message.reply_text("❌ Пожалуйста, отправьте Excel-файл.")
        return STATE_UPLOAD_SALARY_REPORT

    file = await update.message.document.get_file()
    temp_path = os.path.join(CLOUD_DIR, "Временные", "uploaded_salary.xlsx")
    await file.download_to_drive(temp_path)

    try:
        df = pd.read_excel(temp_path, engine='openpyxl')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка чтения файла: {e}")
        return STATE_UPLOAD_SALARY_REPORT

    # Проверка обязательных колонок
    if "Логин" not in df.columns or "Итог" not in df.columns:
        await update.message.reply_text(
            "❌ В файле должны быть колонки 'Логин' и 'Итог'."
        )
        return STATE_UPLOAD_SALARY_REPORT

    year = context.user_data["salary_year"]
    month_name = context.user_data["salary_month"]
    company_dir = None  # Используем общую папку

    # Проверяем, есть ли уже файл
    existing = get_existing_versions(company_dir, year, month_name)
    current_version = 0
    for v in existing:
        if v["is_current"]:
            current_version = v["version"]

    if current_version > 0:
        context.user_data["temp_salary_path"] = temp_path
        context.user_data["current_salary_version"] = current_version

        keyboard = [
            [InlineKeyboardButton("✅ Да, загрузить", callback_data="overwrite_yes")],
            [InlineKeyboardButton("❌ Отмена", callback_data="overwrite_no")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"⚠️ За {month_name} {year} уже есть отчёт (версия {current_version}).\n"
            f"Загрузить новый? Новый станет версией {current_version + 1}.",
            reply_markup=reply_markup
        )
        return STATE_CONFIRM_OVERWRITE

    # Сохраняем файл
    _save_salary_file(temp_path, company_dir, year, month_name)
    await update.message.reply_text(f"✅ Отчёт за {month_name} {year} загружен.")
    return ConversationHandler.END


async def confirm_overwrite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Подтверждение перезаписи отчёта"""
    query = update.callback_query
    await query.answer()

    if query.data == "overwrite_yes":
        temp_path = context.user_data.get("temp_salary_path")
        year = context.user_data["salary_year"]
        month_name = context.user_data["salary_month"]
        company_dir = None

        # Переименовываем старый файл
        base_path = get_salary_file_path(company_dir, year, month_name)
        current_version = context.user_data.get("current_salary_version", 0)
        if os.path.exists(base_path):
            new_name = base_path.replace(".xlsx", f"_v{current_version}.xlsx")
            shutil.move(base_path, new_name)

        # Сохраняем новый
        _save_salary_file(temp_path, company_dir, year, month_name)
        await query.edit_message_text(
            f"✅ Отчёт за {month_name} {year} загружен. Версия {current_version + 1}."
        )
    else:
        await query.edit_message_text("❌ Отменено.")

    return ConversationHandler.END


def _save_salary_file(temp_path: str, company_dir: str, year: int, month_name: str):
    """Сохранить файл зарплаты"""
    target_path = get_salary_file_path(company_dir, year, month_name)
    os.makedirs(os.path.dirname(target_path), exist_ok=True)
    shutil.copy2(temp_path, target_path)


async def view_my_salary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр своей зарплаты (сотрудник)"""
    login = context.user_data.get("login")
    if not login:
        await update.message.reply_text("❌ Ошибка авторизации. Нажмите /start")
        return

    current_year = datetime.now().year
    keyboard = []
    for y in range(current_year - 2, current_year + 1):
        keyboard.append([InlineKeyboardButton(str(y), callback_data=f"my_salary_year_{y}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите год:", reply_markup=reply_markup)


async def select_my_salary_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор года для просмотра своей зарплаты"""
    query = update.callback_query
    await query.answer()
    year = int(query.data.replace("my_salary_year_", ""))
    context.user_data["my_salary_year"] = year

    keyboard = []
    for i, month in enumerate(MONTHS_RU, 1):
        keyboard.append([InlineKeyboardButton(month, callback_data=f"my_salary_month_{i}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите месяц:", reply_markup=reply_markup)


async def select_my_salary_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор месяца для просмотра своей зарплаты"""
    query = update.callback_query
    await query.answer()
    month_num = int(query.data.replace("my_salary_month_", ""))
    month_name = MONTHS_RU[month_num - 1]
    year = context.user_data["my_salary_year"]
    login = context.user_data.get("login")

    company_dir = None
    file_path = get_salary_file_path(company_dir, year, month_name)

    if not os.path.exists(file_path):
        await query.edit_message_text(f"❌ Отчёт за {month_name} {year} ещё не загружен.")
        return

    try:
        df = pd.read_excel(file_path, engine='openpyxl')
        user_row = df[df["Логин"] == login]

        if user_row.empty:
            await query.edit_message_text(f"❌ В отчёте за {month_name} {year} нет данных по вашему логину.")
            return

        total = user_row.iloc[0]["Итог"]
        await query.edit_message_text(
            f"💰 Зарплата за {month_name} {year}\n\n"
            f"Итого: {int(total):,} сом".replace(",", " ")
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка чтения отчёта: {e}")


async def view_all_salaries(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Просмотр всех зарплат (начальник)"""
    current_year = datetime.now().year
    keyboard = []
    for y in range(current_year - 2, current_year + 1):
        keyboard.append([InlineKeyboardButton(str(y), callback_data=f"all_salary_year_{y}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите год:", reply_markup=reply_markup)


async def select_all_salary_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор года для просмотра всех зарплат"""
    query = update.callback_query
    await query.answer()
    year = int(query.data.replace("all_salary_year_", ""))
    context.user_data["all_salary_year"] = year

    keyboard = []
    for i, month in enumerate(MONTHS_RU, 1):
        keyboard.append([InlineKeyboardButton(month, callback_data=f"all_salary_month_{i}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите месяц:", reply_markup=reply_markup)


async def select_all_salary_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор месяца для просмотра всех зарплат"""
    query = update.callback_query
    await query.answer()
    month_num = int(query.data.replace("all_salary_month_", ""))
    month_name = MONTHS_RU[month_num - 1]
    year = context.user_data["all_salary_year"]

    company_dir = None
    file_path = get_salary_file_path(company_dir, year, month_name)

    if not os.path.exists(file_path):
        await query.edit_message_text(f"❌ Отчёт за {month_name} {year} ещё не загружен.")
        return

    try:
        df = pd.read_excel(file_path, engine='openpyxl')

        if df.empty:
            await query.edit_message_text(f"❌ Отчёт за {month_name} {year} пуст.")
            return

        # Формируем текстовую сводку
        lines = [f"📊 Зарплаты за {month_name} {year}\n"]
        total_fund = 0

        for _, row in df.iterrows():
            login = row.get("Логин", "—")
            total = row.get("Итог", 0)
            try:
                total = int(total)
            except (ValueError, TypeError):
                total = 0
            total_fund += total
            lines.append(f"{login} — {total:,} сом".replace(",", " "))

        lines.append(f"\nОбщий фонд: {total_fund:,} сом".replace(",", " "))

        await query.edit_message_text("\n".join(lines))

        # Кнопка скачать файл
        with open(file_path, "rb") as f:
            await query.message.reply_document(
                document=f,
                filename=f"зарплата_{month_name}_{year}.xlsx",
                caption="📥 Скачать Excel"
            )

    except Exception as e:
        await query.edit_message_text(f"❌ Ошибка чтения отчёта: {e}")


async def archive_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Меню архива отчётов"""
    current_year = datetime.now().year
    keyboard = []
    for y in range(current_year - 2, current_year + 1):
        keyboard.append([InlineKeyboardButton(str(y), callback_data=f"archive_year_{y}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("📥 Архив отчётов. Выберите год:", reply_markup=reply_markup)


async def select_archive_year(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор года в архиве"""
    query = update.callback_query
    await query.answer()
    year = int(query.data.replace("archive_year_", ""))
    context.user_data["archive_year"] = year

    keyboard = []
    for i, month in enumerate(MONTHS_RU, 1):
        keyboard.append([InlineKeyboardButton(month, callback_data=f"archive_month_{i}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text("Выберите месяц:", reply_markup=reply_markup)


async def select_archive_month(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выбор месяца в архиве"""
    query = update.callback_query
    await query.answer()
    month_num = int(query.data.replace("archive_month_", ""))
    month_name = MONTHS_RU[month_num - 1]
    year = context.user_data["archive_year"]

    company_dir = None
    versions = get_existing_versions(company_dir, year, month_name)

    if not versions:
        await query.edit_message_text(f"❌ Нет отчётов за {month_name} {year}.")
        return

    lines = [f"📥 Архив: {month_name} {year}\n"]
    for v in versions:
        status = "✅ действующая" if v["is_current"] else "📄 архив"
        lines.append(f"Версия {v['version']} — {status}")

    await query.edit_message_text("\n".join(lines))

    # Отправляем файлы
    for v in versions:
        try:
            with open(v["path"], "rb") as f:
                label = "действующая" if v["is_current"] else f"архив_v{v['version']}"
                await query.message.reply_document(
                    document=f,
                    filename=os.path.basename(v["path"]),
                    caption=f"📄 {label}"
                )
        except Exception as e:
            await query.message.reply_text(f"❌ Ошибка отправки версии {v['version']}: {e}")


def get_salary_handlers():
    """Получить обработчики для зарплат"""
    from telegram.ext import ConversationHandler

    upload_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(upload_report_start, pattern="^upload_report$")],
        states={
            STATE_SELECT_SALARY_YEAR: [CallbackQueryHandler(select_salary_year, pattern="^salary_year_")],
            STATE_SELECT_SALARY_MONTH: [CallbackQueryHandler(select_salary_month, pattern="^salary_month_")],
            STATE_UPLOAD_SALARY_REPORT: [MessageHandler(filters.Document.ALL, handle_salary_file_upload)],
            STATE_CONFIRM_OVERWRITE: [CallbackQueryHandler(confirm_overwrite, pattern="^overwrite_")],
        },
        fallbacks=[],
        name="salary_upload",
        persistent=False,
    )

    return [upload_handler]