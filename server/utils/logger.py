import logging
import os
from datetime import datetime
from typing import Optional

def setup_logger(name: str, log_file: Optional[str] = None, level: str = 'INFO') -> logging.Logger:
    """
    Настройка логгера для приложения
    
    Args:
        name: Имя логгера
        log_file: Путь к файлу логов (опционально)
        level: Уровень логирования
    
    Returns:
        Настроенный логгер
    """
    
    # Создаем логгер
    logger = logging.getLogger(name)
    
    # Устанавливаем уровень
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    
    # Очищаем существующие обработчики
    logger.handlers.clear()
    
    # Формат сообщений
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Консольный обработчик
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Файловый обработчик (если указан файл)
    if log_file:
        # Создаем директорию для логов если не существует
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

def get_app_logger() -> logging.Logger:
    """Получение основного логгера приложения"""
    return logging.getLogger('usb_monitor')

def log_request(username: str, action: str, device_info: str = "", status: str = ""):
    """
    Логирование запросов пользователей
    
    Args:
        username: Имя пользователя
        action: Действие (connect, request, approve, deny)
        device_info: Информация об устройстве
        status: Статус операции
    """
    logger = get_app_logger()
    
    message_parts = [f"User: {username}", f"Action: {action}"]
    
    if device_info:
        message_parts.append(f"Device: {device_info}")
    
    if status:
        message_parts.append(f"Status: {status}")
    
    message = " | ".join(message_parts)
    logger.info(message)

def log_admin_action(action: str, details: str = ""):
    """
    Логирование действий администратора
    
    Args:
        action: Действие администратора
        details: Дополнительные детали
    """
    logger = get_app_logger()
    
    message = f"Admin Action: {action}"
    if details:
        message += f" | Details: {details}"
    
    logger.info(message)

def log_system_event(event: str, details: str = ""):
    """
    Логирование системных событий
    
    Args:
        event: Тип события
        details: Дополнительные детали
    """
    logger = get_app_logger()
    
    message = f"System Event: {event}"
    if details:
        message += f" | Details: {details}"
    
    logger.info(message)

def log_error(error: Exception, context: str = ""):
    """
    Логирование ошибок
    
    Args:
        error: Исключение
        context: Контекст ошибки
    """
    logger = get_app_logger()
    
    message = f"Error: {str(error)}"
    if context:
        message = f"{context} | {message}"
    
    logger.error(message, exc_info=True)
