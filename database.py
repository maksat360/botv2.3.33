"""
V2 MES System — База данных SQLite
Хранит: компании, сессии, глобальные пароли
"""

import sqlite3
import os
from config import DB_PATH


def get_connection():
    """Получить соединение с БД"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Инициализация таблиц БД"""
    conn = get_connection()
    cursor = conn.cursor()

    # Компании
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            company_id TEXT PRIMARY KEY,
            company_name TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            trial_ends_at TEXT,
            max_employees INTEGER DEFAULT 500,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Сессии (Telegram ID → компания)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            telegram_id INTEGER PRIMARY KEY,
            company_id TEXT NOT NULL,
            login TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    # Глобальные пароли (для проверки уникальности)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_passwords (
            password_hash TEXT PRIMARY KEY,
            company_id TEXT NOT NULL,
            login TEXT NOT NULL
        )
    """)

    # Заявки на регистрацию
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registration_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT NOT NULL,
            contact_username TEXT,
            status TEXT DEFAULT 'new',
            created_at TEXT DEFAULT (datetime('now'))
        )
    """)

    conn.commit()
    conn.close()


def save_session(telegram_id: int, company_id: str, login: str, role: str):
    """Сохранить сессию пользователя"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR REPLACE INTO sessions (telegram_id, company_id, login, role)
        VALUES (?, ?, ?, ?)
    """, (telegram_id, company_id, login, role))
    conn.commit()
    conn.close()


def get_session(telegram_id: int):
    """Получить сессию по Telegram ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM sessions WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_session(telegram_id: int):
    """Удалить сессию"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sessions WHERE telegram_id = ?", (telegram_id,))
    conn.commit()
    conn.close()


def add_global_password(password_hash: str, company_id: str, login: str):
    """Добавить пароль в глобальный реестр"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO global_passwords (password_hash, company_id, login)
        VALUES (?, ?, ?)
    """, (password_hash, company_id, login))
    conn.commit()
    conn.close()


def check_password_global(password_hash: str) -> bool:
    """Проверить, занят ли пароль глобально"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM global_passwords WHERE password_hash = ?", (password_hash,))
    row = cursor.fetchone()
    conn.close()
    return row is not None


def add_registration_request(company_name: str, contact_username: str = None):
    """Добавить заявку на регистрацию"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO registration_requests (company_name, contact_username)
        VALUES (?, ?)
    """, (company_name, contact_username))
    conn.commit()
    request_id = cursor.lastrowid
    conn.close()
    return request_id


def get_registration_requests(status: str = None):
    """Получить заявки на регистрацию"""
    conn = get_connection()
    cursor = conn.cursor()
    if status:
        cursor.execute("SELECT * FROM registration_requests WHERE status = ? ORDER BY created_at DESC", (status,))
    else:
        cursor.execute("SELECT * FROM registration_requests ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_all_companies():
    """Получить все компании"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM companies ORDER BY company_name")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_company(company_id: str):
    """Получить компанию по ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM companies WHERE company_id = ?", (company_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def add_company(company_id: str, company_name: str, max_employees: int = 500):
    """Добавить компанию"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO companies (company_id, company_name, max_employees)
        VALUES (?, ?, ?)
    """, (company_id, company_name, max_employees))
    conn.commit()
    conn.close()