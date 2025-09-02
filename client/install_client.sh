#!/bin/bash

# Скрипт установки USB Monitor Client
# Должен запускаться от root

set -e

# Проверяем права root
if [[ $EUID -ne 0 ]]; then
   echo "Этот скрипт должен запускаться от root (sudo)" 
   exit 1
fi

echo "=== Установка USB Monitor Client ==="

# Определяем пути
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/usb-monitor"
BIN_PATH="/usr/local/bin/usb-monitor"
SERVICE_PATH="/etc/systemd/system/usb-monitor.service"
CONFIG_PATH="/etc/usb-monitor/config.yaml"

echo "Создание директорий..."
mkdir -p /opt/usb-monitor
mkdir -p /etc/usb-monitor
mkdir -p /var/log/usb-monitor

echo "Копирование файлов..."
cp "$SCRIPT_DIR/monitor.py" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/config.yaml" "$CONFIG_PATH"

# Создаем исполняемый файл
echo "Создание исполняемого файла..."
cat > "$BIN_PATH" << 'EOF'
#!/bin/bash
cd /opt/usb-monitor
exec python3 monitor.py "$@"
EOF

chmod +x "$BIN_PATH"

# Устанавливаем systemd service
echo "Установка systemd service..."
cp "$SCRIPT_DIR/usb-monitor.service" "$SERVICE_PATH"

# Проверяем версию Ubuntu
echo "Проверка совместимости системы..."
if ! grep -q "Ubuntu 22.04" /etc/os-release 2>/dev/null; then
    echo "ПРЕДУПРЕЖДЕНИЕ: Скрипт протестирован только на Ubuntu 22.04"
    echo "Текущая система: $(lsb_release -d 2>/dev/null || echo 'Неизвестно')"
    read -p "Продолжить установку? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Установка отменена"
        exit 1
    fi
fi

# Устанавливаем зависимости через apt
echo "Обновление списка пакетов..."
apt-get update

echo "Установка зависимостей..."
REQUIRED_PACKAGES=(
    "python3"
    "python3-pyudev"
    "python3-yaml" 
    "python3-requests"
    "python3-pydbus"
    "python3-gi"
    "libnotify-bin"
    "policykit-1"
    "udev"
    "systemd"
)

# Устанавливаем все пакеты одной командой
apt-get install -y "${REQUIRED_PACKAGES[@]}"

# Проверяем, что все критически важные пакеты установлены
echo "Проверка установленных зависимостей..."
FAILED_IMPORTS=""

python3 -c "import pyudev" 2>/dev/null || FAILED_IMPORTS="$FAILED_IMPORTS pyudev"
python3 -c "import yaml" 2>/dev/null || FAILED_IMPORTS="$FAILED_IMPORTS yaml"
python3 -c "import requests" 2>/dev/null || FAILED_IMPORTS="$FAILED_IMPORTS requests"
python3 -c "import pydbus" 2>/dev/null || FAILED_IMPORTS="$FAILED_IMPORTS pydbus"
python3 -c "from gi.repository import GLib" 2>/dev/null || FAILED_IMPORTS="$FAILED_IMPORTS gi.repository.GLib"

if [ -n "$FAILED_IMPORTS" ]; then
    echo "ОШИБКА: Не удалось импортировать модули:$FAILED_IMPORTS"
    echo "Попробуйте установить недостающие пакеты вручную:"
    echo "  sudo apt-get install python3-pyudev python3-yaml python3-requests python3-pydbus python3-gi"
    exit 1
fi

# Проверяем системные утилиты
if ! command -v notify-send >/dev/null 2>&1; then
    echo "ОШИБКА: notify-send не найден. Установите libnotify-bin"
    exit 1
fi

echo "Все зависимости успешно установлены"

# Генерируем правила для отключения автомонтирования
# Генерируем правила для отключения автомонтирования
echo "Генерация правил для отключения автомонтирования..."
cd "$SCRIPT_DIR"

if [ ! -f "rules/gen_polkit_rules.py" ] || [ ! -f "rules/gen_udev_rules.py" ]; then
    echo "ОШИБКА: Не найдены скрипты генерации правил в папке rules/"
    echo "Убедитесь, что файлы rules/gen_polkit_rules.py и rules/gen_udev_rules.py существуют"
    exit 1
fi

echo "Генерация polkit правил..."
python3 rules/gen_polkit_rules.py || {
    echo "ОШИБКА: Не удалось сгенерировать polkit правила"
    exit 1
}

echo "Генерация udev правил..."
python3 rules/gen_udev_rules.py || {
    echo "ОШИБКА: Не удалось сгенерировать udev правила"
    exit 1
}

echo "Перезагрузка правил..."
udevadm control --reload-rules || {
    echo "ПРЕДУПРЕЖДЕНИЕ: Не удалось перезагрузить udev правила"
}

if systemctl is-active --quiet polkit; then
    systemctl restart polkit || {
        echo "ПРЕДУПРЕЖДЕНИЕ: Не удалось перезапустить polkit"
    }
else
    echo "ПРЕДУПРЕЖДЕНИЕ: polkit не запущен"
fi

# Настройка systemd
echo "Настройка systemd service..."
systemctl daemon-reload || {
    echo "ОШИБКА: Не удалось перезагрузить systemd"
    exit 1
}

systemctl enable usb-monitor.service || {
    echo "ОШИБКА: Не удалось включить автозапуск службы"
    exit 1
}

# Проверяем, что служба корректно настроена
if systemctl is-enabled usb-monitor.service >/dev/null 2>&1; then
    echo "Служба usb-monitor успешно настроена для автозапуска"
else
    echo "ПРЕДУПРЕЖДЕНИЕ: Служба может быть настроена некорректно"
fi

echo ""
echo "=== Установка завершена ==="
echo ""
echo "Конфигурация: $CONFIG_PATH"
echo "Логи: journalctl -u usb-monitor -f"
echo ""
echo "Для запуска службы:"
echo "  sudo systemctl start usb-monitor"
echo ""
echo "Для проверки статуса:"
echo "  sudo systemctl status usb-monitor"
echo ""
echo "ВАЖНО: Отредактируйте $CONFIG_PATH для настройки подключения к серверу"
echo ""
