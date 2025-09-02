import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any

class BaseModel:
    """Базовый класс для всех моделей"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def get_connection(self):
        """Получение соединения с базой данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
        return conn
    
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """Выполнение SELECT запроса"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def execute_update(self, query: str, params: tuple = ()) -> int:
        """Выполнение INSERT/UPDATE/DELETE запроса"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            conn.commit()
            return cursor.lastrowid or cursor.rowcount

class User(BaseModel):
    """Модель пользователя"""
    
    def create(self, username: str) -> int:
        """Создание нового пользователя"""
        query = """
        INSERT INTO users (username, created_at)
        VALUES (?, ?)
        """
        return self.execute_update(query, (username, datetime.now().isoformat()))
    
    def get_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Получение пользователя по имени"""
        query = "SELECT * FROM users WHERE username = ?"
        result = self.execute_query(query, (username,))
        return result[0] if result else None
    
    def get_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Получение пользователя по ID"""
        query = "SELECT * FROM users WHERE id = ?"
        result = self.execute_query(query, (user_id,))
        return result[0] if result else None
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Получение всех пользователей"""
        query = "SELECT * FROM users ORDER BY username"
        return self.execute_query(query)
    
    def get_or_create(self, username: str) -> Dict[str, Any]:
        """Получение или создание пользователя"""
        user = self.get_by_username(username)
        if not user:
            user_id = self.create(username)
            user = self.get_by_id(user_id)
        return user
    
    def get_all_with_device_count(self) -> List[Dict[str, Any]]:
        """Получение всех пользователей с количеством устройств"""
        query = """
        SELECT u.*, 
               COUNT(p.id) as device_count
        FROM users u
        LEFT JOIN permissions p ON u.id = p.user_id AND p.granted = 1
        GROUP BY u.id, u.username, u.created_at
        ORDER BY u.username
        """
        return self.execute_query(query)

class Device(BaseModel):
    """Модель устройства"""
    
    def create(self, vid: str, pid: str, serial: str, name: str = "", description: str = "") -> int:
        """Создание нового устройства"""
        query = """
        INSERT INTO devices (vid, pid, serial, name, description, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        return self.execute_update(query, (vid, pid, serial, name, description, datetime.now().isoformat()))
    
    def get_by_identifiers(self, vid: str, pid: str, serial: str) -> Optional[Dict[str, Any]]:
        """Получение устройства по VID/PID/Serial"""
        query = "SELECT * FROM devices WHERE vid = ? AND pid = ? AND serial = ?"
        result = self.execute_query(query, (vid, pid, serial))
        return result[0] if result else None
    
    def get_by_id(self, device_id: int) -> Optional[Dict[str, Any]]:
        """Получение устройства по ID"""
        query = "SELECT * FROM devices WHERE id = ?"
        result = self.execute_query(query, (device_id,))
        return result[0] if result else None
    
    def get_all(self) -> List[Dict[str, Any]]:
        """Получение всех устройств"""
        query = "SELECT * FROM devices ORDER BY name, vid, pid"
        return self.execute_query(query)
    
    def get_or_create(self, vid: str, pid: str, serial: str, name: str = "", description: str = "") -> Dict[str, Any]:
        """Получение или создание устройства"""
        device = self.get_by_identifiers(vid, pid, serial)
        if not device:
            device_id = self.create(vid, pid, serial, name, description)
            device = self.get_by_id(device_id)
        return device
    
    def update(self, device_id: int, name: str = None, description: str = None) -> bool:
        """Обновление информации об устройстве"""
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name)
        
        if description is not None:
            updates.append("description = ?")
            params.append(description)
        
        if not updates:
            return False
        
        params.append(device_id)
        query = f"UPDATE devices SET {', '.join(updates)} WHERE id = ?"
        return self.execute_update(query, tuple(params)) > 0

