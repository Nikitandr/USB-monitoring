"""
Менеджер шифрования для интеграции с базой данных

Обеспечивает удобный интерфейс для шифрования/дешифрования
с автоматическим Base64 кодированием для хранения в TEXT полях
"""

import base64
from typing import Optional
from .blowfish import BlowfishCipher
from .rc4 import RC4Cipher


class CryptoManager:
    """
    Менеджер шифрования данных
    
    Интегрирует Blowfish и RC4 шифры с базой данных.
    Автоматически кодирует зашифрованные данные в Base64 для хранения в TEXT полях.
    """
    
    def __init__(self, blowfish_key: bytes, rc4_key: bytes):
        """
        Инициализация менеджера шифрования
        
        Args:
            blowfish_key: Ключ для Blowfish (4-56 байт)
            rc4_key: Ключ для RC4 (5-256 байт)
        """
        self.blowfish = BlowfishCipher(blowfish_key)
        self.rc4 = RC4Cipher(rc4_key)
    
    def encrypt_username(self, username: str) -> str:
        """
        Шифрование username через Blowfish
        
        Args:
            username: Имя пользователя для шифрования
            
        Returns:
            Зашифрованный username в Base64
        """
        if not username:
            return username
        
        try:
            # Конвертируем строку в байты
            plaintext = username.encode('utf-8')
            
            # Шифруем через Blowfish
            ciphertext = self.blowfish.encrypt(plaintext)
            
            # Кодируем в Base64 для хранения в TEXT поле
            encoded = base64.b64encode(ciphertext).decode('ascii')
            
            return encoded
        except Exception as e:
            raise RuntimeError(f"Ошибка шифрования username: {e}")
    
    def decrypt_username(self, encrypted: str) -> str:
        """
        Дешифрование username из Blowfish
        
        Args:
            encrypted: Зашифрованный username в Base64
            
        Returns:
            Расшифрованное имя пользователя
        """
        if not encrypted:
            return encrypted
        
        try:
            # Декодируем из Base64
            ciphertext = base64.b64decode(encrypted.encode('ascii'))
            
            # Дешифруем через Blowfish
            plaintext = self.blowfish.decrypt(ciphertext)
            
            # Конвертируем байты в строку
            username = plaintext.decode('utf-8')
            
            return username
        except Exception as e:
            raise RuntimeError(f"Ошибка дешифрования username: {e}")
    
    def encrypt_serial(self, serial: str) -> str:
        """
        Шифрование serial через RC4
        
        Args:
            serial: Серийный номер устройства для шифрования
            
        Returns:
            Зашифрованный serial в Base64
        """
        if not serial:
            return serial
        
        try:
            # Конвертируем строку в байты
            plaintext = serial.encode('utf-8')
            
            # Шифруем через RC4
            ciphertext = self.rc4.encrypt(plaintext)
            
            # Кодируем в Base64 для хранения в TEXT поле
            encoded = base64.b64encode(ciphertext).decode('ascii')
            
            return encoded
        except Exception as e:
            raise RuntimeError(f"Ошибка шифрования serial: {e}")
    
    def decrypt_serial(self, encrypted: str) -> str:
        """
        Дешифрование serial из RC4
        
        Args:
            encrypted: Зашифрованный serial в Base64
            
        Returns:
            Расшифрованный серийный номер
        """
        if not encrypted:
            return encrypted
        
        try:
            # Декодируем из Base64
            ciphertext = base64.b64decode(encrypted.encode('ascii'))
            
            # Дешифруем через RC4
            plaintext = self.rc4.decrypt(ciphertext)
            
            # Конвертируем байты в строку
            serial = plaintext.decode('utf-8')
            
            return serial
        except Exception as e:
            raise RuntimeError(f"Ошибка дешифрования serial: {e}")
    
    def safe_decrypt_username(self, encrypted: str) -> Optional[str]:
        """
        Безопасное дешифрование username (не бросает исключения)
        
        Используется для обработки legacy данных, которые могут быть незашифрованными
        
        Args:
            encrypted: Потенциально зашифрованный username
            
        Returns:
            Расшифрованный username или исходное значение при ошибке
        """
        try:
            return self.decrypt_username(encrypted)
        except Exception:
            # Если не удалось расшифровать, возвращаем как есть
            # (возможно, это legacy незашифрованные данные)
            return encrypted
    
    def safe_decrypt_serial(self, encrypted: str) -> Optional[str]:
        """
        Безопасное дешифрование serial (не бросает исключения)
        
        Используется для обработки legacy данных, которые могут быть незашифрованными
        
        Args:
            encrypted: Потенциально зашифрованный serial
            
        Returns:
            Расшифрованный serial или исходное значение при ошибке
        """
        try:
            return self.decrypt_serial(encrypted)
        except Exception:
            # Если не удалось расшифровать, возвращаем как есть
            return encrypted
