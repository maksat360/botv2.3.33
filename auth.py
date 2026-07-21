"""
V2 MES System — Авторизация, регистрация, система ID
"""

import os
import random
import string
import pandas as pd
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

from config import (
    SYSTEM_CONFIG_PATH, USERS_FILE, CLOUD_DIR, hash_password,
    ROLE_BOSS, ROLE_SUPERADMIN, MONTHS_RU, SALARY_REPORTS_DIR,
    PHOTO_PARTIES_DIR, PHOTO_DEFECTS_DIR, TEMP_DIR, REPORTS_DIR, BACKUPS_DIR,
)
from database import (
    save_session, get_session, delete_session,
    add_global_password, check_password_global,
    add_registration_request, get_all_companies, add_company,
)
from conveyor import get_employee_processes

# Состояния для ConversationHandler
(
    STATE_SELECT_COMPANY,
    STATE_LOGIN,
    STATE_REGISTER_CHOICE,
    STATE_ENTER_ID,
    STATE_ENTER_COMPANY_NAME,
    STATE_ENTER_ADMIN_NAME,
    STATE_ENTER_PASSWORD,
    STATE_SELECT_EMPLOYEES_COUNT,
    STATE_UPLOAD_EMPLOYEES,
    STATE_ENTER_NEW_COMPANY_NAME,
) = range(10)


