"""
Конфигурация ключей шифрования

Управление ключами для Blowfish и RC4
"""

import os
import secrets


def get_encryption_keys() -> tuple[bytes, bytes]:
    """
    Получение ключей шифрования из переменных окружения
    
    Returns:
        Кортеж (blowfish_key, rc4_key)
    """
    # Получаем ключ Blowfish из переменной окружения
    blowfish_key_str = os.environ.get('BLOWFISH_KEY')
    
    if blowfish_key_str:
        blowfish_key = blowfish_key_str.encode('utf-8')
    else:
        # Генерируем ключ по умолчанию для разработки (НЕ для продакшн!)
        blowfish_key = b'DEFAULT_DEV_BLOWFISH_KEY_32BYTES'
        print("⚠️  WARNING: Используется ключ Blowfish по умолчанию!")
        print("   Установите переменную окружения BLOWFISH_KEY для продакшн")
    
    # Проверяем длину ключа Blowfish (4-56 байт)
    if len(blowfish_key) < 4 or len(blowfish_key) > 56:
        raise ValueError(f"Ключ Blowfish должен быть от 4 до 56 байт, получено: {len(blowfish_key)}")
    
    # Получаем ключ RC4 из переменной окружения
    rc4_key_str = os.environ.get('RC4_KEY')
    
    if rc4_key_str:
        rc4_key = rc4_key_str.encode('utf-8')
    else:
        # Генерируем ключ по умолчанию для разработки
        rc4_key = b'DEFAULT_DEV_RC4_KEY_16B'
        print("⚠️  WARNING: Используется ключ RC4 по умолчанию!")
        print("   Установите переменную окружения RC4_KEY для продакшн")
    
    # Проверяем длину ключа RC4 (5-256 байт)
    if len(rc4_key) < 5 or len(rc4_key) > 256:
        raise ValueError(f"Ключ RC4 должен быть от 5 до 256 байт, получено: {len(rc4_key)}")
    
    return blowfish_key, rc4_key


def generate_random_key(length: int) -> str:
    """
    Генерация криптографически стойкого случайного ключа
    
    Args:
        length: Длина ключа в байтах
        
    Returns:
        Ключ в виде hex-строки
    """
    return secrets.token_hex(length)


if __name__ == '__main__':
    # Утилита для генерации новых ключей
    print("=== Генератор Ключей Шифрования ===\n")
    
    print("Ключ Blowfish (32 байта - рекомендуется):")
    blowfish_key = generate_random_key(32)
    print(f"BLOWFISH_KEY={blowfish_key}\n")
    
    print("Ключ RC4 (16 байт - рекомендуется):")
    rc4_key = generate_random_key(16)
    print(f"RC4_KEY={rc4_key}\n")
    
    print("Добавьте эти ключи в ваш .env файл или docker-compose.yml")
