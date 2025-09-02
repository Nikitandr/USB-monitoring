#!/bin/bash
# Скрипт генерации самоподписанных SSL сертификатов для USB Monitor Security System

set -e

CERT_DIR="server/certs"
DAYS=365
KEY_SIZE=4096
COUNTRY="RU"
STATE="Moscow"
CITY="Moscow"
ORG="USB Monitor"
OU="Security Department"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Генерация SSL сертификатов для USB Monitor ===${NC}"

# Проверка наличия OpenSSL
if ! command -v openssl &> /dev/null; then
    echo -e "${RED}Ошибка: OpenSSL не установлен${NC}"
    echo "Установите OpenSSL и повторите попытку"
    exit 1
fi

# Создание директории для сертификатов
echo -e "${YELLOW}Создание директории $CERT_DIR...${NC}"
mkdir -p "$CERT_DIR"

# Запрос IP адреса сервера
echo -e "${YELLOW}Введите IP адрес сервера (по умолчанию 192.168.1.100):${NC}"
read -r SERVER_IP
SERVER_IP=${SERVER_IP:-192.168.1.100}

echo -e "${YELLOW}Генерация приватного ключа...${NC}"
openssl genrsa -out "$CERT_DIR/server.key" $KEY_SIZE

echo -e "${YELLOW}Создание конфигурационного файла...${NC}"
cat > "$CERT_DIR/server.conf" <<EOF
[req]
distinguished_name = req_distinguished_name
req_extensions = v3_req
prompt = no

[req_distinguished_name]
C = $COUNTRY
ST = $STATE
L = $CITY
O = $ORG
OU = $OU
CN = localhost

[v3_req]
keyUsage = critical, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = localhost
DNS.2 = *.localhost
DNS.3 = usb-monitor.local
DNS.4 = *.usb-monitor.local
IP.1 = 127.0.0.1
IP.2 = ::1
IP.3 = $SERVER_IP
EOF

echo -e "${YELLOW}Генерация самоподписанного сертификата...${NC}"
openssl req -new -x509 \
    -key "$CERT_DIR/server.key" \
    -out "$CERT_DIR/server.crt" \
    -days $DAYS \
    -config "$CERT_DIR/server.conf" \
    -extensions v3_req \
    -sha256

echo -e "${YELLOW}Создание PEM файла...${NC}"
cat "$CERT_DIR/server.crt" "$CERT_DIR/server.key" > "$CERT_DIR/server.pem"

# Установка правильных прав доступа
chmod 600 "$CERT_DIR/server.key"
chmod 644 "$CERT_DIR/server.crt"
chmod 600 "$CERT_DIR/server.pem"

echo -e "${GREEN}=== Сертификаты успешно созданы ===${NC}"
echo -e "Директория: ${YELLOW}$CERT_DIR/${NC}"
echo -e "Сертификат: ${YELLOW}server.crt${NC}"
echo -e "Приватный ключ: ${YELLOW}server.key${NC}"
echo -e "PEM файл: ${YELLOW}server.pem${NC}"
echo -e "Срок действия: ${YELLOW}$DAYS дней${NC}"
echo -e "IP адрес в сертификате: ${YELLOW}$SERVER_IP${NC}"

echo -e "\n${YELLOW}Информация о сертификате:${NC}"
openssl x509 -in "$CERT_DIR/server.crt" -text -noout | grep -A 1 "Subject:"
openssl x509 -in "$CERT_DIR/server.crt" -text -noout | grep -A 5 "Subject Alternative Name"
openssl x509 -in "$CERT_DIR/server.crt" -noout -dates

echo -e "\n${GREEN}Готово! Теперь можно запускать сервер с HTTPS${NC}"
echo -e "${YELLOW}Примечание: Браузеры будут показывать предупреждение о самоподписанном сертификате${NC}"
