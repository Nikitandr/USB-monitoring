# USB Monitor Security System - Техническая документация

Система безопасности для контроля подключения USB-устройств в корпоративной сети с централизованным управлением и принудительным контролем доступа.

## Архитектура системы

### Обзор компонентов

```
┌─────────────────┐    HTTPS/WSS     ┌──────────────────┐
│   Admin Client  │◄────────────────►│   Flask Server   │
│   (Windows 11)  │                  │   (Docker/SSL)   │
└─────────────────┘                  └──────────────────┘
                                              │
                                              │ HTTPS API
                                              ▼
┌─────────────────┐    HTTPS/WSS     ┌──────────────────┐
│ Linux Clients   │◄────────────────►│   Database       │
│ (Ubuntu 22.04)  │                  │   (SQLite)       │
│                 │                  └──────────────────┘
│ ┌─────────────┐ │
│ │ USB Monitor │ │
│ │ Daemon      │ │
│ └─────────────┘ │
│ ┌─────────────┐ │
│ │ UDev Rules  │ │
│ └─────────────┘ │
│ ┌─────────────┐ │
│ │ Polkit      │ │
│ │ Rules       │ │
│ └─────────────┘ │
└─────────────────┘
```

### Принципы работы

1. **Отключение автомонтирования**: Polkit и UDev правила блокируют стандартное автомонтирование USB
2. **Перехват событий**: UDev мониторинг отслеживает подключение USB устройств
3. **Централизованная авторизация**: Каждое устройство проверяется через HTTPS API сервера
4. **Real-time уведомления**: WebSocket соединения для мгновенных уведомлений
5. **Fail-safe безопасность**: При недоступности сервера все устройства блокируются

## Серверная архитектура

### Структура приложения

```
server/
├── app.py                 # Основное Flask приложение с SocketIO
├── config.py             # Конфигурация (SSL, DB, аутентификация)
├── Dockerfile            # Docker контейнер
├── requirements.txt      # Python зависимости
├── database/            # Модели данных и ORM
│   ├── database.py      # Основной класс БД
│   ├── models/          # SQLite модели
│   └── migrations/      # Схемы миграций
├── utils/               # Утилиты
│   └── logger.py        # Система логирования
├── web/                 # Веб-интерфейс
│   ├── templates/       # HTML шаблоны
│   └── static/          # CSS/JS ресурсы
└── certs/               # SSL сертификаты
    ├── server.crt       # Публичный сертификат
    ├── server.key       # Приватный ключ
    └── server.pem       # PEM формат
```

### Flask приложение

**Основные компоненты:**
- **Flask-SocketIO**: WebSocket сервер для real-time коммуникации
- **CORS**: Настроенный для безопасного cross-origin доступа
- **SSL Context**: Обязательное HTTPS шифрование
- **Session Management**: Аутентификация администратора

**Конфигурация безопасности:**
```python
# Только HTTPS, HTTP отключен
SSL_ENABLED = True
PORT = 443
SSL_CERT_PATH = 'certs/server.crt'
SSL_KEY_PATH = 'certs/server.key'

# TLS настройки
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.maximum_version = ssl.TLSVersion.TLSv1_3
```

### База данных

**SQLite схема:**
```sql
-- Пользователи системы
users (id, username, created_at, last_seen)

-- USB устройства
devices (id, vid, pid, serial, name, created_at)

-- Разрешения пользователь-устройство
permissions (id, user_id, device_id, allowed, created_at, updated_at)

-- Запросы на подключение
requests (id, user_id, device_id, status, device_info, 
         request_time, response_time, admin_username)
```

### Docker контейнеризация

**Dockerfile особенности:**
- Python 3.11 slim базовый образ
- Непривилегированный пользователь (appuser)
- Персистентные данные в `/app/data`
- Health check через HTTPS endpoint
- SSL сертификаты как read-only volume

**Docker Compose конфигурация:**
```yaml
services:
  usb-monitor-server:
    build: ./server
    ports:
      - "443:443"
    volumes:
      - ./data:/app/data
      - ./server/certs:/app/certs:ro
    environment:
      - SSL_ENABLED=true
      - DATABASE_PATH=/app/data/usb_monitor.db
```

