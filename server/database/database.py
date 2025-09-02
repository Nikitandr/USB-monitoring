import sqlite3
import os
from typing import Optional
from database.models import User, Device, Permission, Request

class Database:
    """Класс для управления базой данных"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.user = User(db_path)
        self.device = Device(db_path)
        self.permission = Permission(db_path)
        self.request = Request(db_path)
    
    def init_db(self) -> bool:
        """Инициализация базы данных"""
        try:
            # Создаем директорию для БД если не существует
            db_dir = os.path.dirname(self.db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Создание таблицы пользователей
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                )
                """)
                
                # Создание таблицы устройств
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS devices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vid TEXT NOT NULL,
                    pid TEXT NOT NULL,
                    serial TEXT NOT NULL,
                    name TEXT DEFAULT '',
                    description TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    UNIQUE(vid, pid, serial)
                )
                """)
                
                # Создание таблицы разрешений
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS permissions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    granted BOOLEAN NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE,
                    UNIQUE(user_id, device_id)
                )
                """)
                
                # Создание таблицы запросов
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    device_id INTEGER NOT NULL,
                    device_info TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    processed_at TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                    FOREIGN KEY (device_id) REFERENCES devices (id) ON DELETE CASCADE
                )
                """)
                
                # Создание индексов для оптимизации
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_devices_identifiers ON devices(vid, pid, serial)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_permissions_user ON permissions(user_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_permissions_device ON permissions(device_id)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_requests_user ON requests(user_id)")
                
                conn.commit()
                return True
                
        except Exception as e:
            print(f"Ошибка инициализации базы данных: {e}")
            return False
    
    def check_connection(self) -> bool:
        """Проверка соединения с базой данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                return True
        except Exception:
            return False
    
    def get_stats(self) -> dict:
        """Получение статистики базы данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Количество пользователей
                cursor.execute("SELECT COUNT(*) FROM users")
                users_count = cursor.fetchone()[0]
                
                # Количество устройств
                cursor.execute("SELECT COUNT(*) FROM devices")
                devices_count = cursor.fetchone()[0]
                
                # Количество разрешений
                cursor.execute("SELECT COUNT(*) FROM permissions WHERE granted = 1")
                permissions_count = cursor.fetchone()[0]
                
                # Количество ожидающих запросов
                cursor.execute("SELECT COUNT(*) FROM requests WHERE status = 'pending'")
                pending_requests = cursor.fetchone()[0]
                
                # Общее количество запросов
                cursor.execute("SELECT COUNT(*) FROM requests")
                total_requests = cursor.fetchone()[0]
                
                return {
                    'users': users_count,
                    'devices': devices_count,
                    'permissions': permissions_count,
                    'pending_requests': pending_requests,
                    'total_requests': total_requests
                }
                
        except Exception as e:
            print(f"Ошибка получения статистики: {e}")
            return {}
    
    def cleanup_old_requests(self, days: int = 30) -> int:
        """Очистка старых обработанных запросов"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Удаляем обработанные запросы старше указанного количества дней
                cursor.execute("""
                DELETE FROM requests 
                WHERE status != 'pending' 
                AND datetime(created_at) < datetime('now', '-{} days')
                """.format(days))
                
                deleted_count = cursor.rowcount
                conn.commit()
                return deleted_count
                
        except Exception as e:
            print(f"Ошибка очистки старых запросов: {e}")
            return 0
    
    def backup_database(self, backup_path: str) -> bool:
        """Создание резервной копии базы данных"""
        try:
            # Создаем директорию для бэкапа если не существует
            backup_dir = os.path.dirname(backup_path)
            if backup_dir and not os.path.exists(backup_dir):
                os.makedirs(backup_dir)
            
            # Копируем базу данных
            with sqlite3.connect(self.db_path) as source:
                with sqlite3.connect(backup_path) as backup:
                    source.backup(backup)
            
            return True
            
        except Exception as e:
            print(f"Ошибка создания резервной копии: {e}")
            return False

# Глобальный экземпляр базы данных
db: Optional[Database] = None

def init_database(db_path: str) -> Database:
    """Инициализация глобального экземпляра базы данных"""
    global db
    db = Database(db_path)
    if not db.init_db():
        raise Exception("Не удалось инициализировать базу данных")
    return db

def get_database() -> Database:
    """Получение глобального экземпляра базы данных"""
    if db is None:
        raise Exception("База данных не инициализирована")
    return db
