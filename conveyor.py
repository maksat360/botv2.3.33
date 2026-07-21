"""
V2 MES System — Производственный конвейер с гибкими зависимостями

Поддерживает:
- Параллельные процессы (1, 2, 3 стартуют одновременно)
- Опциональные зависимости (процесс 3 может не участвовать)
- Точки сбора (процесс 4 ждёт 1 и 2)
- Жёсткие цепочки (5→6→7→8→9→10)
- Назначение процессов сотрудникам
"""

import os
import pandas as pd
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import (
    CONVEYOR_CONFIG_FILE, PARTIES_FILE, PHOTO_PARTIES_DIR,
    USERS_FILE, CLOUD_DIR,
)


# ========================
# ЧТЕНИЕ / ЗАПИСЬ ДАННЫХ
# ========================

def read_conveyor_config():
    """Прочитать конфигурацию конвейера"""
    if not os.path.exists(CONVEYOR_CONFIG_FILE):
        return pd.DataFrame(columns=[
            "ID", "Название", "Ответственный", "Зависимость от",
            "Обязательные зависи��ости", "Цена", "Норма времени (мин)", "Требует фотоотчёта"
        ])
    return pd.read_excel(CONVEYOR_CONFIG_FILE, engine='openpyxl')


def write_conveyor_config(df):
    """Записать конфигурацию конвейера"""
    df.to_excel(CONVEYOR_CONFIG_FILE, index=False, engine='openpyxl')


def read_parties():
    """Прочитать партии"""
    if not os.path.exists(PARTIES_FILE):
        return pd.DataFrame(columns=[
            "номер", "название", "клиент", "статус",
            "дата_начала", "дата_готовности",
            "завершённые_процессы", "активные_процессы"
        ])
    return pd.read_excel(PARTIES_FILE, engine='openpyxl')


def write_parties(df):
    """Записать партии"""
    df.to_excel(PARTIES_FILE, index=False, engine='openpyxl')


def read_users():
    """Прочитать пользователи.xlsx"""
    if not os.path.exists(USERS_FILE):
        return pd.DataFrame(columns=["логин", "пароль", "фио", "роль", "telegram_id", "активен", "процессы"])
    return pd.read_excel(USERS_FILE, engine='openpyxl')


def write_users(df):
    """Записать пользователи.xlsx"""
    df.to_excel(USERS_FILE, index=False, engine='openpyxl')


def get_employee_processes(login: str) -> list:
    """Получить список ID процессов, закреплённых за сотрудником"""
    users_df = read_users()
    user = users_df[users_df["логин"] == login]
    if user.empty:
        return []
    processes_str = user.iloc[0].get("процессы", "")
    if pd.isna(processes_str) or not processes_str:
        return []
    try:
        return [int(p.strip()) for p in str(processes_str).split(",") if p.strip()]
    except ValueError:
        return []


def parse_dependencies(dep_str) -> list:
    """Распарсить строку зависимостей вида '1,2,3' в список int"""
    if pd.isna(dep_str) or not dep_str:
        return []
    try:
        return [int(d.strip()) for d in str(dep_str).split(",") if d.strip()]
    except ValueError:
        return []


def get_available_processes(party_row, conveyor_df) -> list:
    """
    Определить, какие процессы доступны для партии.
    Проце��с доступен, если:
    1. Он ещё не завершён
    2. Он не активен сейчас
    3. Все его обязательные зависимости завершены
    """
    completed_str = party_row.get("завершённые_процессы", "")
    active_str = party_row.get("активные_процессы", "")

    completed = parse_dependencies(completed_str)
    active = parse_dependencies(active_str)

    available = []

    for _, proc in conveyor_df.iterrows():
        proc_id = int(proc["ID"])

        # Уже завершён?
        if proc_id in completed:
            continue

        # Уже активен?
        if proc_id in active:
            continue

        # Проверяем зависимости
        deps = parse_dependencies(proc.get("Зависимость от", ""))
        mandatory_deps = parse_dependencies(proc.get("Обязательные зависимости", ""))

        if not deps:
            # Нет зависимостей — процесс стартовый (доступен, если партия активна)
            available.append(proc_id)
            continue

        # Проверяем обязательные зависимости
        all_mandatory_done = all(d in completed for d in mandatory_deps)
        if not all_mandatory_done:
            continue

        # Если есть хоть одна обязательная зависимость и она выполнена — процесс доступен
        # (опциональные игнорируем)
        available.append(proc_id)

    return available


