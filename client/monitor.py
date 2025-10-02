#!/usr/bin/env python3
import pyudev
import yaml
import os
import sys
import subprocess
import requests
import json
import time
import urllib3
import threading
import socketio

# Глобальное отключение SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
urllib3.disable_warnings()

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

# Глобальные переменные
_pending_requests = {}
_pending_devices = {}  # Устройства, ожидающие разрешения: device_key -> device_info
_websocket_client = None

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
    
    # Настройка SSL предупреждений
    if not server_config.get('ssl_warnings', True):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        urllib3.disable_warnings()
    
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
            response = requests.post(
                url, 
                json=data, 
                timeout=server_config['timeout'],
                verify=ssl_verify
            )
            
            if response.status_code == 200:
                result = response.json()
                status = result.get('status', 'unknown')
                
                # Очищаем ожидающий запрос, если устройство получило окончательный статус
                if status in ['allowed', 'denied'] and device_key in _pending_requests:
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

def get_active_user():
    """Определяет активного пользователя через loginctl (systemd-logind)"""
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

def force_close_mount_point(mount_point):
    """Принудительно закрывает процессы, использующие точку монтирования"""
    try:
        # Проверяем, какие процессы используют точку монтирования
        lsof_result = subprocess.run(
            ['lsof', '+D', mount_point], 
            capture_output=True, text=True, check=False
        )
        
        if lsof_result.returncode == 0 and lsof_result.stdout.strip():
            log_message('WARNING', f"Найдены процессы, использующие {mount_point}")
            
            # Сначала пытаемся мягко завершить процессы (SIGTERM)
            fuser_result = subprocess.run(
                ['fuser', '-m', mount_point], 
                capture_output=True, text=True, check=False
            )
            
            if fuser_result.returncode == 0:
                log_message('INFO', f"Отправляем SIGTERM процессам, использующим {mount_point}")
                subprocess.run(['fuser', '-k', '-TERM', mount_point], 
                             capture_output=True, check=False)
                
                # Ждем 3 секунды для корректного завершения
                time.sleep(3)
                
                # Проверяем, остались ли процессы
                check_result = subprocess.run(
                    ['fuser', '-m', mount_point], 
                    capture_output=True, text=True, check=False
                )
                
                if check_result.returncode == 0:
                    log_message('WARNING', f"Процессы не завершились, отправляем SIGKILL")
                    subprocess.run(['fuser', '-k', '-KILL', mount_point], 
                                 capture_output=True, check=False)
                    time.sleep(1)
                
                return True
        
        return False
        
    except Exception as e:
        log_message('WARNING', f"Ошибка при принудительном закрытии процессов для {mount_point}: {e}")
        return False

def safe_remove_mount_point(mount_point, max_attempts=3):
    """Безопасно удаляет точку монтирования с повторными попытками"""
    for attempt in range(max_attempts):
        try:
            if not os.path.exists(mount_point):
                return True
                
            if not os.path.isdir(mount_point):
                log_message('WARNING', f"Точка монтирования {mount_point} не является директорией")
                return False
            
            # Проверяем, что папка пустая
            if os.listdir(mount_point):
                if attempt == 0:  # Только при первой попытке пытаемся закрыть процессы
                    log_message('INFO', f"Точка монтирования {mount_point} не пустая, пытаемся закрыть процессы")
                    if force_close_mount_point(mount_point):
                        time.sleep(2)  # Даем время на освобождение ресурсов
                        continue
                
                log_message('WARNING', f"Точка монтирования {mount_point} не пустая (попытка {attempt + 1})")
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
                else:
                    return False
            
            # Пытаемся удалить пустую директорию
            os.rmdir(mount_point)
            log_message('INFO', f"Удалена точка монтирования: {mount_point}")
            return True
            
        except OSError as e:
            if e.errno == 16:  # Device or resource busy
                if attempt == 0:
                    log_message('INFO', f"Точка монтирования {mount_point} занята, пытаемся освободить")
                    if force_close_mount_point(mount_point):
                        time.sleep(2)
                        continue
                
                log_message('WARNING', f"Точка монтирования {mount_point} занята (попытка {attempt + 1})")
                if attempt < max_attempts - 1:
                    time.sleep(2)
                    continue
            else:
                log_message('WARNING', f"Ошибка удаления {mount_point}: {e}")
                break
        except Exception as e:
            log_message('WARNING', f"Неожиданная ошибка при удалении {mount_point}: {e}")
            break
    
    return False

