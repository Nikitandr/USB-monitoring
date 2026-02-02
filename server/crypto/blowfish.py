"""
Реализация алгоритма шифрования Blowfish

Blowfish - блочный шифр с размером блока 64 бита (8 байт)
Использует Feistel-сеть с 16 раундами
Ключ: от 32 до 448 бит (4-56 байт)
"""

import struct
from typing import List


class BlowfishCipher:
    """
    Реализация блочного шифра Blowfish
    
    Используется для шифрования поля username в базе данных
    """
    
    # Начальные значения P-массива (первые цифры числа π)
    P_ARRAY_INIT = [
        0x243F6A88, 0x85A308D3, 0x13198A2E, 0x03707344,
        0xA4093822, 0x299F31D0, 0x082EFA98, 0xEC4E6C89,
        0x452821E6, 0x38D01377, 0xBE5466CF, 0x34E90C6C,
        0xC0AC29B7, 0xC97C50DD, 0x3F84D5B5, 0xB5470917,
        0x9216D5D9, 0x8979FB1B
    ]
    
    # Начальные значения S-боксов (первые цифры числа e, √2, √3, etc.)
    # Упрощенная версия - используем меньше значений для демонстрации
    S_BOXES_INIT = [
        # S-box 0
        [
            0xD1310BA6, 0x98DFB5AC, 0x2FFD72DB, 0xD01ADFB7,
            0xB8E1AFED, 0x6A267E96, 0xBA7C9045, 0xF12C7F99,
            0x24A19947, 0xB3916CF7, 0x0801F2E2, 0x858EFC16,
            0x636920D8, 0x71574E69, 0xA458FEA3, 0xF4933D7E,
        ] * 16,  # 256 элементов
        # S-box 1
        [
            0x0D95748F, 0x728EB658, 0x718BCD58, 0x82154AEE,
            0x7B54A41D, 0xC25A59B5, 0x9C30D539, 0x2AF26013,
            0xC5D1B023, 0x286085F0, 0xCA417918, 0xB8DB38EF,
            0x8E79DCB0, 0x603A180E, 0x6C9E0E8B, 0xB01E8A3E,
        ] * 16,
        # S-box 2
        [
            0xD71577C1, 0xBD314B27, 0x78AF2FDA, 0x55605C60,
            0xE65525F3, 0xAA55AB94, 0x57489862, 0x63E81440,
            0x55CA396A, 0x2AAB10B6, 0xB4CC5C34, 0x1141E8CE,
            0xA15486AF, 0x7C72E993, 0xB3EE1411, 0x636FBC2A,
        ] * 16,
        # S-box 3
        [
            0x2BA9C55D, 0x741831F6, 0xCE5C3E16, 0x9B87931E,
            0xAFD6BA33, 0x6C24CF5C, 0x7A325381, 0x28958677,
            0x3B8F4898, 0x6B4BB9AF, 0xC4BFE81B, 0x66282193,
            0x61D809CC, 0xFB21A991, 0x487CAC60, 0x5DEC8032,
        ] * 16
    ]
    
    def __init__(self, key: bytes):
        """
        Инициализация Blowfish с заданным ключом
        
        Args:
            key: Ключ шифрования (4-56 байт)
        """
        if len(key) < 4 or len(key) > 56:
            raise ValueError("Ключ должен быть от 4 до 56 байт")
        
        self.key = key
        # Копируем начальные значения P-массива и S-боксов
        self.P = self.P_ARRAY_INIT.copy()
        self.S = [box.copy() for box in self.S_BOXES_INIT]
        
        # Инициализируем ключ
        self._expand_key()
    
    def _expand_key(self):
        """Расширение ключа - XOR P-массива с ключом и шифрование"""
        key_len = len(self.key)
        
        # XOR P-массива с ключом
        j = 0
        for i in range(18):
            data = 0
            for k in range(4):
                data = (data << 8) | self.key[j]
                j = (j + 1) % key_len
            self.P[i] ^= data
        
        # Шифруем нулевой блок для генерации новых значений P и S
        left = right = 0
        for i in range(0, 18, 2):
            left, right = self._encrypt_block(left, right)
            self.P[i] = left
            self.P[i + 1] = right
        
        for i in range(4):
            for j in range(0, 256, 2):
                left, right = self._encrypt_block(left, right)
                self.S[i][j] = left
                self.S[i][j + 1] = right
    
    def _f_function(self, x: int) -> int:
        """
        F-функция Blowfish (часть Feistel-сети)
        
        Args:
            x: 32-битное входное значение
            
        Returns:
            32-битный результат F-функции
        """
        # Разбиваем 32-битное значение на 4 байта
        a = (x >> 24) & 0xFF
        b = (x >> 16) & 0xFF
        c = (x >> 8) & 0xFF
        d = x & 0xFF
        
        # F(x) = ((S[0][a] + S[1][b]) XOR S[2][c]) + S[3][d]
        result = (self.S[0][a] + self.S[1][b]) & 0xFFFFFFFF
        result = result ^ self.S[2][c]
        result = (result + self.S[3][d]) & 0xFFFFFFFF
        
        return result
    
    def _encrypt_block(self, left: int, right: int) -> tuple:
        """
        Шифрование одного 64-битного блока
        
        Args:
            left: Левые 32 бита
            right: Правые 32 бита
            
        Returns:
            Кортеж (зашифрованные_левые_32_бита, зашифрованные_правые_32_бита)
        """
        # 16 раундов Feistel-сети
        for i in range(16):
            left = left ^ self.P[i]
            right = self._f_function(left) ^ right
            # Обмен left и right
            left, right = right, left
        
        # Отменяем последний обмен
        left, right = right, left
        
        # Финальная перестановка
        right = right ^ self.P[16]
        left = left ^ self.P[17]
        
        return left, right
    
    def _decrypt_block(self, left: int, right: int) -> tuple:
        """
        Дешифрование одного 64-битного блока
        
        Args:
            left: Левые 32 бита зашифрованного блока
            right: Правые 32 бита зашифрованного блока
            
        Returns:
            Кортеж (расшифрованные_левые_32_бита, расшифрованные_правые_32_бита)
        """
        # Дешифрование - то же самое, но P-массив в обратном порядке
        for i in range(17, 1, -1):
            left = left ^ self.P[i]
            right = self._f_function(left) ^ right
            left, right = right, left
        
        left, right = right, left
        
        right = right ^ self.P[1]
        left = left ^ self.P[0]
        
        return left, right
    
    def encrypt(self, plaintext: bytes) -> bytes:
        """
        Шифрование данных с padding
        
        Args:
            plaintext: Данные для шифрования
            
        Returns:
            Зашифрованные данные
        """
        # Добавляем PKCS#7 padding
        padded = self._pad_pkcs7(plaintext, 8)
        
        result = bytearray()
        
        # Шифруем блоки по 8 байт
        for i in range(0, len(padded), 8):
            block = padded[i:i+8]
            
            # Конвертируем 8 байт в два 32-битных числа
            left = struct.unpack('>I', block[0:4])[0]
            right = struct.unpack('>I', block[4:8])[0]
            
            # Шифруем блок
            left, right = self._encrypt_block(left, right)
            
            # Конвертируем обратно в байты
            result.extend(struct.pack('>I', left))
            result.extend(struct.pack('>I', right))
        
        return bytes(result)
    
    def decrypt(self, ciphertext: bytes) -> bytes:
        """
        Дешифрование данных с удалением padding
        
        Args:
            ciphertext: Зашифрованные данные
            
        Returns:
            Расшифрованные данные
        """
        if len(ciphertext) % 8 != 0:
            raise ValueError("Длина ciphertext должна быть кратна 8")
        
        result = bytearray()
        
        # Дешифруем блоки по 8 байт
        for i in range(0, len(ciphertext), 8):
            block = ciphertext[i:i+8]
            
            # Конвертируем 8 байт в два 32-битных числа
            left = struct.unpack('>I', block[0:4])[0]
            right = struct.unpack('>I', block[4:8])[0]
            
            # Дешифруем блок
            left, right = self._decrypt_block(left, right)
            
            # Конвертируем обратно в байты
            result.extend(struct.pack('>I', left))
            result.extend(struct.pack('>I', right))
        
        # Удаляем PKCS#7 padding
        return self._unpad_pkcs7(bytes(result))
    
    @staticmethod
    def _pad_pkcs7(data: bytes, block_size: int) -> bytes:
        """
        Добавление PKCS#7 padding
        
        Args:
            data: Данные для padding
            block_size: Размер блока
            
        Returns:
            Данные с padding
        """
        padding_len = block_size - (len(data) % block_size)
        padding = bytes([padding_len] * padding_len)
        return data + padding
    
    @staticmethod
    def _unpad_pkcs7(data: bytes) -> bytes:
        """
        Удаление PKCS#7 padding
        
        Args:
            data: Данные с padding
            
        Returns:
            Данные без padding
        """
        if len(data) == 0:
            raise ValueError("Данные не могут быть пустыми")
        
        padding_len = data[-1]
        
        if padding_len > len(data) or padding_len == 0:
            raise ValueError("Некорректный padding")
        
        # Проверяем корректность padding
        for i in range(1, padding_len + 1):
            if data[-i] != padding_len:
                raise ValueError("Некорректный PKCS#7 padding")
        
        return data[:-padding_len]
