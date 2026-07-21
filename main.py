"""
V2 MES System — Точка входа
MES-система управления производством в Telegram
"""

import logging
import os
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ConversationHandler,
)

from config import BOT_TOKEN, ROLE_BOSS, ROLE_TECHNOLOGIST, ROLE_TIMESHEET, ROLE_ACCOUNTANT
from database import init_db
from auth import (
    init_system_config, start, button_callback, handle_login,
    handle_enter_id, handle_enter_company_name, handle_enter_admin_name,
    handle_enter_password, handle_employees_count, handle_upload_employees,
    handle_new_company_name, logout, get_auth_handlers,
    STATE_SELECT_COMPANY, STATE_LOGIN, STATE_REGISTER_CHOICE,
    STATE_ENTER_ID, STATE_ENTER_COMPANY_NAME, STATE_ENTER_ADMIN_NAME,
    STATE_ENTER_PASSWORD, STATE_SELECT_EMPLOYEES_COUNT, STATE_UPLOAD_EMPLOYEES,
    STATE_ENTER_NEW_COMPANY_NAME,
)
from salary import (
    salary_menu, upload_report_start, select_salary_year, select_salary_month,
    handle_salary_file_upload, confirm_overwrite,
    view_my_salary, select_my_salary_year, select_my_salary_month,
    view_all_salaries, select_all_salary_year, select_all_salary_month,
    archive_menu, select_archive_year, select_archive_month,
    get_salary_handlers,
)
from conveyor import (
    show_parties, party_done, handle_party_photo, show_my_tasks,
    create_party, handle_create_party_text,
)
from defect import (
    report_defect, handle_defect_text, handle_defect_photo,
    view_defects, handle_defect_action,
)
from dashboard import show_dashboard
from time_tracking import (
    time_tracking_menu, add_shift_start, select_employee,
    enter_date, enter_hours, view_my_hours, select_my_hours_month,
    get_time_tracking_handlers,
)
from scheduler import start_scheduler

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler("bot.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def handle_menu(update: Update, context):
    """Обработчик кнопок главного меню"""
    text = update.message.text
    role = context.user_data.get("role")
    login = context.user_data.get("login")

    # Проверка авторизации
    if not role:
        await update.message.reply_text("❌ Пожалуйста, авторизуйтесь: /start")
        return

    # Проверяем, не в процессе ли создания партии
    if context.user_data.get("create_party_step"):
        await handle_create_party_text(update, context)
        return

    # === НАЧАЛЬНИК ===
    if text == "📊 Производство" and role in [ROLE_BOSS]:
        await show_dashboard(update, context)

    elif text == "📋 Партии" and role in [ROLE_BOSS, ROLE_TECHNOLOGIST]:
        await show_parties(update, context)

    elif text == "📸 Брак":
        await view_defects(update, context)

    elif text == "💰 Зарплаты" and role in [ROLE_BOSS, ROLE_ACCOUNTANT]:
        await salary_menu(update, context)

    elif text == "📊 Все зарплаты" and role == ROLE_BOSS:
        await view_all_salaries(update, context)

    elif text == "⏱ Учёт времени" and role in [ROLE_BOSS, ROLE_TIMESHEET]:
        await time_tracking_menu(update, context)

    elif text == "👥 Сотрудники" and role == ROLE_BOSS:
        await update.message.reply_text("👥 Управление сотрудниками (в разработке)")

    elif text == "📥 Архив отчётов" and role == ROLE_BOSS:
        await archive_menu(update, context)

    # === ТЕХНОЛОГ ===
    elif text == "📋 Партии" and role == ROLE_TECHNOLOGIST:
        await show_parties(update, context)

    # === ТАБЕЛЬЩИК ===
    elif text == "⏱ Учёт времени" and role == ROLE_TIMESHEET:
        await time_tracking_menu(update, context)

    # === БУХГАЛТЕР ===
    elif text == "📤 Загрузить отчёт" and role == ROLE_ACCOUNTANT:
        await upload_report_start(update, context)

    # === СОТРУДНИК ===
    elif text == "📋 Мои задачи":
        await show_my_tasks(update, context)

    elif text == "💰 Моя зарплата":
        await view_my_salary(update, context)

    elif text == "⏱ Мои часы":
        await view_my_hours(update, context)

    elif text == "🆕 Создать партию":
        await create_party(update, context)

    # === ОБЩЕЕ ===
    elif text == "🚪 Выйти":
        await logout(update, context)

    else:
        await update.message.reply_text("❌ Неизвестная команда. Используйте кнопки меню.")


async def handle_photo(update: Update, context):
    """Обработчик фотографий"""
    # Проверяем, ожидается ли фото для брака
    if context.user_data.get("defect_step") == "waiting_photo":
        await handle_defect_photo(update, context)
        return

    # Проверяем, ожидается ли фото для партии
    if context.user_data.get("pending_photo_party"):
        await handle_party_photo(update, context)
        return

    await update.message.reply_text("📸 Фото получено, но не было ожидающего запроса.")


async def handle_document(update: Update, context):
    """Обработчик документов"""
    # Проверяем, ожидается ли файл сотрудников
    if context.user_data.get("template_path"):
        await handle_upload_employees(update, context)
        return

    await update.message.reply_text("📄 Документ получен.")


async def error_handler(update: Update, context):
    """Глобальный обработчик ошибок"""
    logger.error(f"Ошибка: {context.error}", exc_info=context.error)

    if update and update.effective_message:
        from marketing import get_pr_message
        await update.effective_message.reply_text(get_pr_message())


def main():
    """Главная функция запуска бота"""
    # Проверка токена
    if not BOT_TOKEN or BOT_TOKEN == "ВАШ_ТОКЕН_ОТ_BOTFATHER":
        print("❌ Ошибка: Вставьте токен бота в config.py!")
        print("   BOT_TOKEN = 'ваш_токен_от_BotFather'")
        sys.exit(1)

    # Инициализация
    print("🔄 Инициализация системы...")
    init_db()
    init_system_config()

    # Запуск фоновых задач
    start_scheduler()

    # Создание приложения
    application = Application.builder().token(BOT_TOKEN).build()

    # Регистрация обработчиков
    # Авторизация
    auth_handlers = get_auth_handlers()
    for handler in auth_handlers:
        application.add_handler(handler)

    # Зарплаты
    salary_handlers = get_salary_handlers()
    for handler in salary_handlers:
        application.add_handler(handler)

    # Учёт времени
    time_handlers = get_time_tracking_handlers()
    for handler in time_handlers:
        application.add_handler(handler)

    # Callback-обработчики
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^select_company_"))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^register_company$"))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^have_id$"))
    application.add_handler(CallbackQueryHandler(button_callback, pattern="^get_id$"))
    application.add_handler(CallbackQueryHandler(handle_employees_count, pattern="^count_"))
    application.add_handler(CallbackQueryHandler(party_done, pattern="^party_done_"))
    application.add_handler(CallbackQueryHandler(handle_defect_action, pattern="^defect_"))
    application.add_handler(CallbackQueryHandler(select_my_salary_year, pattern="^my_salary_year_"))
    application.add_handler(CallbackQueryHandler(select_my_salary_month, pattern="^my_salary_month_"))
    application.add_handler(CallbackQueryHandler(select_all_salary_year, pattern="^all_salary_year_"))
    application.add_handler(CallbackQueryHandler(select_all_salary_month, pattern="^all_salary_month_"))
    application.add_handler(CallbackQueryHandler(select_archive_year, pattern="^archive_year_"))
    application.add_handler(CallbackQueryHandler(select_archive_month, pattern="^archive_month_"))
    application.add_handler(CallbackQueryHandler(select_my_hours_month, pattern="^my_hours_month_"))

    # Команды
    application.add_handler(CommandHandler("start", start))

    # Текстовые сообщения (меню)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu))

    # Фото
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    # Документы
    application.add_handler(MessageHandler(filters.Document.ALL, handle_document))

    # Ошибки
    application.add_error_handler(error_handler)

    # Запуск
    print("✅ V2 MES System запущен!")
    print("📱 Бот слушает Telegram...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()