def unmount_device(device_node):
    """Размонтирует USB устройство и очищает точку монтирования"""
    log_message('INFO', f"Размонтирование устройства {device_node}")
    
    try:
        # Находим все точки монтирования для данного устройства
        mount_check = subprocess.run(['/bin/mount'], capture_output=True, text=True)
        mount_points = set()  # Используем set для избежания дублирования
        
        for line in mount_check.stdout.splitlines():
            if device_node in line and ' on ' in line:
                # Парсим строку монтирования: /dev/sdb on /media/user/1812-D65 type vfat (...)
                parts = line.split(' on ')
                if len(parts) >= 2:
                    mount_point = parts[1].split(' type ')[0].strip()
                    if mount_point:  # Проверяем, что точка монтирования не пустая
                        mount_points.add(mount_point)
        
        if not mount_points:
            log_message('INFO', f"Точки монтирования для {device_node} не найдены")
            return
        
        log_message('INFO', f"Найдено точек монтирования: {len(mount_points)}")
        
        # Размонтируем каждую найденную точку
        for mount_point in mount_points:
            try:
                # Проверяем, что точка монтирования еще существует
                if not os.path.exists(mount_point):
                    continue
                
                # Используем nsenter для размонтирования в основном namespace
                umount_cmd = ['/usr/bin/nsenter', '-t', '1', '-m', '/bin/umount', mount_point]
                
                result = subprocess.run(umount_cmd, capture_output=True, text=True, check=False)
                
                if result.returncode == 0:
                    log_message('INFO', f"Устройство {device_node} размонтировано из {mount_point}")
                    
                    # Безопасно удаляем точку монтирования
                    safe_remove_mount_point(mount_point)
                        
                else:
                    # Проверяем, не была ли точка уже размонтирована
                    if "not mounted" in result.stderr or "no mount point" in result.stderr:
                        log_message('INFO', f"Точка {mount_point} уже размонтирована")
                        # Все равно пытаемся удалить директорию
                        safe_remove_mount_point(mount_point)
                    else:
                        log_message('ERROR', f"Ошибка размонтирования {mount_point}: {result.stderr.strip()}")
                    
            except Exception as e:
                log_message('ERROR', f"Неожиданная ошибка при размонтировании {mount_point}: {e}")
                
    except Exception as e:
        log_message('ERROR', f"Ошибка при поиске точек монтирования для {device_node}: {e}")


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
    """Монтирует USB устройство через nsenter"""
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

    # Создаем базовую папку если нужно
    if not os.path.isdir(mount_base):
        try:
            os.makedirs(mount_base, exist_ok=True)
            if target_user != "root":
                subprocess.run(["/bin/chown", f"{target_user}:{target_user}", mount_base], check=False)
        except Exception as e:
            log_message('ERROR', f"Не удалось создать {mount_base}: {e}")
            return

    # Простое имя папки монтирования (базовое имя устройства)
    mount_name = os.path.basename(device_node)
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

    # Монтируем устройство через nsenter
    try:
        if target_user != "root":
            mount_options = f'rw,nosuid,nodev,uid={uid},gid={gid},umask=0022'
        else:
            mount_options = 'rw,nosuid,nodev'
        
        # Используем nsenter для монтирования в основном namespace (PID 1)
        mount_cmd = ['/usr/bin/nsenter', '-t', '1', '-m', '/bin/mount', '-o', mount_options, device_node, mount_point]
        
        # Выполняем монтирование
        result = subprocess.run(mount_cmd, capture_output=True, text=True, check=False)
        
        if result.returncode == 0:
            log_message('INFO', f"Устройство {device_node} успешно смонтировано в: {mount_point}")
            
            # Устанавливаем права на точку монтирования
            if target_user != "root":
                subprocess.run(["/bin/chown", f"{target_user}:{target_user}", mount_point], check=False)
                subprocess.run(["/bin/chmod", "755", mount_point], check=False)
        else:
            log_message('ERROR', f"Ошибка монтирования {device_node}: {result.stderr.strip()}")
            
            # Удаляем созданную точку монтирования при ошибке
            try:
                if os.path.exists(mount_point) and os.path.isdir(mount_point):
                    os.rmdir(mount_point)
            except Exception:
                pass
            
    except Exception as e:
        log_message('ERROR', f"Неожиданная ошибка при монтировании: {e}")

