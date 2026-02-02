"""
Unit-тесты для модуля шифрования

Тестирование Blowfish, RC4 и CryptoManager
"""

import unittest
from .blowfish import BlowfishCipher
from .rc4 import RC4Cipher
from .manager import CryptoManager


class TestBlowfish(unittest.TestCase):
    """Тесты для Blowfish шифра"""
    
    def setUp(self):
        """Инициализация перед каждым тестом"""
        self.key = b'test_key_1234567890'
        self.cipher = BlowfishCipher(self.key)
    
    def test_encrypt_decrypt_short_text(self):
        """Тест шифрования/дешифрования короткого текста"""
        plaintext = b'Hello'
        ciphertext = self.cipher.encrypt(plaintext)
        decrypted = self.cipher.decrypt(ciphertext)
        self.assertEqual(plaintext, decrypted)
    
    def test_encrypt_decrypt_long_text(self):
        """Тест шифрования/дешифрования длинного текста"""
        plaintext = b'This is a much longer text that spans multiple blocks and should be encrypted correctly'
        ciphertext = self.cipher.encrypt(plaintext)
        decrypted = self.cipher.decrypt(ciphertext)
        self.assertEqual(plaintext, decrypted)
    
    def test_encrypt_decrypt_empty_string(self):
        """Тест шифрования пустой строки"""
        plaintext = b''
        ciphertext = self.cipher.encrypt(plaintext)
        decrypted = self.cipher.decrypt(ciphertext)
        self.assertEqual(plaintext, decrypted)
    
    def test_encrypt_decrypt_unicode(self):
        """Тест шифрования Unicode текста"""
        plaintext = 'Привет, мир! 🔒'.encode('utf-8')
        ciphertext = self.cipher.encrypt(plaintext)
        decrypted = self.cipher.decrypt(ciphertext)
        self.assertEqual(plaintext, decrypted)
    
    def test_deterministic_encryption(self):
        """Тест детерминированности шифрования"""
        plaintext = b'deterministic_test'
        ciphertext1 = self.cipher.encrypt(plaintext)
        ciphertext2 = self.cipher.encrypt(plaintext)
        self.assertEqual(ciphertext1, ciphertext2)
    
    def test_different_keys_different_output(self):
        """Тест что разные ключи дают разный результат"""
        plaintext = b'test_data'
        cipher1 = BlowfishCipher(b'key1_1234567890')
        cipher2 = BlowfishCipher(b'key2_1234567890')
        
        ciphertext1 = cipher1.encrypt(plaintext)
        ciphertext2 = cipher2.encrypt(plaintext)
        
        self.assertNotEqual(ciphertext1, ciphertext2)
    
    def test_padding_removal(self):
        """Тест корректного удаления padding"""
        # Тексты разной длины должны правильно обрабатываться
        for length in range(1, 20):
            plaintext = b'x' * length
            ciphertext = self.cipher.encrypt(plaintext)
            decrypted = self.cipher.decrypt(ciphertext)
            self.assertEqual(plaintext, decrypted)


class TestRC4(unittest.TestCase):
    """Тесты для RC4 шифра"""
    
    def setUp(self):
        """Инициализация перед каждым тестом"""
        self.key = b'test_rc4_key'
        self.cipher = RC4Cipher(self.key)
    
    def test_encrypt_decrypt_short_text(self):
        """Тест шифрования/дешифрования короткого текста"""
        plaintext = b'Hello'
        ciphertext = self.cipher.encrypt(plaintext)
        
        # Для дешифрования нужен новый экземпляр с тем же ключом
        cipher_decrypt = RC4Cipher(self.key)
        decrypted = cipher_decrypt.decrypt(ciphertext)
        
        self.assertEqual(plaintext, decrypted)
    
    def test_encrypt_decrypt_long_text(self):
        """Тест шифрования/дешифрования длинного текста"""
        plaintext = b'This is a very long text that should be encrypted using RC4 stream cipher properly'
        ciphertext = self.cipher.encrypt(plaintext)
        
        cipher_decrypt = RC4Cipher(self.key)
        decrypted = cipher_decrypt.decrypt(ciphertext)
        
        self.assertEqual(plaintext, decrypted)
    
    def test_encrypt_decrypt_empty_string(self):
        """Тест шифрования пустой строки"""
        plaintext = b''
        ciphertext = self.cipher.encrypt(plaintext)
        
        cipher_decrypt = RC4Cipher(self.key)
        decrypted = cipher_decrypt.decrypt(ciphertext)
        
        self.assertEqual(plaintext, decrypted)
    
    def test_encrypt_decrypt_unicode(self):
        """Тест шифрования Unicode текста"""
        plaintext = 'Тестовый текст 测试 🎉'.encode('utf-8')
        ciphertext = self.cipher.encrypt(plaintext)
        
        cipher_decrypt = RC4Cipher(self.key)
        decrypted = cipher_decrypt.decrypt(ciphertext)
        
        self.assertEqual(plaintext, decrypted)
    
    def test_deterministic_encryption(self):
        """Тест детерминированности шифрования"""
        plaintext = b'deterministic_test'
        
        cipher1 = RC4Cipher(self.key)
        ciphertext1 = cipher1.encrypt(plaintext)
        
        cipher2 = RC4Cipher(self.key)
        ciphertext2 = cipher2.encrypt(plaintext)
        
        self.assertEqual(ciphertext1, ciphertext2)
    
    def test_encrypt_is_decrypt(self):
        """Тест что encrypt и decrypt - одна и та же операция для RC4"""
        plaintext = b'test_data'
        cipher1 = RC4Cipher(self.key)
        ciphertext = cipher1.encrypt(plaintext)
        
        cipher2 = RC4Cipher(self.key)
        decrypted = cipher2.decrypt(ciphertext)
        
        self.assertEqual(plaintext, decrypted)
    
    def test_different_keys_different_output(self):
        """Тест что разные ключи дают разный результат"""
        plaintext = b'test_data'
        
        cipher1 = RC4Cipher(b'key1_12345')
        ciphertext1 = cipher1.encrypt(plaintext)
        
        cipher2 = RC4Cipher(b'key2_12345')
        ciphertext2 = cipher2.encrypt(plaintext)
        
        self.assertNotEqual(ciphertext1, ciphertext2)