def is_process_blocked(proc_id: int, party_row, conveyor_df) -> tuple:
    """
    Проверить, заблокирован ли процесс.
    Возвращает (заблокирован: bool, причина: str)
    """
    completed_str = party_row.get("завершённые_процессы", "")
    completed = parse_dependencies(completed_str)

    proc = conveyor_df[conveyor_df["ID"] == proc_id]
    if proc.empty:
        return True, "Процесс не найден"

    proc = proc.iloc[0]
    deps = parse_dependencies(proc.get("Зависимость от", ""))
    mandatory_deps = parse_dependencies(proc.get("Обязательные зависимости", ""))

    if not deps:
        return False, ""  # Стартовый процесс

    # Проверяем обязательные
    for dep_id in mandatory_deps:
        if dep_id not in completed:
            dep_name = conveyor_df[conveyor_df["ID"] == dep_id]["Название"].values
            dep_name = dep_name[0] if len(dep_name) > 0 else f"Процесс {dep_id}"
            return True, f"ждёт завершения процесса {dep_id} ({dep_name})"

    return False, ""


# ========================
# ОСНОВНЫЕ ФУНКЦИИ
# ========================

async def show_my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать задачи текущего сотрудника"""
    login = context.user_data.get("login")
    role = context.user_data.get("role")

    if role == "начальник":
        await show_parties(update, context)
        return

    employee_processes = get_employee_processes(login)
    if not employee_processes:
        await update.message.reply_text("📋 За вами не закреплено ни одного процесса.")
        return

    parties_df = read_parties()
    conveyor_df = read_conveyor_config()

    if parties_df.empty:
        await update.message.reply_text("📋 Нет активных партий.")
        return

    active_parties = parties_df[parties_df["статус"] == "активна"]
    if active_parties.empty:
        await update.message.reply_text("📋 Нет активных партий.")
        return

    found_any = False
    for _, party in active_parties.iterrows():
        active_procs = parse_dependencies(party.get("активные_процессы", ""))

        # Ищем процессы, закреплённые за сотрудником, которые активны для этой партии
        my_active = [p for p in employee_processes if p in active_procs]

        if not my_active:
            continue

        found_any = True
        party_num = party["номер"]
        party_name = party.get("название", "")

        lines = [f"📋 Партия #{party_num} — {party_name}\n"]

        for proc_id in my_active:
            proc = conveyor_df[conveyor_df["ID"] == proc_id]
            if proc.empty:
                continue
            proc_name = proc.iloc[0]["Название"]
            needs_photo = proc.iloc[0].get("Требует фотоотчёта", "Нет")
            price = proc.iloc[0].get("Цена", "")

            price_str = f" ({price} сом)" if pd.notna(price) and price else ""
            photo_req = " 📸" if needs_photo == "Да" else ""

            lines.append(f"  🔄 Процесс {proc_id}: {proc_name}{price_str}{photo_req}")

        text = "\n".join(lines)

        keyboard = []
        for proc_id in my_active:
            keyboard.append([InlineKeyboardButton(
                f"✅ Завершить процесс {proc_id}",
                callback_data=f"party_done_{party_num}_{proc_id}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text, reply_markup=reply_markup)

    if not found_any:
        await update.message.reply_text("📋 Нет активных задач для ваших процессов.")


async def show_parties(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать все партии (для начальника)"""
    parties_df = read_parties()
    conveyor_df = read_conveyor_config()

    if parties_df.empty:
        await update.message.reply_text("📋 Нет партий.")
        return

    active_parties = parties_df[parties_df["статус"] == "активна"]
    if active_parties.empty:
        await update.message.reply_text("📋 Нет активных партий.")
        return

    for _, party in active_parties.iterrows():
        party_num = party["номер"]
        party_name = party.get("название", "")
        completed = parse_dependencies(party.get("завершённые_процессы", ""))
        active = parse_dependencies(party.get("активные_процессы", ""))

        lines = [f"📋 Партия #{party_num} — {party_name}\n"]

        for _, proc in conveyor_df.iterrows():
            proc_id = int(proc["ID"])
            proc_name = proc["Название"]
            responsible = proc.get("Ответственный", "")

            if proc_id in completed:
                lines.append(f"  ✅ Процесс {proc_id}: {proc_name} — завершён")
            elif proc_id in active:
                emp = f" ({responsible})" if pd.notna(responsible) and responsible else ""
                lines.append(f"  🔄 Процесс {proc_id}: {proc_name} — в работе{emp}")
            else:
                blocked, reason = is_process_blocked(proc_id, party, conveyor_df)
                if blocked:
                    lines.append(f"  🔒 Процесс {proc_id}: {proc_name} — {reason}")
                else:
                    lines.append(f"  ⏳ Процесс {proc_id}: {proc_name} — ожидает")

        await update.message.reply_text("\n".join(lines))


