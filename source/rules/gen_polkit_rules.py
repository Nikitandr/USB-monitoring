#!/usr/bin/env python3
import os
import sys
import stat

# Пути для файла .pkla
PKLA_DIR = "/etc/polkit-1/localauthority/50-local.d"
PKLA_PATH = os.path.join(PKLA_DIR, "disable-usb-mount.pkla")

PKLA_CONTENT = """\
[Disable USB filesystem mount]
Identity=unix-user:*
Action=org.freedesktop.udisks2.filesystem-mount;org.freedesktop.udisks2.filesystem-mount-system
ResultActive=no
ResultAny=no
ResultInactive=no
"""

def check_root():
    if os.geteuid() != 0:
        print("Ошибка: этот скрипт нужно запускать от root (sudo).", file=sys.stderr)
        sys.exit(1)

def ensure_directory():
    if not os.path.isdir(PKLA_DIR):
        os.makedirs(PKLA_DIR, exist_ok=True)
        print(f"Создана директория {PKLA_DIR}")

def write_pkla():
    with open(PKLA_PATH, "w", encoding="utf-8") as f:
        f.write(PKLA_CONTENT)
    # Устанавливаем права 0644
    os.chmod(PKLA_PATH, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    print(f"Записан файл {PKLA_PATH}")

def main():
    check_root()
    ensure_directory()
    write_pkla()
    print("Polkit локальная политика для USB-монтажа успешно создана.")

if __name__ == "__main__":
    main()