## Клиентская архитектура

### Структура клиента

```
client/
├── monitor.py           # Основной демон
├── config.yaml         # Конфигурация клиента
├── install_client.sh   # Скрипт установки
├── usb-monitor.service # SystemD unit файл
└── rules/              # Генераторы правил
    ├── gen_polkit_rules.py
    └── gen_udev_rules.py
```

### USB Monitor Daemon

**Основные модули:**
```python
# UDev мониторинг
context = pyudev.Context()
monitor = pyudev.Monitor.from_netlink(context)
monitor.filter_by(subsystem='block')

# D-Bus интеграция для монтирования
bus = SystemBus()
udisks = bus.get('org.freedesktop.UDisks2')

# WebSocket клиент для real-time уведомлений
sio = socketio.Client(ssl_verify=False)
```

**Алгоритм обработки USB событий:**
1. **Детекция устройства**: UDev событие `add` для USB блочного устройства
2. **Определение пользователя**: Множественные fallback методы
3. **Извлечение метаданных**: VID/PID/Serial из UDev атрибутов
4. **API запрос**: HTTPS POST к `/api/devices/check`
5. **Обработка ответа**:
   - `allowed` → монтирование через UDisks2
   - `denied` → блокировка + уведомление
   - `unknown` → запрос администратору + ожидание

### Определение активного пользователя

**Fallback методы (в порядке приоритета):**
1. **loginctl**: Анализ активных сессий через systemd-logind
2. **who**: Парсинг графических терминалов (`:0`, `tty7`)
3. **X11 процессы**: Поиск владельцев Xorg процессов
4. **/proc анализ**: Сканирование DISPLAY переменных в процессах

```python
def get_active_user():
    # Метод 1: loginctl (основной)
    for session in loginctl_sessions:
        if session.seat == "seat0" and session.state == "active":
            return session.user
    
    # Метод 2-4: fallback методы
    return fallback_user_detection()
```

### Система монтирования

**UDisks2 D-Bus интеграция:**
```python
# Прямое монтирование через mount с nsenter
mount_cmd = [
    '/usr/bin/nsenter', '-t', '1', '-m', 
    '/bin/mount', '-o', mount_options, 
    device_node, mount_point
]
```

**Безопасная очистка:**
- Принудительное закрытие процессов (SIGTERM → SIGKILL)
- Проверка занятости точек монтирования
- Автоматическая очистка при запуске демона

### Polkit/UDev правила

**Polkit правило (отключение автомонтирования):**
```javascript
polkit.addRule(function(action, subject) {
    if (action.id.indexOf("org.freedesktop.udisks2.") == 0) {
        return polkit.Result.NO;
    }
});
```

**UDev правило (блокировка USB):**
```bash
# Блокировка автомонтирования USB устройств
SUBSYSTEM=="block", ENV{ID_BUS}=="usb", ENV{UDISKS_IGNORE}="1"
```

## Протоколы коммуникации

### HTTPS REST API

**Базовый URL:** `https://server:443/api`

#### Проверка разрешения устройства
```http
POST /api/devices/check
Content-Type: application/json

{
  "username": "user1",
  "vid": "0781",
  "pid": "5567", 
  "serial": "123456"
}

Response:
{
  "status": "allowed" | "denied" | "unknown"
}
```

#### Создание запроса на разрешение
```http
POST /api/requests
Content-Type: application/json

{
  "username": "user1",
  "vid": "0781",
  "pid": "5567",
  "serial": "123456", 
  "device_info": "SanDisk Cruzer Blade 16GB"
}

Response:
{
  "request_id": 123,
  "status": "pending"
}
```

#### Управление запросами (только админ)
```http
POST /api/requests/{id}/approve
POST /api/requests/{id}/deny

Response:
{
  "status": "approved" | "denied"
}
```

#### Статистика и отчеты
```http
GET /api/stats
GET /api/requests?status=pending&username=user1
GET /api/users
GET /api/users/{username}/devices
```

