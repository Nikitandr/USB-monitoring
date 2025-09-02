#!/usr/bin/env python3
"""
Скрипт для инициализации базы данных и создания тестовых данных
"""

import os
import sys
from datetime import datetime

# Добавляем путь к серверу в PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.database import init_database
from config import config

def create_test_data(db):
    """Создание тестовых данных"""
    print("Создание тестовых данных...")
    
    # Создаем тестовых пользователей
    test_users = ['user1', 'user2', 'testuser']
    for username in test_users:
        user = db.user.get_or_create(username)
        print(f"Создан пользователь: {user['username']} (ID: {user['id']})")
    
    # Создаем тестовые устройства
    test_devices = [
        {
            'vid': '0781',
            'pid': '5571', 
            'serial': '4C531001230318112343',
            'name': 'SanDisk Cruzer Blade',
            'description': 'USB Flash Drive 16GB'
        },
        {
            'vid': '8564',
            'pid': '1000',
            'serial': 'AA0123456789',
            'name': 'Transcend JetFlash',
            'description': 'USB Flash Drive 32GB'
        },
        {
            'vid': '0951',
            'pid': '1666',
            'serial': 'BB9876543210',
            'name': 'Kingston DataTraveler',
            'description': 'USB Flash Drive 64GB'
        }
    ]
    
    for device_data in test_devices:
        device = db.device.get_or_create(**device_data)
        print(f"Создано устройство: {device['name']} (ID: {device['id']})")
    
    # Создаем тестовые разрешения
    user1 = db.user.get_by_username('user1')
    user2 = db.user.get_by_username('user2')
    
    if user1 and user2:
        # user1 может использовать SanDisk и Transcend
        sandisk = db.device.get_by_identifiers('0781', '5571', '4C531001230318112343')
        transcend = db.device.get_by_identifiers('8564', '1000', 'AA0123456789')
        
        if sandisk:
            db.permission.set_permission(user1['id'], sandisk['id'], True)
            print(f"Разрешение создано: {user1['username']} -> {sandisk['name']}")
        
        if transcend:
            db.permission.set_permission(user1['id'], transcend['id'], True)
            print(f"Разрешение создано: {user1['username']} -> {transcend['name']}")
        
        # user2 может использовать только Kingston
        kingston = db.device.get_by_identifiers('0951', '1666', 'BB9876543210')
        if kingston:
            db.permission.set_permission(user2['id'], kingston['id'], True)
            print(f"Разрешение создано: {user2['username']} -> {kingston['name']}")

def main():
    """Основная функция"""
    print("Инициализация базы данных USB Monitor...")
    
    # Получаем конфигурацию
    env = os.environ.get('FLASK_ENV', 'development')
    app_config = config.get(env, config['default'])
    
    db_path = app_config.DATABASE_PATH
    print(f"Путь к базе данных: {db_path}")
    
    try:
        # Инициализируем базу данных
        db = init_database(db_path)
        print("База данных успешно инициализирована!")
        
        # Проверяем соединение
        if db.check_connection():
            print("Соединение с базой данных установлено!")
        else:
            print("Ошибка соединения с базой данных!")
            return False
        
        # Создаем тестовые данные
        create_test_data(db)
        
        # Выводим статистику
        stats = db.get_stats()
        print("\nСтатистика базы данных:")
        print(f"  Пользователи: {stats.get('users', 0)}")
        print(f"  Устройства: {stats.get('devices', 0)}")
        print(f"  Разрешения: {stats.get('permissions', 0)}")
        print(f"  Запросы: {stats.get('total_requests', 0)}")
        
        print("\nИнициализация завершена успешно!")
        return True
        
    except Exception as e:
        print(f"Ошибка инициализации: {e}")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