def generate_company_id(length=8):
    """Сгенерировать ID компании"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def generate_invite_id(length=8):
    """Сгенерировать ID приглашения"""
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=length))


def read_system_config():
    """Прочитать system_config.xlsx"""
    if not os.path.exists(SYSTEM_CONFIG_PATH):
        return None
    return pd.read_excel(SYSTEM_CONFIG_PATH, sheet_name=None, engine='openpyxl')


def write_system_config(sheets_dict):
    """Записать system_config.xlsx"""
    with pd.ExcelWriter(SYSTEM_CONFIG_PATH, engine='openpyxl') as writer:
        for sheet_name, df in sheets_dict.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def read_users(company_dir: str = None):
    """Прочитать пользователи.xlsx"""
    file_path = USERS_FILE
    if company_dir:
        file_path = os.path.join(company_dir, "пользователи.xlsx")
    if not os.path.exists(file_path):
        return pd.DataFrame(columns=["логин", "пароль", "фио", "роль", "telegram_id", "активен", "процессы"])
    return pd.read_excel(file_path, engine='openpyxl')


def write_users(df, company_dir: str = None):
    """Записать пользователи.xlsx"""
    file_path = USERS_FILE
    if company_dir:
        file_path = os.path.join(company_dir, "пользователи.xlsx")
    df.to_excel(file_path, index=False, engine='openpyxl')


def init_system_config():
    """Создать system_config.xlsx при первом запуске"""
    if os.path.exists(SYSTEM_CONFIG_PATH):
        return

    os.makedirs(os.path.dirname(SYSTEM_CONFIG_PATH), exist_ok=True)

    company_id = generate_company_id()

    # Лист Компании
    companies_df = pd.DataFrame([{
        "company_id": company_id,
        "company_name": "TelegramBot ERP",
        "is_active": 1,
        "trial_ends_at": "2026-09-10",
        "max_employees": 500,
    }])

    # Лист Приглаш��ния
    invites = []
    for _ in range(20):
        invites.append({
            "ID": generate_invite_id(),
            "Статус": "свободен",
            "Компания": "",
        })
    invites_df = pd.DataFrame(invites)

    # Лист Администраторы
    admin_password = "123456789"
    admins_df = pd.DataFrame([{
        "admin_login": "Макс",
        "admin_password": admin_password,
        "company_id": company_id,
        "role": ROLE_SUPERADMIN,
    }])

    # Лист Глобальные настройки
    settings_df = pd.DataFrame([
        {"setting_key": "bot_name", "setting_value": "V2 MES System"},
        {"setting_key": "default_trial_days", "setting_value": "60"},
        {"setting_key": "temp_cleanup_minutes", "setting_value": "10"},
        {"setting_key": "pr_message", "setting_value": "Извините, нас стало слишком много..."},
    ])

    sheets = {
        "Компании": companies_df,
        "Приглашения": invites_df,
        "Администраторы": admins_df,
        "Глобальные настройки": settings_df,
    }

    write_system_config(sheets)

    # Создаём пользователи.xlsx с колонкой процессы
    users_df = pd.DataFrame([{
        "логин": "Макс",
        "пароль": admin_password,
        "фио": "Макс Админ",
        "роль": ROLE_BOSS,
        "telegram_id": "",
        "активен": 1,
        "процессы": "0,7",  # Максат — процессы 0 и 7
    }])
    write_users(users_df)

    # Добавляем в БД
    add_company(company_id, "TelegramBot ERP")
    add_global_password(hash_password(admin_password), company_id, "Макс")

    # Создаём пустые Excel-файлы
    _init_empty_excel_files()

    print(f"✅ Компания создана!")
    print(f"ID: {company_id}")
    print(f"Логин: Макс")
    print(f"Пароль: {admin_password}")

    return company_id, "Макс", admin_password


def _init_empty_excel_files():
    """Создать пустые Excel-файлы для работы"""
    from config import (
        PARTIES_FILE, TIME_TRACKING_FILE, DEFECTS_FILE, CONVEYOR_CONFIG_FILE,
    )

    # партии.xlsx — новый формат с графом зависимостей
    if not os.path.exists(PARTIES_FILE):
        parties_df = pd.DataFrame(columns=[
            "номер", "название", "клиент", "статус",
            "дата_начала", "дата_готовности",
            "завершённые_процессы", "активные_процессы"
        ])
        parties_df.to_excel(PARTIES_FILE, index=False, engine='openpyxl')

    # учёт_времени.xlsx
    if not os.path.exists(TIME_TRACKING_FILE):
        time_df = pd.DataFrame(columns=["дата", "сотрудник", "часы", "проект", "менеджер"])
        time_df.to_excel(TIME_TRACKING_FILE, index=False, engine='openpyxl')

    # брак.xlsx
    if not os.path.exists(DEFECTS_FILE):
        defects_df = pd.DataFrame(columns=[
            "партия", "процесс", "сотрудник", "фото_ссылка",
            "дата", "статус", "технолог_статус"
        ])
        defects_df.to_excel(DEFECTS_FILE, index=False, engine='openpyxl')

    # конвейер_настройки.xlsx — новый формат с зависимостями и ценами
    if not os.path.exists(CONVEYOR_CONFIG_FILE):
        conveyor_df = pd.DataFrame([
            {"ID": 0, "Название": "Раскрой (создание партий)", "Ответственный": "Максат",
             "Зависимость от": "", "Обязательные зависимости": "",
             "Цена": 12, "Норма времени (мин)": 30, "Требует фотоотчёта": "Нет"},
            {"ID": 1, "Название": "Процесс 1", "Ответственный": "",
             "Зависимость от": "0", "Обязательные зависимости": "0",
             "Цена": "", "Норма времени (мин)": 45, "Требует фотоотчёта": "Нет"},
            {"ID": 2, "Название": "Процесс 2", "Ответственный": "Гулжамал",
             "Зависимость от": "0", "Обязательные зависимости": "0",
             "Цена": "", "Норма времени (мин)": 60, "Требует фотоотчёта": "Нет"},
            {"ID": 3, "Название": "Процесс 3 (опционально)", "Ответственный": "Нуржамал",
             "Зависимость от": "0", "Обязательные зависимости": "",
             "Цена": "", "Норма времени (мин)": 30, "Требует фотоотчёта": "Нет"},
            {"ID": 4, "Название": "Сборка", "Ответственный": "Нуржамал",
             "Зависимость от": "1,2,3", "Обязательные зависимости": "1,2",
             "Цена": "", "Норма времени (мин)": 45, "Требует фотоотчёта": "Да"},
            {"ID": 5, "Название": "Процесс 5", "Ответственный": "Омка",
             "Зависимость от": "4", "Обязательные зависимости": "4",
             "Цена": "", "Норма времени (мин)": 30, "Требует фотоотчёта": "Нет"},
            {"ID": 6, "Название": "Процесс 6", "Ответственный": "",
             "Зависимость от": "5", "Обязательные зависимости": "5",
             "Цена": "", "Норма времени (мин)": 30, "Требует фотоотчёта": "Нет"},
            {"ID": 7, "Название": "Процесс 7", "Ответственный": "Максат",
             "Зависимость от": "6", "Обязательные зависимости": "6",
             "Цена": 16.2, "Норма времени (мин)": 40, "Требует фотоотчёта": "Да"},
            {"ID": 8, "Название": "Процесс 8", "Ответственный": "Гулжамал",
             "Зависимость от": "7", "Обязательные зависимости": "7",
             "Цена": "", "Норма времени (мин)": 35, "Требует фотоотчёта": "Нет"},
            {"ID": 9, "Название": "Процесс 9", "Ответственный": "Омка",
             "Зависимость от": "8", "Обязательные зависимости": "8",
             "Цена": "", "Норма времени (мин)": 25, "Требует фотоотчёта": "Нет"},
            {"ID": 10, "Название": "Процесс 10", "Ответственный": "",
             "Зависимость от": "9", "Обязательные зависимости": "9",
             "Цена": "", "Норма времени (мин)": 20, "Требует фотоотчёта": "Да"},
        ])
        conveyor_df.to_excel(CONVEYOR_CONFIG_FILE, index=False, engine='openpyxl')

    # Создаём папки
    for d in [SALARY_REPORTS_DIR, PHOTO_PARTIES_DIR, PHOTO_DEFECTS_DIR,
              TEMP_DIR, REPORTS_DIR, BACKUPS_DIR]:
        os.makedirs(d, exist_ok=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    telegram_id = update.effective_user.id

    # Проверяем, есть ли активная сессия
    session = get_session(telegram_id)
    if session:
        company_id = session["company_id"]
        login = session["login"]
        role = session["role"]
        context.user_data["company_id"] = company_id
        context.user_data["login"] = login
        context.user_data["role"] = role
        await show_main_menu(update, context, role)
        return

    # Показываем список компаний
    companies = get_all_companies()
    keyboard = []
    for company in companies:
        keyboard.append([InlineKeyboardButton(
            f"🏢 {company['company_name']}",
            callback_data=f"select_company_{company['company_id']}"
        )])

    keyboard.append([InlineKeyboardButton("🆕 Зарегистрировать компанию", callback_data="register_company")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🏢 Выберите компанию:",
        reply_markup=reply_markup
    )
    return STATE_SELECT_COMPANY


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик нажатий на кнопки"""
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("select_company_"):
        company_id = data.replace("select_company_", "")
        context.user_data["selected_company_id"] = company_id
        await query.edit_message_text(
            "🔑 Введите логин и пароль через пробел.\n\n"
            "Пример: Макс 123456789"
        )
        return STATE_LOGIN

    elif data == "register_company":
        keyboard = [
            [InlineKeyboardButton("🔑 У меня есть ID", callback_data="have_id")],
            [InlineKeyboardButton("🆔 Получить ID", callback_data="get_id")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "Выберите действие:",
            reply_markup=reply_markup
        )
        return STATE_REGISTER_CHOICE

    elif data == "have_id":
        await query.edit_message_text("Введите ID приглашения:")
        return STATE_ENTER_ID

    elif data == "get_id":
        await query.edit_message_text(
            "Введите название вашей компании:"
        )
        return STATE_ENTER_NEW_COMPANY_NAME

    return ConversationHandler.END


async def handle_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода логина и пароля"""
    text = update.message.text.strip()
    parts = text.split(" ", 1)

    if len(parts) != 2:
        await update.message.reply_text(
            "❌ Неверный формат. Введите логин и пароль через пробел.\n"
            "Пример: Макс 123456789"
        )
        return STATE_LOGIN

    login, password = parts
    company_id = context.user_data.get("selected_company_id")

    if not company_id:
        await update.message.reply_text("❌ Ошибка: компания не выбрана. Начните заново: /start")
        return ConversationHandler.END

    # Проверяем пользователя
    users_df = read_users()
    user = users_df[(users_df["логин"] == login) & (users_df["пароль"] == password)]

    if user.empty:
        await update.message.reply_text(
            "❌ Неверный логин или пароль. Попробуйте ещё раз.\n"
            "Или начните заново: /start"
        )
        return STATE_LOGIN

    user_row = user.iloc[0]
    role = user_row["роль"]
    telegram_id = update.effective_user.id

    # Сохраняем сессию
    save_session(telegram_id, company_id, login, role)
    context.user_data["company_id"] = company_id
    context.user_data["login"] = login
    context.user_data["role"] = role

    # Обновляем telegram_id в файле
    users_df.loc[users_df["логин"] == login, "telegram_id"] = str(telegram_id)
    write_users(users_df)

    await update.message.reply_text(f"👋 Добро пожаловать, {login}!")
    await show_main_menu(update, context, role)
    return ConversationHandler.END


async def handle_enter_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода ID приглашения"""
    invite_id = update.message.text.strip()
    sheets = read_system_config()

    if sheets is None:
        await update.message.reply_text("❌ Ошибка конфигурации. Обратитесь к администратору.")
        return ConversationHandler.END

    invites_df = sheets["Приглашения"]
    invite = invites_df[invites_df["ID"] == invite_id]

    if invite.empty:
        await update.message.reply_text("❌ Неверный ID. Проверьте и попробуйте снова.")
        return STATE_ENTER_ID

    if invite.iloc[0]["Статус"] != "свободен":
        await update.message.reply_text("❌ Этот ID уже занят.")
        return STATE_ENTER_ID

    context.user_data["invite_id"] = invite_id
    await update.message.reply_text("Введите название компании:")
    return STATE_ENTER_COMPANY_NAME


async def handle_enter_company_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода названия компании"""
    company_name = update.message.text.strip()
    context.user_data["new_company_name"] = company_name
    await update.message.reply_text("Введите ваше имя (администратор):")
    return STATE_ENTER_ADMIN_NAME


async def handle_enter_admin_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода имени администратора"""
    admin_name = update.message.text.strip()
    context.user_data["admin_name"] = admin_name
    await update.message.reply_text("Придумайте пароль (минимум 6 символов):")
    return STATE_ENTER_PASSWORD


async def handle_enter_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода пароля"""
    password = update.message.text.strip()

    if len(password) < 6:
        await update.message.reply_text("❌ Пароль должен быть минимум 6 символов. Попробуйте снова:")
        return STATE_ENTER_PASSWORD

    # Проверяем глобальную уникальность
    password_hash = hash_password(password)
    if check_password_global(password_hash):
        await update.message.reply_text(
            "❌ Этот пароль уже используется в другой компании. Придумайте другой:"
        )
        return STATE_ENTER_PASSWORD

    context.user_data["password"] = password
    context.user_data["password_hash"] = password_hash

    keyboard = [
        [InlineKeyboardButton("1–10", callback_data="count_10")],
        [InlineKeyboardButton("11–30", callback_data="count_30")],
        [InlineKeyboardButton("31–100", callback_data="count_100")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "Сколько сотрудников планируется?",
        reply_markup=reply_markup
    )
    return STATE_SELECT_EMPLOYEES_COUNT


async def handle_employees_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора количества сотрудников"""
    query = update.callback_query
    await query.answer()
    data = query.data

    count_map = {
        "count_10": 10,
        "count_30": 30,
        "count_100": 100,
    }
    max_employees = count_map.get(data, 10)
    context.user_data["max_employees"] = max_employees

    # Создаём шаблон Excel
    import io
    import pandas as pd

    template_df = pd.DataFrame(columns=["логин", "пароль", "фио", "роль", "процессы"])
    # Добавляем пустые строки
    for _ in range(max_employees):
        template_df.loc[len(template_df)] = ["", "", "", "", ""]

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        template_df.to_excel(writer, index=False, sheet_name="Сотрудники")
    buffer.seek(0)

    await query.edit_message_text(
        f"📋 Шаблон на {max_employees} сотрудников готов.\n"
        "Заполните: логин, пароль, ФИО, роль (начальник/технолог/табельщик/бухгалтер/сотрудник), процессы (ID через запятую, например: 0,7).\n\n"
        "❗ Обязательно: хотя бы один начальник, все логины уникальны.\n\n"
        "Отправьте заполненный Excel-файл:"
    )

    # Сохраняем шаблон во временную папку
    template_path = os.path.join(TEMP_DIR, "template.xlsx")
    with open(template_path, "wb") as f:
        f.write(buffer.getvalue())

    context.user_data["template_path"] = template_path
    return STATE_UPLOAD_EMPLOYEES


async def handle_upload_employees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка загрузки файла с сотрудниками"""
    if not update.message.document:
        await update.message.reply_text("❌ Пожалуйста, отправьте Excel-файл.")
        return STATE_UPLOAD_EMPLOYEES

    file = await update.message.document.get_file()
    file_path = os.path.join(TEMP_DIR, "uploaded_employees.xlsx")
    await file.download_to_drive(file_path)

    try:
        df = pd.read_excel(file_path, engine='openpyxl')
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка чтения файла: {e}")
        return STATE_UPLOAD_EMPLOYEES

    # Проверки
    required_cols = ["логин", "пароль", "фио", "роль"]
    for col in required_cols:
        if col not in df.columns:
            await update.message.reply_text(f"❌ В файле нет колонки '{col}'.")
            return STATE_UPLOAD_EMPLOYEES

    # Убираем пустые строки
    df = df.dropna(subset=["логин", "пароль"]).reset_index(drop=True)

    if df.empty:
        await update.message.reply_text("❌ Файл пуст. Заполните хотя бы одного сотрудника.")
        return STATE_UPLOAD_EMPLOYEES

    # Проверка уникальности логинов
    if df["логин"].duplicated().any():
        await update.message.reply_text("❌ Есть повторяющиеся логины. Исправьте и отправьте снова.")
        return STATE_UPLOAD_EMPLOYEES

    # Проверка уникальности паролей глобально
    for _, row in df.iterrows():
        if check_password_global(hash_password(str(row["пароль"]))):
            await update.message.reply_text(
                f"❌ Пароль для '{row['логин']}' уже используется в другой компании."
            )
            return STATE_UPLOAD_EMPLOYEES

    # Проверка наличия начальника
    if "начальник" not in df["роль"].str.lower().values:
        await update.message.reply_text("❌ Нужен хотя бы один начальник.")
        return STATE_UPLOAD_EMPLOYEES

    # Всё ок — создаём компанию
    invite_id = context.user_data.get("invite_id")
    company_name = context.user_data["new_company_name"]
    admin_name = context.user_data["admin_name"]
    password = context.user_data["password"]
    max_employees = context.user_data["max_employees"]

    # Генерируем ID компании
    company_id = generate_company_id()

    # Создаём папку компании
    company_dir = os.path.join(CLOUD_DIR, company_id)
    os.makedirs(company_dir, exist_ok=True)

    # Создаём пользователи.xlsx для компании
    if "процессы" not in df.columns:
        df["процессы"] = ""
    df["активен"] = 1
    df["telegram_id"] = ""
    df.to_excel(os.path.join(company_dir, "пользователи.xlsx"), index=False, engine='openpyxl')

    # Добавляем администратора
    admin_df = pd.DataFrame([{
        "логин": admin_name,
        "пароль": password,
        "фио": f"{admin_name} Админ",
        "роль": "начальник",
        "telegram_id": "",
        "активен": 1,
        "процессы": "",
    }])
    admin_df.to_excel(os.path.join(company_dir, "администратор.xlsx"), index=False, engine='openpyxl')

    # Обновляем system_config.xlsx
    sheets = read_system_config()
    if sheets:
        # Обновляем статус ID
        invites_df = sheets["Приглашения"]
        invites_df.loc[invites_df["ID"] == invite_id, "Статус"] = "занят"
        invites_df.loc[invites_df["ID"] == invite_id, "Компания"] = company_name
        sheets["Приглашения"] = invites_df

        # Добавляем компанию
        companies_df = sheets["Компании"]
        new_company = pd.DataFrame([{
            "company_id": company_id,
            "company_name": company_name,
            "is_active": 1,
            "trial_ends_at": "",
            "max_employees": max_employees,
        }])
        companies_df = pd.concat([companies_df, new_company], ignore_index=True)
        sheets["Компании"] = companies_df

        write_system_config(sheets)

    # Добавляем в БД
    add_company(company_id, company_name, max_employees)
    for _, row in df.iterrows():
        add_global_password(hash_password(str(row["пароль"])), company_id, row["логин"])

    # Создаём пустые файлы для компании
    for fname in ["партии.xlsx", "учёт_времени.xlsx", "брак.xlsx", "конвейер_настройки.xlsx"]:
        empty_df = pd.DataFrame()
        empty_df.to_excel(os.path.join(company_dir, fname), index=False, engine='openpyxl')

    # Создаём папки для компании
    for d in ["Зарплатные_отчеты", "Фото_партий", "Фото_брака", "Временные", "Отчёты", "backups"]:
        os.makedirs(os.path.join(company_dir, d), exist_ok=True)

    await update.message.reply_text(
        f"✅ Компания '{company_name}' успешно создана!\n\n"
        f"👤 Администратор: {admin_name}\n"
        f"🔑 Пароль: {password}\n"
        f"👥 Сотрудников: {len(df)}\n\n"
        f"Войдите через /start"
    )

    return ConversationHandler.END


async def handle_new_company_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка заявки на новую компанию"""
    company_name = update.message.text.strip()
    username = update.effective_user.username or update.effective_user.first_name

    add_registration_request(company_name, username)

    await update.message.reply_text(
        f"✅ Заявка отправлена!\n\n"
        f"Компания: {company_name}\n"
        f"Контакт: @{username}\n\n"
        f"Администратор свяжется с вами в ближайшее время."
    )
    return ConversationHandler.END


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, role: str):
    """Показать главное меню в зависимости от роли"""
    from telegram import ReplyKeyboardMarkup

    login = context.user_data.get("login", "")

    if role == "начальник":
        keyboard = [
            ["📊 Производство", "📋 Партии"],
            ["📸 Брак", "💰 Зарплаты"],
            ["📊 Все зарплаты", "⏱ Учёт времени"],
            ["👥 Сотрудники", "📥 Архив отчётов"],
            ["🚪 Выйти"],
        ]
    elif role == "технолог":
        keyboard = [
            ["📋 Партии", "📸 Брак"],
            ["🚪 Выйти"],
        ]
    elif role == "табельщик":
        keyboard = [
            ["⏱ Учёт времени"],
            ["🚪 Выйти"],
        ]
    elif role == "бухгалтер":
        keyboard = [
            ["💰 Зарплаты", "📤 Загрузить отчёт"],
            ["🚪 Выйти"],
        ]
    else:  # сотрудник
        # Проверяем, есть ли у сотрудника процесс 0 (раскройщик)
        employee_procs = get_employee_processes(login)
        has_process_0 = 0 in employee_procs

        if has_process_0:
            keyboard = [
                ["📋 Мои задачи", "🆕 Создать партию"],
                ["📸 Брак", "💰 Моя зарплата"],
                ["⏱ Мои часы"],
                ["🚪 Выйти"],
            ]
        else:
            keyboard = [
                ["📋 Мои задачи", "📸 Брак"],
                ["💰 Моя зарплата", "⏱ Мои часы"],
                ["🚪 Выйти"],
            ]

    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    msg = await update.message.reply_text(
        f"👋 Добро пожаловать, {login}!",
        reply_markup=reply_markup
    )
    # Сохраняем ID сообщения с меню
    context.user_data["menu_message_id"] = msg.message_id


