import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Базовая конфигурация"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    DATABASE_PATH = os.environ.get('DATABASE_PATH') or 'usb_monitor.db'
    
    # Настройки администратора
    ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME') or 'admin'
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD') or 'admin123'
    
    # Настройки сервера (только HTTPS)
    HOST = os.environ.get('HOST') or '0.0.0.0'
    PORT = int(os.environ.get('PORT') or 443)  # HTTPS порт по умолчанию
    DEBUG = os.environ.get('FLASK_ENV') == 'development'
    
    # SSL настройки (обязательные)
    SSL_ENABLED = True  # Всегда включен для безопасности
    SSL_CERT_PATH = os.environ.get('SSL_CERT_PATH') or 'certs/server.crt'
    SSL_KEY_PATH = os.environ.get('SSL_KEY_PATH') or 'certs/server.key'
    SSL_PEM_PATH = os.environ.get('SSL_PEM_PATH') or 'certs/server.pem'
    
    # Настройки WebSocket
    SOCKETIO_ASYNC_MODE = 'threading'
    
    # Настройки логирования
    LOG_LEVEL = os.environ.get('LOG_LEVEL') or 'INFO'
    LOG_FILE = os.environ.get('LOG_FILE') or 'usb_monitor.log'
    
    # Настройки клиентов
    CLIENT_TIMEOUT = int(os.environ.get('CLIENT_TIMEOUT') or 30)  # секунды
    MAX_CLIENTS = int(os.environ.get('MAX_CLIENTS') or 100)

class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = True
    DATABASE_PATH = 'dev_usb_monitor.db'

class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    DEBUG = False

class TestingConfig(Config):
    """Конфигурация для тестирования"""
    TESTING = True
    DATABASE_PATH = ':memory:'  # SQLite в памяти для тестов

# Словарь конфигураций
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