def send_desktop_notification(username, title, message):
    """Отправляет уведомление пользователю"""
    log_message('DEBUG', f"📢 Отправка уведомления пользователю {username}: {title}")
    
    # Метод 1: Через su с определением окружения пользователя
    try:
        # Ищем окружение пользователя
        display = None
        wayland_display = None
        
        for proc_dir in os.listdir('/proc'):
            if not proc_dir.isdigit():
                continue
            try:
                environ_path = f'/proc/{proc_dir}/environ'
                if os.path.exists(environ_path):
                    with open(environ_path, 'rb') as f:
                        environ_data = f.read().decode('utf-8', errors='ignore')
                    
                    if f'USER={username}' in environ_data:
                        for line in environ_data.split('\0'):
                            if line.startswith('DISPLAY='):
                                display = line.split('=', 1)[1]
                            elif line.startswith('WAYLAND_DISPLAY='):
                                wayland_display = line.split('=', 1)[1]
                        if display or wayland_display:
                            break
            except (OSError, IOError, PermissionError):
                continue
        
        if display or wayland_display:
            import pwd
            user_info = pwd.getpwnam(username)
            uid = user_info.pw_uid
            
            # Настраиваем окружение
            env = {
                'USER': username,
                'HOME': user_info.pw_dir,
                'PATH': '/usr/local/bin:/usr/bin:/bin',
            }
            
            if display:
                env['DISPLAY'] = display
            if wayland_display:
                env['WAYLAND_DISPLAY'] = wayland_display
            
            env['XDG_RUNTIME_DIR'] = f'/run/user/{uid}'
            
            # Отправляем уведомление
            result = subprocess.run([
                'su', '-', username, '-c', 
                f'notify-send --urgency=normal --expire-time=5000 "{title}" "{message}"'
            ], env=env, capture_output=True, text=True, timeout=10, check=False)
            
            if result.returncode == 0:
                log_message('INFO', f"✅ Уведомление отправлено пользователю {username}")
                return True
            else:
                log_message('DEBUG', f"Ошибка отправки уведомления: {result.stderr.strip()}")
                
    except Exception as e:
        log_message('DEBUG', f"Ошибка при отправке уведомления: {e}")
    
    # Метод 2: Fallback в системный лог
    try:
        subprocess.run([
            'logger', '-t', 'usb-monitor', 
            f"NOTIFICATION for {username}: {title} - {message}"
        ], check=False, timeout=5)
        log_message('WARNING', f"⚠️ Уведомление записано в syslog для {username}")
        return False
        
    except Exception as e:
        log_message('ERROR', f"Ошибка записи в syslog: {e}")
    
    log_message('ERROR', f"❌ Не удалось отправить уведомление пользователю {username}")
    return False