async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Выход из системы"""
    telegram_id = update.effective_user.id
    delete_session(telegram_id)
    context.user_data.clear()

    await update.message.reply_text(
        "👋 Вы вышли из системы. Для входа нажмите /start"
    )


def get_auth_handlers():
    """Получить обработчики для регистрации"""
    from telegram.ext import ConversationHandler

    conv_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.COMMAND, start)],
        states={
            STATE_SELECT_COMPANY: [CallbackQueryHandler(button_callback)],
            STATE_LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_login)],
            STATE_REGISTER_CHOICE: [CallbackQueryHandler(button_callback)],
            STATE_ENTER_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_enter_id)],
            STATE_ENTER_COMPANY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_enter_company_name)],
            STATE_ENTER_ADMIN_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_enter_admin_name)],
            STATE_ENTER_PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_enter_password)],
            STATE_SELECT_EMPLOYEES_COUNT: [CallbackQueryHandler(handle_employees_count)],
            STATE_UPLOAD_EMPLOYEES: [MessageHandler(filters.Document.ALL, handle_upload_employees)],
            STATE_ENTER_NEW_COMPANY_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_new_company_name)],
        },
        fallbacks=[MessageHandler(filters.COMMAND, start)],
        name="auth_conversation",
        persistent=False,
    )

    return [conv_handler]