### WebSocket события

**Подключение и комнаты:**
```javascript
// Администратор
socket.emit('join_admin');

// Пользователь  
socket.emit('join_user', {username: 'user1'});
```

**События сервера:**
```javascript
// Новый запрос (→ admin)
socket.emit('device_request', {
  request_id: 123,
  username: 'user1',
  device_info: 'SanDisk USB',
  vid: '0781',
  pid: '5567'
});

// Одобрение запроса (→ user)
socket.emit('request_approved', {
  request_id: 123,
  username: 'user1'
});

// Отклонение запроса (→ user)
socket.emit('request_denied', {
  request_id: 123, 
  username: 'user1'
});
```

## Безопасность

### Принципы безопасности

1. **Fail-safe по умолчанию**: При недоступности сервера все USB устройства блокируются
2. **Обязательное шифрование**: Только HTTPS/WSS соединения, HTTP отключен
3. **Централизованное управление**: Локальные белые списки не используются
4. **Полный аудит**: Все события логируются с временными метками
5. **Минимальные привилегии**: Демон работает с ограниченными правами

### SSL/TLS конфигурация

**Генерация самоподписанных сертификатов:**
```bash
# Создание CA
openssl genrsa -out ca.key 4096
openssl req -new -x509 -days 365 -key ca.key -out ca.crt

# Создание серверного сертификата
openssl genrsa -out server.key 4096
openssl req -new -key server.key -out server.csr
openssl x509 -req -days 365 -in server.csr -CA ca.crt -CAkey ca.key -out server.crt
```

**TLS настройки:**
- Минимальная версия: TLS 1.2
- Максимальная версия: TLS 1.3
- Шифры: ECDHE+AESGCM, ECDHE+CHACHA20, DHE+AESGCM
- Отключены: aNULL, MD5, DSS

### Системные правила безопасности

**Polkit правила:**
- Блокировка всех UDisks2 операций для обычных пользователей
- Исключения только для root и системных процессов

**UDev правила:**
- Установка UDISKS_IGNORE=1 для всех USB блочных устройств
- Предотвращение автоматического создания device nodes

## Мониторинг и логирование

### Структура логов

**Серверные логи:**
```
[2024-01-15 10:30:45] INFO: USB Monitor Server запущен
[2024-01-15 10:30:46] INFO: SSL контекст создан успешно
[2024-01-15 10:30:47] INFO: База данных инициализирована
[2024-01-15 10:31:15] INFO: Admin logged in from 192.168.1.100
[2024-01-15 10:32:30] INFO: Device check: user1, 0781:5567:123456, allowed
[2024-01-15 10:33:45] WARNING: Device request: user2, 1234:5678:abcdef, unknown
```

**Клиентские логи:**
```
[2024-01-15 10:30:45] INFO: Запуск USB Monitor Client
[2024-01-15 10:30:46] INFO: WebSocket подключение установлено
[2024-01-15 10:30:47] INFO: Мониторинг USB-событий запущен
[2024-01-15 10:32:30] INFO: USB устройство подключено: VID:PID=0781:5567
[2024-01-15 10:32:31] INFO: Сервер ответил: allowed для user1:0781:5567:123456
[2024-01-15 10:32:32] INFO: Устройство /dev/sdb успешно смонтировано в /media/user1/USB_DRIVE
```

### Системные метрики

**Health checks:**
- HTTP endpoint: `GET https://server:443/` (код 200)
- WebSocket connectivity: Ping/pong каждые 30 секунд
- Database connectivity: SQLite pragma проверки
- SSL certificate validity: Проверка срока действия

**Мониторинг клиентов:**
```bash
# Статус службы
systemctl status usb-monitor

# Логи в реальном времени
journalctl -u usb-monitor -f

# Системные события USB
udevadm monitor --subsystem-match=block
```

## Развертывание

### Docker развертывание (рекомендуемый)