class TestCryptoManager(unittest.TestCase):
    """Тесты для CryptoManager"""
    
    def setUp(self):
        """Инициализация перед каждым тестом"""
        blowfish_key = b'test_blowfish_key_123456'
        rc4_key = b'test_rc4_key_123'
        self.manager = CryptoManager(blowfish_key, rc4_key)
    
    def test_encrypt_decrypt_username(self):
        """Тест шифрования/дешифрования username"""
        username = 'john_doe'
        encrypted = self.manager.encrypt_username(username)
        decrypted = self.manager.decrypt_username(encrypted)
        self.assertEqual(username, decrypted)
    
    def test_encrypt_decrypt_username_unicode(self):
        """Тест шифрования/дешифрования username с Unicode"""
        username = 'пользователь_123'
        encrypted = self.manager.encrypt_username(username)
        decrypted = self.manager.decrypt_username(encrypted)
        self.assertEqual(username, decrypted)
    
    def test_encrypt_decrypt_serial(self):
        """Тест шифрования/дешифрования serial"""
        serial = '1234567890ABCDEF'
        encrypted = self.manager.encrypt_serial(serial)
        decrypted = self.manager.decrypt_serial(encrypted)
        self.assertEqual(serial, decrypted)
    
    def test_encrypt_decrypt_serial_empty(self):
        """Тест шифрования пустого serial"""
        serial = ''
        encrypted = self.manager.encrypt_serial(serial)
        decrypted = self.manager.decrypt_serial(encrypted)
        self.assertEqual(serial, decrypted)
    
    def test_encrypted_is_base64(self):
        """Тест что зашифрованные данные в Base64 формате"""
        username = 'test_user'
        encrypted = self.manager.encrypt_username(username)
        
        # Base64 должен содержать только ASCII символы
        self.assertTrue(encrypted.isascii())
        
        # Попробуем декодировать Base64
        import base64
        try:
            base64.b64decode(encrypted)
            is_valid_base64 = True
        except Exception:
            is_valid_base64 = False
        
        self.assertTrue(is_valid_base64)
    
    def test_username_deterministic(self):
        """Тест детерминированности шифрования username"""
        username = 'same_user'
        encrypted1 = self.manager.encrypt_username(username)
        encrypted2 = self.manager.encrypt_username(username)
        self.assertEqual(encrypted1, encrypted2)
    
    def test_serial_deterministic(self):
        """Тест детерминированности шифрования serial"""
        serial = 'SERIAL123'
        encrypted1 = self.manager.encrypt_serial(serial)
        encrypted2 = self.manager.encrypt_serial(serial)
        self.assertEqual(encrypted1, encrypted2)
    
    def test_safe_decrypt_username_valid(self):
        """Тест безопасного дешифрования валидных данных"""
        username = 'test_user'
        encrypted = self.manager.encrypt_username(username)
        decrypted = self.manager.safe_decrypt_username(encrypted)
        self.assertEqual(username, decrypted)
    
    def test_safe_decrypt_username_invalid(self):
        """Тест безопасного дешифрования некорректных данных"""
        invalid_data = 'this_is_not_encrypted'
        result = self.manager.safe_decrypt_username(invalid_data)
        # Должно вернуть исходное значение без ошибки
        self.assertEqual(invalid_data, result)
    
    def test_different_data_different_output(self):
        """Тест что разные данные дают разный вывод"""
        user1 = 'user1'
        user2 = 'user2'
        
        encrypted1 = self.manager.encrypt_username(user1)
        encrypted2 = self.manager.encrypt_username(user2)
        
        self.assertNotEqual(encrypted1, encrypted2)


def run_tests():
    """Запуск всех тестов"""
    # Создаем test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Добавляем тесты
    suite.addTests(loader.loadTestsFromTestCase(TestBlowfish))
    suite.addTests(loader.loadTestsFromTestCase(TestRC4))
    suite.addTests(loader.loadTestsFromTestCase(TestCryptoManager))
    
    # Запускаем тесты
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    # Возвращаем результат
    return result.wasSuccessful()


if __name__ == '__main__':
    print("=" * 70)
    print("Запуск Unit-тестов для модуля шифрования")
    print("=" * 70)
    print()
    
    success = run_tests()
    
    print()
    print("=" * 70)
    if success:
        print("✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    else:
        print("❌ НЕКОТОРЫЕ ТЕСТЫ НЕ ПРОШЛИ")
    print("=" * 70)
    
    exit(0 if success else 1)