async def party_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Завершить процесс в партии"""
    query = update.callback_query
    await query.answer()

    # Формат: party_done_{party_num}_{process_id}
    data = query.data
    parts = data.replace("party_done_", "").split("_")
    if len(parts) < 2:
        await query.edit_message_text("❌ Ошибка формата данных.")
        return

    party_num = int(parts[0])
    process_id = int(parts[1])

    parties_df = read_parties()
    conveyor_df = read_conveyor_config()

    party_idx = parties_df[parties_df["номер"] == party_num].index
    if party_idx.empty:
        await query.edit_message_text("❌ Партия не найдена.")
        return

    # Проверяем, нужно ли фото
    proc = conveyor_df[conveyor_df["ID"] == process_id]
    if proc.empty:
        await query.edit_message_text("❌ Процесс не найден.")
        return

    proc_name = proc.iloc[0]["Название"]
    needs_photo = proc.iloc[0].get("Требует фотоотчёта", "Нет")

    if needs_photo == "Да":
        context.user_data["pending_photo_party"] = party_num
        context.user_data["pending_photo_process"] = process_id
        await query.edit_message_text(
            f"📸 Для процесса {process_id} '{proc_name}' требуется фотоотчёт. Отправьте фото:"
        )
        return

    # Завершаем процесс
    _complete_process(parties_df, party_idx[0], process_id, conveyor_df)
    write_parties(parties_df)

    await query.edit_message_text(f"✅ Процесс {process_id} '{proc_name}' завершён!")


def _complete_process(parties_df, idx, process_id, conveyor_df):
    """Завершить процесс: обновить списки завершённых и активных процессов"""
    completed_str = parties_df.loc[idx].get("завершённые_процессы", "")
    active_str = parties_df.loc[idx].get("активные_процессы", "")

    completed = parse_dependencies(completed_str)
    active = parse_dependencies(active_str)

    # Добавляем в завершённые
    if process_id not in completed:
        completed.append(process_id)

    # Убираем из активных
    if process_id in active:
        active.remove(process_id)

    # Проверяем, какие новые процессы стали доступны
    for _, proc in conveyor_df.iterrows():
        proc_id = int(proc["ID"])
        if proc_id in completed or proc_id in active:
            continue

        deps = parse_dependencies(proc.get("Зависимость от", ""))
        mandatory_deps = parse_dependencies(proc.get("Обязательные зависимости", ""))

        if not deps:
            # Стартовый процесс — добавляем только если партия только создана
            continue

        # Проверяем обязательные зависимости
        all_mandatory_done = all(d in completed for d in mandatory_deps)
        if all_mandatory_done:
            active.append(proc_id)

    # Обновляем в DataFrame
    parties_df.loc[idx, "завершённые_процессы"] = ",".join(str(p) for p in sorted(completed))
    parties_df.loc[idx, "активные_процессы"] = ",".join(str(p) for p in sorted(active))

    # Если все процессы завершены — партия готова
    if len(completed) >= len(conveyor_df):
        parties_df.loc[idx, "статус"] = "завершена"
        parties_df.loc[idx, "дата_готовности"] = datetime.now().strftime("%Y-%m-%d %H:%M")


async def handle_party_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка фото для завершения процесса"""
    party_num = context.user_data.get("pending_photo_party")
    process_id = context.user_data.get("pending_photo_process")

    if not party_num or process_id is None:
        await update.message.reply_text("❌ Нет ожидающих фото.")
        return

    if not update.message.photo:
        await update.message.reply_text("❌ Пожалуйста, отправьте фото.")
        return

    photo = update.message.photo[-1]
    file = await photo.get_file()

    # Сохраняем фото
    party_dir = os.path.join(PHOTO_PARTIES_DIR, f"Партия_{party_num}")
    os.makedirs(party_dir, exist_ok=True)

    photo_path = os.path.join(party_dir, f"Процесс_{process_id}.jpg")
    await file.download_to_drive(photo_path)

    # Завершаем процесс
    parties_df = read_parties()
    conveyor_df = read_conveyor_config()
    party_idx = parties_df[parties_df["номер"] == party_num].index

    if not party_idx.empty:
        _complete_process(parties_df, party_idx[0], process_id, conveyor_df)
        write_parties(parties_df)

    context.user_data.pop("pending_photo_party", None)
    context.user_data.pop("pending_photo_process", None)

    proc_name = conveyor_df[conveyor_df["ID"] == process_id]["Название"].values
    proc_name = proc_name[0] if len(proc_name) > 0 else f"Процесс {process_id}"
    await update.message.reply_text(f"✅ Фото сохранено! Процесс {process_id} '{proc_name}' завершён.")