```bash
# 1. Генерация SSL сертификатов
bash scripts/ssl/generate_certs.sh

# 2. Запуск через Docker Compose
docker-compose up -d

# 3. Проверка статуса
docker-compose ps
docker-compose logs usb-monitor-server
```

### Ручное развертывание сервера

```bash
# 1. Установка зависимостей
cd server
pip install -r requirements.txt

# 2. Генерация SSL сертификатов
mkdir -p certs
# ... генерация сертификатов

# 3. Настройка переменных окружения
export FLASK_ENV=production
export SSL_CERT_PATH=certs/server.crt
export SSL_KEY_PATH=certs/server.key

# 4. Запуск сервера
python app.py
```

### Установка клиента

```bash
# 1. Копирование файлов на Linux машину
scp -r client/ user@linux-machine:/tmp/

# 2. Установка от root
sudo /tmp/client/install_client.sh

# 3. Настройка конфигурации
sudo nano /etc/usb-monitor/config.yaml

# 4. Запуск службы
sudo systemctl start usb-monitor
sudo systemctl enable usb-monitor
```

### Конфигурационные файлы

**Серверная конфигурация (.env):**
```bash
FLASK_ENV=production
HOST=0.0.0.0
PORT=443
ADMIN_USERNAME=admin
ADMIN_PASSWORD=secure_password_here
DATABASE_PATH=/app/data/usb_monitor.db
SSL_CERT_PATH=/app/certs/server.crt
SSL_KEY_PATH=/app/certs/server.key
LOG_LEVEL=INFO
```

**Клиентская конфигурация (config.yaml):**
```yaml
server:
  server_url: "https://192.168.1.100:443"
  timeout: 10
  retry_attempts: 3
  retry_delay: 5
  cache_duration: 300
  ssl_verify: false  # Для самоподписанных сертификатов
  ssl_warnings: false
```

## Диагностика и отладка

### Типичные проблемы

**1. SSL сертификат не найден**
```bash
# Проверка наличия сертификатов
ls -la server/certs/
# Генерация новых сертификатов
bash scripts/ssl/generate_certs.sh
```

**2. Клиент не может подключиться к серверу**
```bash
# Проверка сетевого соединения
curl -k https://server-ip:443/
# Проверка логов клиента
journalctl -u usb-monitor -n 50
```

**3. USB устройства не блокируются**
```bash
# Проверка polkit правил
ls -la /etc/polkit-1/rules.d/
# Проверка udev правил  
ls -la /etc/udev/rules.d/
# Перезагрузка правил
sudo udevadm control --reload-rules
sudo systemctl restart polkit
```

**4. WebSocket соединение не работает**
```bash
# Проверка WebSocket подключения
wscat -c wss://server-ip:443 --no-check
# Проверка логов сервера
docker-compose logs usb-monitor-server
```

### Отладочные команды

```bash
# Тестирование API
curl -k -X POST https://server:443/api/devices/check \
  -H "Content-Type: application/json" \
  -d '{"username":"test","vid":"0781","pid":"5567","serial":"123"}'

# Мониторинг USB событий
udevadm monitor --subsystem-match=block --property

# Проверка монтирования
mount | grep /media/
lsblk -f

# Анализ процессов
ps aux | grep usb-monitor
systemctl status usb-monitor
```

## Ограничения и известные проблемы

1. **Совместимость**: Протестировано только на Ubuntu 22.04
2. **Производительность**: Не оптимизировано для >100 одновременных клиентов
3. **Безопасность**: Использует самоподписанные SSL сертификаты
4. **Масштабируемость**: SQLite база данных не подходит для больших нагрузок
5. **Отказоустойчивость**: Единая точка отказа (сервер)

## Лицензия и назначение

Проект создан для демонстрации концепции безопасности USB-устройств в корпоративной среде. Не предназначен для продакшн использования без дополнительной доработки в области:

- Масштабируемости (переход на PostgreSQL/MySQL)
- Безопасности (CA сертификаты, аутентификация клиентов)
- Отказоустойчивости (кластеризация, репликация)
- Мониторинга (интеграция с Prometheus/Grafana)
- Управления (REST API для автоматизации)