class Permission(BaseModel):
    """Модель разрешений"""
    
    def create(self, user_id: int, device_id: int, granted: bool = True) -> int:
        """Создание нового разрешения"""
        query = """
        INSERT INTO permissions (user_id, device_id, granted, created_at)
        VALUES (?, ?, ?, ?)
        """
        return self.execute_update(query, (user_id, device_id, granted, datetime.now().isoformat()))
    
    def get_user_permissions(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение всех разрешений пользователя"""
        query = """
        SELECT p.*, d.vid, d.pid, d.serial, d.name, d.description
        FROM permissions p
        JOIN devices d ON p.device_id = d.id
        WHERE p.user_id = ?
        ORDER BY d.name, d.vid, d.pid
        """
        return self.execute_query(query, (user_id,))
    
    def check_permission(self, user_id: int, device_id: int) -> Optional[bool]:
        """Проверка разрешения пользователя на устройство"""
        query = "SELECT granted FROM permissions WHERE user_id = ? AND device_id = ?"
        result = self.execute_query(query, (user_id, device_id))
        return result[0]['granted'] if result else None
    
    def set_permission(self, user_id: int, device_id: int, granted: bool) -> bool:
        """Установка разрешения"""
        # Проверяем, существует ли уже разрешение
        existing = self.execute_query(
            "SELECT id FROM permissions WHERE user_id = ? AND device_id = ?",
            (user_id, device_id)
        )
        
        if existing:
            # Обновляем существующее
            query = "UPDATE permissions SET granted = ? WHERE user_id = ? AND device_id = ?"
            return self.execute_update(query, (granted, user_id, device_id)) > 0
        else:
            # Создаем новое
            return self.create(user_id, device_id, granted) > 0
    
    def remove_permission(self, user_id: int, device_id: int) -> bool:
        """Удаление разрешения"""
        query = "DELETE FROM permissions WHERE user_id = ? AND device_id = ?"
        return self.execute_update(query, (user_id, device_id)) > 0
    
    def get_user_devices(self, user_id: int) -> List[Dict[str, Any]]:
        """Получение всех устройств пользователя с разрешениями"""
        query = """
        SELECT d.*, p.granted, p.created_at as permission_created_at
        FROM devices d
        JOIN permissions p ON d.id = p.device_id
        WHERE p.user_id = ? AND p.granted = 1
        ORDER BY d.name, d.vid, d.pid
        """
        return self.execute_query(query, (user_id,))

class Request(BaseModel):
    """Модель запросов на разрешения"""
    
    STATUS_PENDING = 'pending'
    STATUS_APPROVED = 'approved'
    STATUS_DENIED = 'denied'
    
    def create(self, user_id: int, device_id: int, device_info: str = "") -> int:
        """Создание нового запроса"""
        query = """
        INSERT INTO requests (user_id, device_id, device_info, status, created_at)
        VALUES (?, ?, ?, ?, ?)
        """
        return self.execute_update(query, (user_id, device_id, device_info, self.STATUS_PENDING, datetime.now().isoformat()))
    
    def get_by_id(self, request_id: int) -> Optional[Dict[str, Any]]:
        """Получение запроса по ID"""
        query = """
        SELECT r.*, u.username, d.vid, d.pid, d.serial, d.name, d.description
        FROM requests r
        JOIN users u ON r.user_id = u.id
        JOIN devices d ON r.device_id = d.id
        WHERE r.id = ?
        """
        result = self.execute_query(query, (request_id,))
        return result[0] if result else None
    
    def get_pending(self) -> List[Dict[str, Any]]:
        """Получение всех ожидающих запросов"""
        query = """
        SELECT r.*, u.username, d.vid, d.pid, d.serial, d.name, d.description
        FROM requests r
        JOIN users u ON r.user_id = u.id
        JOIN devices d ON r.device_id = d.id
        WHERE r.status = ?
        ORDER BY r.created_at DESC
        """
        return self.execute_query(query, (self.STATUS_PENDING,))
    
    def get_all(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Получение всех запросов"""
        query = """
        SELECT r.*, u.username, d.vid, d.pid, d.serial, d.name, d.description
        FROM requests r
        JOIN users u ON r.user_id = u.id
        JOIN devices d ON r.device_id = d.id
        ORDER BY r.created_at DESC
        LIMIT ?
        """
        return self.execute_query(query, (limit,))
    
    def update_status(self, request_id: int, status: str) -> bool:
        """Обновление статуса запроса"""
        query = "UPDATE requests SET status = ?, processed_at = ? WHERE id = ?"
        return self.execute_update(query, (status, datetime.now().isoformat(), request_id)) > 0
    
    def approve(self, request_id: int) -> bool:
        """Одобрение запроса"""
        return self.update_status(request_id, self.STATUS_APPROVED)
    
    def deny(self, request_id: int) -> bool:
        """Отклонение запроса"""
        return self.update_status(request_id, self.STATUS_DENIED)
    
    def check_existing(self, user_id: int, device_id: int) -> Optional[Dict[str, Any]]:
        """Проверка существующего запроса"""
        query = """
        SELECT * FROM requests 
        WHERE user_id = ? AND device_id = ? AND status = ?
        ORDER BY created_at DESC
        LIMIT 1
        """
        result = self.execute_query(query, (user_id, device_id, self.STATUS_PENDING))
        return result[0] if result else None
    
    def get_filtered(self, status: str = None, username: str = None, 
                    date_from: str = None, date_to: str = None, limit: int = None) -> List[Dict[str, Any]]:
        """Получение отфильтрованных запросов"""
        query = """
        SELECT r.*, u.username, d.vid, d.pid, d.serial, d.name, d.description
        FROM requests r
        JOIN users u ON r.user_id = u.id
        JOIN devices d ON r.device_id = d.id
        WHERE 1=1
        """
        params = []
        
        if status:
            query += " AND r.status = ?"
            params.append(status)
        
        if username:
            query += " AND u.username LIKE ?"
            params.append(f"%{username}%")
        
        if date_from:
            query += " AND date(r.created_at) >= ?"
            params.append(date_from)
        
        if date_to:
            query += " AND date(r.created_at) <= ?"
            params.append(date_to)
        
        query += " ORDER BY r.created_at DESC"
        
        if limit:
            query += " LIMIT ?"
            params.append(limit)
        
        return self.execute_query(query, tuple(params))
