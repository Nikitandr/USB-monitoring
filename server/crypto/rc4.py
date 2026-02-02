"""
Реализация потокового шифра RC4

RC4 (Rivest Cipher 4) - потоковый шифр
Использует переменную длину ключа (40-2048 бит)
Простая и быстрая реализация
"""

from typing import Generator


class RC4Cipher:
    """
    Реализация потокового шифра RC4
    
    Используется для шифрования поля serial в базе данных
    """
    
    def __init__(self, key: bytes):
        """
        Инициализация RC4 с заданным ключом
        
        Args:
            key: Ключ шифрования (5-256 байт)
        """
        if len(key) < 5 or len(key) > 256:
            raise ValueError("Ключ должен быть от 5 до 256 байт")
        
        self.key = key
        self.S = list(range(256))  # Инициализируем S-массив
        
        # Выполняем KSA (Key Scheduling Algorithm)
        self._ksa()
    
    def _ksa(self) -> None:
        """
        KSA - Key Scheduling Algorithm
        
        Инициализация S-массива на основе ключа
        """
        j = 0
        key_len = len(self.key)
        
        for i in range(256):
            j = (j + self.S[i] + self.key[i % key_len]) % 256
            # Обмен S[i] и S[j]
            self.S[i], self.S[j] = self.S[j], self.S[i]
    
    def _prga(self) -> Generator[int, None, None]:
        """
        PRGA - Pseudo-Random Generation Algorithm
        
        Генератор ключевого потока
        
        Yields:
            Байты ключевого потока
        """
        i = 0
        j = 0
        S = self.S.copy()  # Копируем S, чтобы не изменять исходный
        
        while True:
            i = (i + 1) % 256
            j = (j + S[i]) % 256
            
            # Обмен S[i] и S[j]
            S[i], S[j] = S[j], S[i]
            
            # Генерируем байт ключевого потока
            K = S[(S[i] + S[j]) % 256]
            yield K
    
    def encrypt(self, plaintext: bytes) -> bytes:
        """
        Шифрование данных
        
        Args:
            plaintext: Данные для шифрования
            
        Returns:
            Зашифрованные данные
        """
        keystream = self._prga()
        result = bytearray()
        
        for byte in plaintext:
            # XOR с ключевым потоком
            result.append(byte ^ next(keystream))
        
        return bytes(result)
    
    def decrypt(self, ciphertext: bytes) -> bytes:
        """
        Дешифрование данных
        
        Для RC4 шифрование и дешифрование - одна и та же операция (XOR)
        
        Args:
            ciphertext: Зашифрованные данные
            
        Returns:
            Расшифрованные данные
        """
        # Для потокового шифра encrypt и decrypt идентичны
        return self.encrypt(ciphertext)