async def create_party(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Создать новую партию (процесс 0)"""
    login = context.user_data.get("login")
    employee_processes = get_employee_processes(login)

    if 0 not in employee_processes:
        await update.message.reply_text("❌ У вас нет прав на создание партий.")
        return

    context.user_data["create_party_step"] = "waiting_name"
    await update.message.reply_text(
        "🆕 Создание новой партии.\n"
        "Введите название партии:"
    )


async def handle_create_party_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка текста при создании партии"""
    step = context.user_data.get("create_party_step")

    if step == "waiting_name":
        party_name = update.message.text.strip()
        context.user_data["new_party_name"] = party_name
        context.user_data["create_party_step"] = "waiting_client"
        await update.message.reply_text("Введите название клиента:")

    elif step == "waiting_client":
        client = update.message.text.strip()
        party_name = context.user_data.get("new_party_name", "")
        login = context.user_data.get("login", "")

        parties_df = read_parties()
        conveyor_df = read_conveyor_config()

        # Определяем номер новой партии
        new_num = 1
        if not parties_df.empty:
            new_num = int(parties_df["номер"].max()) + 1

        # Создаём запись
        new_party = pd.DataFrame([{
            "номер": new_num,
            "название": party_name,
            "клиент": client,
            "статус": "активна",
            "дата_начала": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "дата_готовности": "",
            "завершённые_процессы": "",
            "активные_процессы": "0",  # Процесс 0 стартует сразу
        }])
        parties_df = pd.concat([parties_df, new_party], ignore_index=True)
        write_parties(parties_df)

        context.user_data.pop("create_party_step", None)
        context.user_data.pop("new_party_name", None)

        await update.message.reply_text(
            f"✅ Партия #{new_num} создана!\n"
            f"📌 {party_name}\n"
            f"👤 Клиент: {client}\n\n"
            f"Процесс 0 (Раскрой) запущен. Вы можете начать работу."
        )


async def start_create_party(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Начать создание партии — вызывается из меню"""
    await create_party(update, context)