class WebSocketClient:
    """WebSocket клиент для получения уведомлений от сервера"""
    
    def __init__(self, server_config):
        self.server_config = server_config
        self.sio = socketio.Client(ssl_verify=server_config.get('ssl_verify', False))
        self.connected = False
        self.current_user = None
        
        # Настраиваем обработчики событий
        self.sio.on('connect', self.on_connect)
        self.sio.on('disconnect', self.on_disconnect)
        self.sio.on('request_approved', self.on_request_approved)
        self.sio.on('request_denied', self.on_request_denied)
    
    def connect(self):
        """Подключается к WebSocket серверу"""
        try:
            server_url = self.server_config['server_url']
            log_message('INFO', f"🔌 Попытка подключения к WebSocket серверу: {server_url}")
            
            # Подключаемся без дополнительных параметров (совместимость с socketio 5.x)
            self.sio.connect(server_url)
            log_message('INFO', f"✅ WebSocket подключение установлено успешно")
            return True
            
        except Exception as e:
            log_message('ERROR', f"❌ Ошибка подключения к WebSocket: {e}")
            return False
    
    def disconnect(self):
        """Отключается от WebSocket сервера"""
        try:
            if self.connected:
                self.sio.disconnect()
        except Exception as e:
            log_message('ERROR', f"Ошибка отключения от WebSocket: {e}")
    
    def join_user_room(self, username):
        """Присоединяется к комнате пользователя"""
        try:
            if self.connected:
                self.current_user = username
                self.sio.emit('join_user', {'username': username})
                log_message('INFO', f"Присоединились к комнате пользователя: {username}")
            else:
                log_message('WARNING', f"Попытка присоединиться к комнате {username}, но WebSocket не подключен")
        except Exception as e:
            log_message('ERROR', f"Ошибка присоединения к комнате пользователя {username}: {e}")
    
    def on_connect(self):
        """Обработчик подключения"""
        self.connected = True
        log_message('INFO', "WebSocket подключен")
        
        # Присоединяемся к комнате текущего пользователя, если он известен
        if self.current_user:
            self.join_user_room(self.current_user)
    
    def on_disconnect(self):
        """Обработчик отключения"""
        self.connected = False
        log_message('WARNING', "WebSocket отключен")
    
    def on_request_approved(self, data):
        """Обработчик одобрения запроса"""
        try:
            username = data.get('username')
            request_id = data.get('request_id')
            
            log_message('INFO', f"🟢 WebSocket: Получено одобрение запроса {request_id} для пользователя {username}")
            log_message('DEBUG', f"Данные события одобрения: {data}")
            log_message('DEBUG', f"Текущие pending_devices: {list(_pending_devices.keys())}")
            log_message('DEBUG', f"Текущие pending_requests: {_pending_requests}")
            
            # Ищем соответствующее устройство в pending_devices
            device_to_mount = None
            device_key_to_remove = None
            
            for device_key, device_info in _pending_devices.items():
                log_message('DEBUG', f"Проверяем устройство {device_key}: username={device_info.get('username')}")
                if device_info.get('username') == username:
                    # Проверяем, соответствует ли это устройство запросу
                    if device_key in _pending_requests and _pending_requests[device_key] == request_id:
                        device_to_mount = device_info
                        device_key_to_remove = device_key
                        log_message('DEBUG', f"Найдено соответствующее устройство: {device_key}")
                        break
            
            if device_to_mount:
                log_message('INFO', f"🔧 Автоматически монтируем одобренное устройство: {device_to_mount['device_node']}")
                
                # Отправляем уведомление пользователю
                send_desktop_notification(
                    username,
                    "USB устройство одобрено",
                    f"Устройство {device_to_mount['device_info_str']} одобрено и подключается автоматически"
                )
                
                # Монтируем устройство
                mount_device(device_to_mount['device_node'])
                
                # Очищаем из pending
                if device_key_to_remove:
                    del _pending_devices[device_key_to_remove]
                    if device_key_to_remove in _pending_requests:
                        del _pending_requests[device_key_to_remove]
                    log_message('DEBUG', f"Очищены pending данные для {device_key_to_remove}")
            else:
                log_message('WARNING', f"❌ Не найдено устройство для одобренного запроса {request_id}")
                log_message('DEBUG', f"Доступные устройства для пользователя {username}:")
                for device_key, device_info in _pending_devices.items():
                    if device_info.get('username') == username:
                        log_message('DEBUG', f"  - {device_key}: request_id={_pending_requests.get(device_key, 'N/A')}")
                
        except Exception as e:
            log_message('ERROR', f"Ошибка обработки одобрения запроса: {e}")
            import traceback
            log_message('DEBUG', f"Traceback: {traceback.format_exc()}")
    
    def on_request_denied(self, data):
        """Обработчик отклонения запроса"""
        try:
            username = data.get('username')
            request_id = data.get('request_id')
            
            log_message('INFO', f"Получено отклонение запроса {request_id} для пользователя {username}")
            
            # Ищем соответствующее устройство в pending_devices
            device_key_to_remove = None
            device_info_str = "неизвестное устройство"
            
            for device_key, device_info in _pending_devices.items():
                if device_info.get('username') == username:
                    if device_key in _pending_requests and _pending_requests[device_key] == request_id:
                        device_info_str = device_info.get('device_info_str', device_info_str)
                        device_key_to_remove = device_key
                        break
            
            # Отправляем уведомление пользователю
            send_desktop_notification(
                username,
                "USB устройство отклонено",
                f"Запрос на подключение устройства {device_info_str} был отклонен администратором"
            )
            
            # Очищаем из pending
            if device_key_to_remove:
                del _pending_devices[device_key_to_remove]
                if device_key_to_remove in _pending_requests:
                    del _pending_requests[device_key_to_remove]
                    
        except Exception as e:
            log_message('ERROR', f"Ошибка обработки отклонения запроса: {e}")

