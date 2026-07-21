"""
V2 MES System — Дэшборд начальника с графом зависимостей и расчётом стоимости
"""

import os
import pandas as pd
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes

from config import PARTIES_FILE, CONVEYOR_CONFIG_FILE


def read_parties():
    """Прочитать партии"""
    if not os.path.exists(PARTIES_FILE):
        return pd.DataFrame(columns=[
            "номер", "название", "клиент", "статус",
            "дата_начала", "дата_готовности",
            "завершённые_процессы", "активные_процессы"
        ])
    return pd.read_excel(PARTIES_FILE, engine='openpyxl')


def read_conveyor_config():
    """Прочитать конфигурацию конвейера"""
    if not os.path.exists(CONVEYOR_CONFIG_FILE):
        return pd.DataFrame(columns=[
            "ID", "Название", "Ответственный", "Зависимость от",
            "Обязательные зависимости", "Цена", "Норма времени (мин)", "Требует фотоотчёта"
        ])
    return pd.read_excel(CONVEYOR_CONFIG_FILE, engine='openpyxl')


def parse_dependencies(dep_str) -> list:
    """Распарсить строку зависимостей в список int"""
    if pd.isna(dep_str) or not dep_str:
        return []
    try:
        return [int(d.strip()) for d in str(dep_str).split(",") if d.strip()]
    except ValueError:
        return []


def get_process_price(proc_id: int, conveyor_df) -> float:
    """Получить цену процесса. Возвращает 0, если цена не указана."""
    proc = conveyor_df[conveyor_df["ID"] == proc_id]
    if proc.empty:
        return 0.0
    price = proc.iloc[0].get("Цена", "")
    if pd.isna(price) or price == "":
        return 0.0
    try:
        return float(price)
    except (ValueError, TypeError):
        return 0.0


def calculate_party_cost(completed: list, conveyor_df) -> float:
    """Рассчитать общую стоимость завершённых процессов партии"""
    total = 0.0
    for proc_id in completed:
        total += get_process_price(proc_id, conveyor_df)
    return total


def is_process_blocked(proc_id: int, completed: list, conveyor_df) -> tuple:
    """
    Проверить, заблокирован ли процесс.
    Возвращает (заблокирован: bool, причина: str)
    """
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
            return True, f"ждёт процесса {dep_id} ({dep_name})"

    return False, ""


async def show_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показать производственный дэшборд с графом зависимостей и стоимостью"""
    parties_df = read_parties()
    conveyor_df = read_conveyor_config()

    if parties_df.empty:
        await update.message.reply_text("📊 Нет активных партий.")
        return

    if conveyor_df.empty:
        await update.message.reply_text("📊 Не настроен конвейер.")
        return

    active_parties = parties_df[parties_df["статус"] == "активна"]
    if active_parties.empty:
        await update.message.reply_text("📊 Нет активных партий.")
        return

    lines = ["📊 ПРОИЗВОДСТВО\n"]
    grand_total_cost = 0.0

    for _, party in active_parties.iterrows():
        party_num = party["номер"]
        party_name = party.get("название", "")
        completed = parse_dependencies(party.get("завершённые_процессы", ""))
        active = parse_dependencies(party.get("активные_процессы", ""))

        # Расчёт стоимости партии
        party_cost = calculate_party_cost(completed, conveyor_df)
        grand_total_cost += party_cost

        lines.append(f"📦 Партия #{party_num} — {party_name}")

        for _, proc in conveyor_df.iterrows():
            proc_id = int(proc["ID"])
            proc_name = proc["Название"]
            responsible = proc.get("Ответственный", "")
            emp = f" ({responsible})" if pd.notna(responsible) and responsible else ""

            # Цена процесса
            price = get_process_price(proc_id, conveyor_df)
            price_str = f" [{price:.1f} сом]" if price > 0 else ""

            if proc_id in completed:
                lines.append(f"  ✅ Процесс {proc_id}: {proc_name}{emp}{price_str} — завершён")
            elif proc_id in active:
                lines.append(f"  🔄 Процесс {proc_id}: {proc_name}{emp}{price_str} — в работе")
            else:
                blocked, reason = is_process_blocked(proc_id, completed, conveyor_df)
                if blocked:
                    lines.append(f"  🔒 Процесс {proc_id}: {proc_name}{emp} — {reason}")
                else:
                    lines.append(f"  ⏳ Процесс {proc_id}: {proc_name}{emp} — ожидает")

        # Стоимость партии
        lines.append(f"  💰 Стоимость партии: {party_cost:.1f} сом")
        lines.append("")  # пустая строка между партиями

    # Общая стоимость всех активных партий
    lines.append(f"📊 Общая стоимость в работе: {grand_total_cost:.1f} сом\n")

    # Прогноз
    lines.append("📈 Прогноз:")
    for _, party in active_parties.iterrows():
        party_num = party["номер"]
        completed = parse_dependencies(party.get("завершённые_процессы", ""))
        remaining = len(conveyor_df) - len(completed)

        if remaining <= 0:
            lines.append(f"  Партия #{party_num} — завершается")
            continue

        total_time = 0
        remaining_cost = 0.0
        for _, proc in conveyor_df.iterrows():
            proc_id = int(proc["ID"])
            if proc_id not in completed:
                total_time += proc.get("Норма времени (мин)", 0) or 0
                remaining_cost += get_process_price(proc_id, conveyor_df)

        eta = datetime.now() + timedelta(minutes=total_time)
        lines.append(
            f"  Партия #{party_num} — осталось {remaining} процессов, "
            f"~{total_time} мин, +{remaining_cost:.1f} сом, "
            f"готовность ~{eta.strftime('%d.%m %H:%M')}"
        )

    await update.message.reply_text("\n".join(lines))