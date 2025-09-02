#!/usr/bin/env python3
import os
import sys
import stat
import subprocess

UDEV_RULE_PATH = "/etc/udev/rules.d/99-usb-ignore.rules"
UDEV_RULE_CONTENT = r'''
# /etc/udev/rules.d/99-usb-ignore.rules
# Полностью игнорируем все USB-блочные устройства
ACTION=="add|change", SUBSYSTEM=="block", ENV{ID_BUS}=="usb", ENV{UDISKS_IGNORE}="1"
'''.lstrip()

def check_root():
    if os.geteuid() != 0:
        print("Этот скрипт нужно запускать от root (sudo).")
        sys.exit(1)

def write_rule():
    with open(UDEV_RULE_PATH, 'w', encoding='utf-8') as f:
        f.write(UDEV_RULE_CONTENT)
    # Сделаем права 0644
    os.chmod(UDEV_RULE_PATH, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
    print(f"Записано udev-правило в {UDEV_RULE_PATH}")

def reload_udev():
    subprocess.run(["udevadm", "control", "--reload-rules"], check=True)
    subprocess.run([
        "udevadm", "trigger",
        "--subsystem-match=block",
        "--attr-match=ID_BUS=usb"
    ], check=True)
    print("udev-правила перезагружены и триггеры выполнены")

def main():
    check_root()
    write_rule()
    reload_udev()

if __name__ == "__main__":
    main()