def start_websocket_client(server_config):
    """Запускает WebSocket клиент в отдельном потоке"""
    global _websocket_client
    
    def websocket_thread():
        try:
            _websocket_client = WebSocketClient(server_config)
            
            # Пытаемся подключиться с повторными попытками
            max_attempts = 5
            for attempt in range(max_attempts):
                if _websocket_client.connect():
                    # После успешного подключения присоединяемся к комнате активного пользователя
                    time.sleep(2)  # Даем время на установку соединения
                    current_user = get_active_user()
                    if current_user:
                        log_message('INFO', f"Присоединяемся к комнате активного пользователя: {current_user}")
                        _websocket_client.join_user_room(current_user)
                    else:
                        log_message('WARNING', "Не удалось определить активного пользователя для WebSocket комнаты")
                    break
                else:
                    if attempt < max_attempts - 1:
                        log_message('WARNING', f"Попытка подключения WebSocket {attempt + 1}/{max_attempts} неудачна, повтор через 10 секунд")
                        time.sleep(10)
                    else:
                        log_message('ERROR', "Не удалось подключиться к WebSocket серверу")
                        return
            
            # Поддерживаем соединение
            while True:
                try:
                    time.sleep(30)  # Проверяем соединение каждые 30 секунд
                    if not _websocket_client.connected:
                        log_message('WARNING', "WebSocket соединение потеряно, пытаемся переподключиться")
                        if _websocket_client.connect():
                            # После переподключения снова присоединяемся к комнате
                            time.sleep(2)
                            current_user = get_active_user()
                            if current_user:
                                _websocket_client.join_user_room(current_user)
                except Exception as e:
                    log_message('ERROR', f"Ошибка в WebSocket потоке: {e}")
                    time.sleep(10)
                    
        except Exception as e:
            log_message('ERROR', f"Критическая ошибка в WebSocket потоке: {e}")
    
    # Запускаем WebSocket в отдельном потоке
    thread = threading.Thread(target=websocket_thread, daemon=True)
    thread.start()
    log_message('INFO', "WebSocket клиент запущен в фоновом режиме")

def main():
    check_root()
    
    log_message('INFO', "Запуск USB Monitor Client")

    # Загружаем конфигурацию
    cfg = load_config()
    
    log_message('INFO', f"Сервер: {cfg['server']['server_url']}")
    log_message('INFO', f"Таймаут: {cfg['server']['timeout']}с, попыток: {cfg['server']['retry_attempts']}")

    # Запускаем WebSocket клиент для получения уведомлений от сервера
    start_websocket_client(cfg['server'])

    # udev-мониторинг блочных устройств
    context = pyudev.Context()
    monitor = pyudev.Monitor.from_netlink(context)
    monitor.filter_by(subsystem='block')

    log_message('INFO', "Мониторинг USB-событий запущен")

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
            
            # Сохраняем информацию об устройстве для автоматического монтирования после одобрения
            device_key = f"{username}:{vid}:{pid}:{serial}"
            _pending_devices[device_key] = {
                'username': username,
                'device_node': device_node,
                'device_info_str': device_info_str,
                'vid': vid,
                'pid': pid,
                'serial': serial
            }
            
            # Присоединяемся к комнате пользователя через WebSocket для получения уведомлений
            global _websocket_client
            if _websocket_client and _websocket_client.connected:
                _websocket_client.join_user_room(username)
            
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
