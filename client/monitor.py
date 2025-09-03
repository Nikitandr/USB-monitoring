#!/usr/bin/env python3
import pyudev
import yaml
import os
import sys
from pydbus import SystemBus
from gi.repository import GLib
import subprocess
import requests
import json
import time
import urllib3

# UDisks2 D-Bus константы
UDISKS_BUS_NAME     = 'org.freedesktop.UDisks2'
UDISKS_OBJ_MANAGER  = '/org/freedesktop/UDisks2'
BLOCK_IFACE         = 'org.freedesktop.UDisks2.Block'
FS_IFACE            = 'org.freedesktop.UDisks2.Filesystem'

# Путь к конфигу
CONFIG_PATH = '/etc/usb-monitor/config.yaml' if os.path.exists('/etc/usb-monitor/config.yaml') else os.path.join(os.path.dirname(__file__), 'config.yaml')

# Конфигурация сервера по умолчанию
DEFAULT_SERVER_CONFIG = {
    'server_url': 'https://localhost:443',
    'timeout': 10,
    'retry_attempts': 3,
    'retry_delay': 5,
    'cache_duration': 300,  # 5 минут
    'ssl_verify': False,    # Для самоподписанных сертификатов
    'ssl_warnings': False   # Отключаем SSL предупреждения
}

# Глобальные переменные для кэширования
_device_cache = {}
_cache_timestamps = {}
_pending_requests = {}

def check_root():
    if os.geteuid() != 0:
        print("Ошибка: этот скрипт нужно запускать от root (sudo).", file=sys.stderr)
        sys.exit(1)

def load_config():
    """Загружает конфигурацию клиента"""
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        cfg = {}
    
    # Объединяем с настройками по умолчанию
    server_config = DEFAULT_SERVER_CONFIG.copy()
    server_config.update(cfg.get('server', {}))
    
    return {
        'server': server_config
    }

def log_message(level, message):
    """Логирование сообщений для демона"""
    timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{timestamp}] {level}: {message}", file=sys.stderr if level == 'ERROR' else sys.stdout)

def check_device_permission_server(username, vid, pid, serial, server_config):
    """Проверяет разрешение устройства через сервер API"""
    device_key = f"{username}:{vid}:{pid}:{serial}"
    current_time = time.time()
    
    # Проверяем кэш
    if device_key in _device_cache:
        cache_time = _cache_timestamps.get(device_key, 0)
        if current_time - cache_time < server_config['cache_duration']:
            log_message('DEBUG', f"Используем кэшированный результат для {device_key}")
            return _device_cache[device_key]
    
    # Настройка SSL предупреждений
    if not server_config.get('ssl_warnings', True):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Делаем запрос к серверу
    url = f"{server_config['server_url']}/api/devices/check"
    data = {
        'username': username,
        'vid': vid,
        'pid': pid,
        'serial': serial
    }
    
    # Настройки SSL для requests
    ssl_verify = server_config.get('ssl_verify', True)
    
    for attempt in range(server_config['retry_attempts']):
        try:
            log_message('DEBUG', f"Запрос к серверу (попытка {attempt + 1}): {url}")
            response = requests.post(
                url, 
                json=data, 
                timeout=server_config['timeout'],
                verify=ssl_verify
            )
            
            if response.status_code == 200:
                result = response.json()
                status = result.get('status', 'unknown')
                
                # Кэшируем результат только для allowed/denied, но не для unknown
                if status in ['allowed', 'denied']:
                    _device_cache[device_key] = status
                    _cache_timestamps[device_key] = current_time
                    # Очищаем ожидающий запрос, если устройство получило окончательный статус
                    if device_key in _pending_requests:
                        del _pending_requests[device_key]
                
                log_message('INFO', f"Сервер ответил: {status} для {device_key}")
                return status
            else:
                log_message('ERROR', f"Сервер вернул код {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            log_message('ERROR', f"Ошибка соединения с сервером (попытка {attempt + 1}): {e}")
            
        if attempt < server_config['retry_attempts'] - 1:
            time.sleep(server_config['retry_delay'])
    
    log_message('ERROR', f"Не удалось связаться с сервером после {server_config['retry_attempts']} попыток")
    return None

def create_device_request(username, vid, pid, serial, device_info, server_config):
    """Создает запрос на разрешение устройства"""
    device_key = f"{username}:{vid}:{pid}:{serial}"
    
    # Проверяем, нет ли уже ожидающего запроса
    if device_key in _pending_requests:
        log_message('INFO', f"Запрос для {device_key} уже отправлен, ожидаем ответа")
        return _pending_requests[device_key]
    
    # Настройка SSL предупреждений
    if not server_config.get('ssl_warnings', True):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    url = f"{server_config['server_url']}/api/requests"
    data = {
        'username': username,
        'vid': vid,
        'pid': pid,
        'serial': serial,
        'device_info': device_info
    }
    
    # Настройки SSL для requests
    ssl_verify = server_config.get('ssl_verify', True)
    
    try:
        log_message('INFO', f"Отправляем запрос администратору для {device_key}")
        response = requests.post(
            url, 
            json=data, 
            timeout=server_config['timeout'],
            verify=ssl_verify
        )
        
        if response.status_code == 200:
            result = response.json()
            request_id = result.get('request_id')
            
            # Сохраняем ID запроса
            _pending_requests[device_key] = request_id
            
            log_message('INFO', f"Запрос создан с ID {request_id}")
            return request_id
        else:
            log_message('ERROR', f"Ошибка создания запроса: {response.status_code}")
            
    except requests.exceptions.RequestException as e:
        log_message('ERROR', f"Ошибка отправки запроса: {e}")
    
    return None

def check_device_policy(username, vid, pid, serial, device_info, cfg):
    """Основная функция проверки политики устройства"""
    server_config = cfg['server']
    
    # Пытаемся проверить через сервер
    server_result = check_device_permission_server(username, vid, pid, serial, server_config)
    
    if server_result is not None:
        if server_result == 'unknown':
            # Создаем запрос администратору
            create_device_request(username, vid, pid, serial, device_info, server_config)
            return 'unknown'
        return server_result
    
    # Если сервер недоступен - всегда блокируем устройства
    # Это обеспечивает безопасность: без связи с сервером никакие устройства не разрешаются
    log_message('WARNING', "Сервер недоступен - блокируем все USB устройства для безопасности")
    return 'deny'

def find_fs_object_path(bus, device_node):
    om = bus.get(UDISKS_BUS_NAME, UDISKS_OBJ_MANAGER)
    objects = om.GetManagedObjects()
    for obj_path, ifaces in objects.items():
        block = ifaces.get(BLOCK_IFACE)
        fs    = ifaces.get(FS_IFACE)
        if not block or not fs:
            continue
        # block.device — байтовый массив с '\x00' на конце
        dev = bytes(block.get('Device')).rstrip(b'\x00').decode()
        if dev == device_node:
            return obj_path
    return None

def get_active_user():
    """
    Определяет активного пользователя с использованием нескольких методов fallback.
    Возвращает имя пользователя или None, если не удалось определить.
    """
    # Метод 1: loginctl (основной)
    user = _get_user_via_loginctl()
    if user:
        return user
    
    # Метод 2: who команда
    user = _get_user_via_who()
    if user:
        return user
    
    # Метод 3: анализ X11 сессий
    user = _get_user_via_x11()
    if user:
        return user
    
    # Метод 4: проверка /proc/*/environ для графических процессов
    user = _get_user_via_proc()
    if user:
        return user
    
    return None

def _get_user_via_loginctl():
    """Определение пользователя через loginctl"""
    try:
        out = subprocess.check_output(
            ["loginctl", "list-sessions", "--no-legend"],
            stderr=subprocess.DEVNULL
        ).decode('utf-8')
    except subprocess.CalledProcessError:
        return None

    for line in out.splitlines():
        parts = line.split()
        if not parts:
            continue
        session_id = parts[0]

        try:
            info = subprocess.check_output(
                ["loginctl", "show-session", session_id, "-p", "Name", "-p", "State", "-p", "Seat", "-p", "Type"],
                stderr=subprocess.DEVNULL
            ).decode('utf-8')
        except subprocess.CalledProcessError:
            continue

        user = None
        state = None
        seat = None
        session_type = None

        for kv in info.splitlines():
            if kv.startswith("Name="):
                user = kv.split("=", 1)[1].strip()
            elif kv.startswith("State="):
                state = kv.split("=", 1)[1].strip()
            elif kv.startswith("Seat="):
                seat = kv.split("=", 1)[1].strip()
            elif kv.startswith("Type="):
                session_type = kv.split("=", 1)[1].strip()

        # Приоритет: активная графическая сессия на seat0
        if (seat == "seat0" and state == "active" and 
            session_type in ["x11", "wayland", "tty"] and user):
            return user

    return None

def _get_user_via_who():
    """Определение пользователя через команду who"""
    try:
        out = subprocess.check_output(["who"], stderr=subprocess.DEVNULL).decode('utf-8')
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                user = parts[0]
                terminal = parts[1]
                # Ищем пользователей на графических терминалах
                if terminal.startswith((':0', 'tty7', 'tty1')) and user != 'root':
                    return user
    except subprocess.CalledProcessError:
        pass
    return None

def _get_user_via_x11():
    """Определение пользователя через анализ X11 процессов"""
    try:
        # Ищем процессы X сервера
        out = subprocess.check_output(
            ["ps", "aux"], stderr=subprocess.DEVNULL
        ).decode('utf-8')
        
        for line in out.splitlines():
            if '/usr/bin/X' in line or 'Xorg' in line:
                parts = line.split()
                if len(parts) > 0:
                    user = parts[0]
                    if user != 'root':
                        return user
    except subprocess.CalledProcessError:
        pass
    return None

def _get_user_via_proc():
    """Определение пользователя через анализ /proc для графических процессов"""
    try:
        # Ищем процессы с DISPLAY переменной
        for proc_dir in os.listdir('/proc'):
            if not proc_dir.isdigit():
                continue
            
            try:
                environ_path = f'/proc/{proc_dir}/environ'
                if os.path.exists(environ_path):
                    with open(environ_path, 'rb') as f:
                        environ_data = f.read().decode('utf-8', errors='ignore')
                        
                    if 'DISPLAY=' in environ_data:
                        # Получаем владельца процесса
                        stat_path = f'/proc/{proc_dir}/stat'
                        if os.path.exists(stat_path):
                            stat_info = os.stat(stat_path)
                            uid = stat_info.st_uid
                            
                            # Конвертируем UID в имя пользователя
                            import pwd
                            try:
                                user_info = pwd.getpwuid(uid)
                                user = user_info.pw_name
                                if user != 'root':
                                    return user
                            except KeyError:
                                continue
            except (OSError, IOError, PermissionError):
                continue
    except OSError:
        pass
    return None

def wait_for_device_ready(device_node, timeout=10):
    """Ожидает готовности устройства к монтированию"""
    log_message('DEBUG', f"Ожидаем готовности устройства {device_node}")
    
    for attempt in range(timeout):
        try:
            # Проверяем, что устройство существует и доступно для чтения
            if os.path.exists(device_node) and os.access(device_node, os.R_OK):
                # Пытаемся прочитать первые байты устройства
                with open(device_node, 'rb') as f:
                    f.read(512)  # Читаем первый сектор
                log_message('DEBUG', f"Устройство {device_node} готово к монтированию")
                return True
        except (OSError, IOError) as e:
            log_message('DEBUG', f"Устройство {device_node} не готово (попытка {attempt + 1}): {e}")
        
        time.sleep(1)
    
    log_message('WARNING', f"Устройство {device_node} не готово после {timeout} секунд ожидания")
    return False

def unmount_device(device_node):
    """Размонтирует USB устройство и очищает точку монтирования"""
    log_message('INFO', f"Размонтирование устройства {device_node}")
    
    try:
        # Находим все точки монтирования для данного устройства
        mount_check = subprocess.run(['/bin/mount'], capture_output=True, text=True)
        mount_points = []
        
        for line in mount_check.stdout.splitlines():
            if device_node in line:
                # Парсим строку монтирования: /dev/sdb on /media/user/1812-D65 type vfat (...)
                parts = line.split(' on ')
                if len(parts) >= 2:
                    mount_point = parts[1].split(' type ')[0]
                    mount_points.append(mount_point)
                    log_message('DEBUG', f"Найдена точка монтирования: {mount_point}")
        
        # Размонтируем каждую найденную точку
        for mount_point in mount_points:
            try:
                # Используем nsenter для размонтирования в основном namespace
                umount_cmd = ['/usr/bin/nsenter', '-t', '1', '-m', '/bin/umount', mount_point]
                
                log_message('DEBUG', f"Выполняем размонтирование: {' '.join(umount_cmd)}")
                result = subprocess.run(umount_cmd, capture_output=True, text=True, check=False)
                
                if result.returncode == 0:
                    log_message('INFO', f"Устройство {device_node} размонтировано из {mount_point}")
                    
                    # Удаляем пустую точку монтирования
                    try:
                        if os.path.exists(mount_point) and os.path.isdir(mount_point):
                            # Проверяем, что папка пустая
                            if not os.listdir(mount_point):
                                os.rmdir(mount_point)
                                log_message('DEBUG', f"Удалена точка монтирования: {mount_point}")
                            else:
                                log_message('WARNING', f"Точка монтирования не пустая: {mount_point}")
                    except Exception as e:
                        log_message('WARNING', f"Не удалось удалить точку монтирования {mount_point}: {e}")
                        
                else:
                    log_message('ERROR', f"Ошибка размонтирования {mount_point}: {result.stderr.strip()}")
                    
            except Exception as e:
                log_message('ERROR', f"Неожиданная ошибка при размонтировании {mount_point}: {e}")
                
    except Exception as e:
        log_message('ERROR', f"Ошибка при поиске точек монтирования для {device_node}: {e}")

def cleanup_stale_mount_points():
    """Очищает старые неиспользуемые точки монтирования при запуске"""
    log_message('INFO', "Очистка старых точек монтирования")
    
    try:
        # Получаем список всех смонтированных устройств
        mount_check = subprocess.run(['/bin/mount'], capture_output=True, text=True)
        mounted_points = set()
        
        for line in mount_check.stdout.splitlines():
            if '/media/' in line:
                parts = line.split(' on ')
                if len(parts) >= 2:
                    mount_point = parts[1].split(' type ')[0]
                    mounted_points.add(mount_point)
        
        # Проверяем папки в /media/
        if os.path.exists('/media'):
            for user_dir in os.listdir('/media'):
                user_media_path = os.path.join('/media', user_dir)
                if os.path.isdir(user_media_path):
                    for mount_dir in os.listdir(user_media_path):
                        mount_path = os.path.join(user_media_path, mount_dir)
                        if os.path.isdir(mount_path) and mount_path not in mounted_points:
                            try:
                                # Проверяем, что папка пустая
                                if not os.listdir(mount_path):
                                    os.rmdir(mount_path)
                                    log_message('DEBUG', f"Удалена неиспользуемая точка монтирования: {mount_path}")
                                else:
                                    log_message('DEBUG', f"Точка монтирования не пустая, оставляем: {mount_path}")
                            except Exception as e:
                                log_message('WARNING', f"Не удалось удалить {mount_path}: {e}")
                                
    except Exception as e:
        log_message('ERROR', f"Ошибка при очистке точек монтирования: {e}")

def get_device_info_for_notification(device):
    """Получает информацию об устройстве для уведомлений"""
    return {
        'vendor': device.get('ID_VENDOR', 'Unknown'),
        'model': device.get('ID_MODEL', 'Unknown'),
        'fs_type': device.get('ID_FS_TYPE', 'Unknown'),
        'fs_label': device.get('ID_FS_LABEL', ''),
        'device_node': device.device_node
    }

def mount_device(device_node):
    # Ждем готовности устройства
    if not wait_for_device_ready(device_node):
        log_message('ERROR', f"Устройство {device_node} не готово к монтированию")
        return

    # Получаем имя активного пользователя
    user = get_active_user()
    if not user:
        log_message('WARNING', "Не удалось определить активного пользователя; монтируем под /media/root")
        mount_base = "/media/root"
        target_user = "root"
        uid = 0
        gid = 0
    else:
        mount_base = f"/media/{user}"
        target_user = user
        try:
            import pwd
            user_info = pwd.getpwnam(target_user)
            uid = user_info.pw_uid
            gid = user_info.pw_gid
        except KeyError:
            log_message('ERROR', f"Пользователь {target_user} не найден")
            uid = 0
            gid = 0

    # Убедимся, что базовая папка существует
    if not os.path.isdir(mount_base):
        try:
            os.makedirs(mount_base, exist_ok=True)
            # Устанавливаем владельца каталога на нужного пользователя
            if target_user != "root":
                subprocess.run(["/bin/chown", f"{target_user}:{target_user}", mount_base], check=False)
        except Exception as e:
            log_message('ERROR', f"Не удалось создать или назначить {mount_base}: {e}")

    # Получаем информацию об устройстве для создания уникального имени папки
    try:
        # Используем blkid для получения информации о файловой системе
        blkid_output = subprocess.check_output(['/sbin/blkid', device_node], stderr=subprocess.DEVNULL).decode('utf-8')
        
        fs_label = ''
        fs_uuid = ''
        
        # Парсим вывод blkid
        for part in blkid_output.split():
            if part.startswith('LABEL='):
                fs_label = part.split('=', 1)[1].strip('"')
            elif part.startswith('UUID='):
                fs_uuid = part.split('=', 1)[1].strip('"')
        
        # Создаем имя папки монтирования
        if fs_label:
            mount_name = fs_label
        elif fs_uuid:
            mount_name = fs_uuid[:8]  # Первые 8 символов UUID
        else:
            mount_name = os.path.basename(device_node)
            
    except subprocess.CalledProcessError:
        # Если blkid не сработал, используем имя устройства
        mount_name = os.path.basename(device_node)
        log_message('WARNING', f"Не удалось получить информацию о файловой системе для {device_node}")
    
    mount_point = os.path.join(mount_base, mount_name)
    
    # Создаем точку монтирования
    try:
        if not os.path.exists(mount_point):
            os.makedirs(mount_point, exist_ok=True)
            if target_user != "root":
                subprocess.run(["/bin/chown", f"{target_user}:{target_user}", mount_point], check=False)
    except Exception as e:
        log_message('ERROR', f"Ошибка создания точки монтирования {mount_point}: {e}")
        return

    # Проверяем, не смонтировано ли уже устройство
    try:
        mount_check = subprocess.run(['/bin/mount'], capture_output=True, text=True)
        if device_node in mount_check.stdout:
            log_message('INFO', f"Устройство {device_node} уже смонтировано")
            return
    except subprocess.CalledProcessError:
        pass

    # Монтируем устройство напрямую через mount команду
    # Это обходит polkit ограничения, так как выполняется от root
    try:
        if target_user != "root":
            # Опции для пользовательского монтирования
            mount_options = f'rw,nosuid,nodev,uid={uid},gid={gid},umask=0022'
        else:
            # Опции для root монтирования
            mount_options = 'rw,nosuid,nodev'
        
        # Используем nsenter для монтирования в основном namespace (PID 1)
        # Это обходит изоляцию mount namespace в systemd
        mount_cmd = ['/usr/bin/nsenter', '-t', '1', '-m', '/bin/mount', '-o', mount_options, device_node, mount_point]
        
        # Детальное логирование перед выполнением
        log_message('DEBUG', f"Выполняем команду монтирования через nsenter: {' '.join(mount_cmd)}")
        log_message('DEBUG', f"Рабочая директория: {os.getcwd()}")
        log_message('DEBUG', f"Устройство существует: {os.path.exists(device_node)}")
        log_message('DEBUG', f"Точка монтирования существует: {os.path.exists(mount_point)}")
        log_message('DEBUG', f"Права на точку монтирования: {oct(os.stat(mount_point).st_mode)[-3:] if os.path.exists(mount_point) else 'N/A'}")
        
        # Настраиваем окружение с полным PATH
        env = os.environ.copy()
        env['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
        
        # Выполняем монтирование с захватом stderr
        result = subprocess.run(
            mount_cmd,
            capture_output=True,
            text=True,
            check=False,
            env=env
        )
        
        # Логируем результат выполнения
        log_message('DEBUG', f"Код возврата mount: {result.returncode}")
        if result.stdout:
            log_message('DEBUG', f"STDOUT mount: {result.stdout.strip()}")
        if result.stderr:
            log_message('DEBUG', f"STDERR mount: {result.stderr.strip()}")
        
        # Проверяем успешность монтирования
        if result.returncode == 0:
            # Ждем немного и проверяем, действительно ли устройство смонтировано
            time.sleep(2)
            mount_check = subprocess.run(['/bin/mount'], capture_output=True, text=True)
            
            # Проверяем несколькими способами
            device_mounted = False
            mount_point_used = False
            
            for line in mount_check.stdout.splitlines():
                if device_node in line:
                    device_mounted = True
                    log_message('DEBUG', f"Найдена строка монтирования: {line.strip()}")
                if mount_point in line:
                    mount_point_used = True
            
            # Дополнительная проверка через /proc/mounts
            try:
                with open('/proc/mounts', 'r') as f:
                    proc_mounts = f.read()
                    if device_node in proc_mounts:
                        device_mounted = True
                        log_message('DEBUG', f"Устройство найдено в /proc/mounts")
            except Exception as e:
                log_message('DEBUG', f"Не удалось прочитать /proc/mounts: {e}")
            
            # Проверяем, есть ли файлы в точке монтирования
            try:
                if os.path.exists(mount_point):
                    files_in_mount = os.listdir(mount_point)
                    if files_in_mount:
                        log_message('DEBUG', f"В точке монтирования найдены файлы: {files_in_mount[:5]}")  # Первые 5 файлов
                        device_mounted = True
            except Exception as e:
                log_message('DEBUG', f"Не удалось проверить содержимое точки монтирования: {e}")
            
            if device_mounted or mount_point_used:
                log_message('INFO', f"Устройство {device_node} успешно смонтировано в: {mount_point}")
                
                # Дополнительно устанавливаем права на точку монтирования
                if target_user != "root":
                    subprocess.run(["/bin/chown", f"{target_user}:{target_user}", mount_point], check=False)
                    subprocess.run(["/bin/chmod", "755", mount_point], check=False)
            else:
                log_message('ERROR', f"Команда mount завершилась успешно, но устройство не найдено в списке смонтированных")
                log_message('DEBUG', f"Полный вывод mount: {mount_check.stdout}")
                
                # Пытаемся выяснить причину
                log_message('DEBUG', "Дополнительная диагностика:")
                
                # Проверяем dmesg на ошибки
                try:
                    dmesg_result = subprocess.run(['/bin/dmesg', '-T'], capture_output=True, text=True, timeout=5)
                    recent_lines = dmesg_result.stdout.splitlines()[-20:]  # Последние 20 строк
                    for line in recent_lines:
                        if any(keyword in line.lower() for keyword in ['error', 'fail', 'mount', device_node.split('/')[-1]]):
                            log_message('DEBUG', f"dmesg: {line.strip()}")
                except Exception as e:
                    log_message('DEBUG', f"Не удалось получить dmesg: {e}")
        else:
            log_message('ERROR', f"Ошибка монтирования {device_node}: код возврата {result.returncode}")
            if result.stderr:
                log_message('ERROR', f"Детали ошибки: {result.stderr.strip()}")
            
            # Удаляем созданную точку монтирования при ошибке
            try:
                if os.path.exists(mount_point) and os.path.isdir(mount_point):
                    os.rmdir(mount_point)
                    log_message('DEBUG', f"Удалена неиспользуемая точка монтирования: {mount_point}")
            except Exception as cleanup_error:
                log_message('WARNING', f"Не удалось удалить точку монтирования: {cleanup_error}")
            
    except Exception as e:
        log_message('ERROR', f"Неожиданная ошибка при монтировании: {e}")

def send_desktop_notification(username, title, message):
    """Отправляет уведомление пользователю"""
    try:
        # Получаем DISPLAY и другие переменные окружения для пользователя
        display = None
        xdg_runtime_dir = None
        
        for proc_dir in os.listdir('/proc'):
            if not proc_dir.isdigit():
                continue
            try:
                environ_path = f'/proc/{proc_dir}/environ'
                if os.path.exists(environ_path):
                    with open(environ_path, 'rb') as f:
                        environ_data = f.read().decode('utf-8', errors='ignore')
                    
                    if f'USER={username}' in environ_data and 'DISPLAY=' in environ_data:
                        for line in environ_data.split('\0'):
                            if line.startswith('DISPLAY='):
                                display = line.split('=', 1)[1]
                            elif line.startswith('XDG_RUNTIME_DIR='):
                                xdg_runtime_dir = line.split('=', 1)[1]
                        if display:
                            break
            except (OSError, IOError, PermissionError):
                continue
        
        if display:
            # Получаем UID пользователя
            try:
                import pwd
                user_info = pwd.getpwnam(username)
                uid = user_info.pw_uid
                
                # Настраиваем окружение для уведомления
                env = {
                    'DISPLAY': display,
                    'USER': username,
                    'HOME': user_info.pw_dir,
                }
                
                if xdg_runtime_dir:
                    env['XDG_RUNTIME_DIR'] = xdg_runtime_dir
                else:
                    env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
                
                # Отправляем уведомление используя su
                subprocess.run([
                    'su', '-', username, '-c', 
                    f'DISPLAY={display} notify-send --urgency=normal --expire-time=5000 "{title}" "{message}"'
                ], env=env, check=False, timeout=10)
                
                log_message('DEBUG', f"Уведомление отправлено пользователю {username}")
                
            except (KeyError, subprocess.TimeoutExpired) as e:
                log_message('WARNING', f"Не удалось отправить уведомление: {e}")
        else:
            log_message('WARNING', f"Не удалось найти DISPLAY для пользователя {username}")
            
    except Exception as e:
        log_message('ERROR', f"Ошибка отправки уведомления: {e}")

def main():
    check_root()
    
    log_message('INFO', "Запуск USB Monitor Client")

    # Очищаем старые точки монтирования при запуске
    cleanup_stale_mount_points()

    # udev-мониторинг блочных устройств
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem='block')

    log_message('INFO', "Мониторинг USB-событий запущен")
    cfg = load_config()
    
    log_message('INFO', f"Сервер: {cfg['server']['server_url']}")
    log_message('INFO', f"Таймаут: {cfg['server']['timeout']}с, попыток: {cfg['server']['retry_attempts']}")

    for action, device in monitor:
        # Обрабатываем события подключения и отключения
        if action not in ('add', 'remove'):
            continue

        # Фильтруем только USB-блочные устройства
        if device.get('ID_BUS') != 'usb':
            continue

        # Для события remove не требуется файловая система
        if action == 'add' and not device.get('ID_FS_TYPE'):
            continue

        # Обрабатываем и диски, и разделы
        if device.get('DEVTYPE') not in ('disk', 'partition'):
            continue

        device_node = device.device_node
        device_info = get_device_info_for_notification(device)
        device_info_str = f"{device_info['vendor']} {device_info['model']} ({device_info.get('fs_type', 'Unknown')})"

        if action == 'remove':
            # Обработка отключения USB устройства
            log_message('INFO', f"USB устройство отключено: {device_node}")
            log_message('DEBUG', f"Информация об устройстве: {device_info_str}")
            
            # Размонтируем устройство
            unmount_device(device_node)
            
            # Уведомляем всех активных пользователей об отключении
            try:
                # Получаем список всех активных пользователей
                active_users = set()
                loginctl_result = subprocess.run(['loginctl', 'list-sessions', '--no-legend'], 
                                               capture_output=True, text=True, check=False)
                if loginctl_result.returncode == 0:
                    for line in loginctl_result.stdout.splitlines():
                        parts = line.split()
                        if len(parts) >= 3:
                            session_id = parts[0]
                            user = parts[2]
                            if user != 'root':
                                active_users.add(user)
                
                # Отправляем уведомления всем активным пользователям
                for username in active_users:
                    send_desktop_notification(
                        username,
                        "USB устройство отключено",
                        f"Устройство {device_info_str} было отключено"
                    )
            except Exception as e:
                log_message('WARNING', f"Не удалось отправить уведомления об отключении: {e}")
            
            continue

        # Обработка подключения USB устройства (action == 'add')
        # Получаем активного пользователя
        username = get_active_user()
        if not username:
            log_message('WARNING', "Не удалось определить активного пользователя, пропускаем устройство")
            continue

        vid = device.get('ID_VENDOR_ID', 'unknown')
        pid = device.get('ID_MODEL_ID', 'unknown')
        serial = device.get('ID_SERIAL_SHORT', '')
        
        log_info = f"VID:PID={vid}:{pid}, Serial={serial or 'n/a'}, User={username}"
        
        log_message('INFO', f"USB устройство подключено: {log_info}")
        log_message('DEBUG', f"Информация об устройстве: {device_info_str}")

        # Проверяем политику через сервер
        policy = check_device_policy(username, vid, pid, serial, device_info_str, cfg)

        if policy == 'allowed':
            log_message('INFO', f"Устройство разрешено: {log_info}")
            send_desktop_notification(
                username, 
                "USB устройство подключено", 
                f"Устройство {device_info_str} успешно подключено"
            )
            mount_device(device.device_node)
            
        elif policy == 'denied':
            log_message('WARNING', f"Устройство запрещено: {log_info}")
            send_desktop_notification(
                username, 
                "USB устройство заблокировано", 
                f"Устройство {device_info_str} заблокировано политикой безопасности"
            )
            
        else:  # unknown
            log_message('INFO', f"Неизвестное устройство, запрос отправлен администратору: {log_info}")
            send_desktop_notification(
                username, 
                "USB устройство ожидает разрешения", 
                f"Устройство {device_info_str} ожидает разрешения администратора"
            )

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\nЗавершение работы.")
