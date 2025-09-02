#!/usr/bin/env python3
"""
Основное приложение USB Monitor Server
"""

import os
import sys
import ssl
from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
from flask_cors import CORS

# Добавляем текущую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import config
from database.database import init_database, get_database
from utils.logger import setup_logger, log_admin_action, log_request, log_system_event, log_error

# Глобальные переменные
app = None
socketio = None
db = None
logger = None

def create_app(config_name='default'):
    """Фабрика приложений Flask"""
    global app, socketio, db, logger
    
    # Получаем путь к директории сервера
    server_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Создаем приложение Flask с правильными путями
    app = Flask(__name__,
                template_folder=os.path.join(server_dir, 'web', 'templates'),
                static_folder=os.path.join(server_dir, 'web', 'static'))
    
    # Загружаем конфигурацию
    app_config = config.get(config_name, config['default'])
    app.config.from_object(app_config)
    
    # Настраиваем CORS
    CORS(app, origins="*")
    
    # Настраиваем SocketIO
    socketio = SocketIO(
        app, 
        cors_allowed_origins="*",
        async_mode=app_config.SOCKETIO_ASYNC_MODE
    )
    
    # Настраиваем логирование
    logger = setup_logger(
        'usb_monitor',
        app_config.LOG_FILE,
        app_config.LOG_LEVEL
    )
    
    # Инициализируем базу данных
    try:
        db = init_database(app_config.DATABASE_PATH)
        logger.info("База данных успешно инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации базы данных: {e}")
        sys.exit(1)
    
    # Регистрируем маршруты
    register_routes()
    register_socketio_events()
    
    logger.info("Приложение USB Monitor Server запущено")
    return app

def register_routes():
    """Регистрация HTTP маршрутов"""
    
    # Главная страница - редирект на админку
    @app.route('/')
    def index():
        return redirect(url_for('admin_login'))
    
    # Страница входа администратора
    @app.route('/admin/login', methods=['GET', 'POST'])
    def admin_login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            if (username == app.config['ADMIN_USERNAME'] and 
                password == app.config['ADMIN_PASSWORD']):
                session['admin_logged_in'] = True
                log_admin_action("login", f"Admin logged in from {request.remote_addr}")
                return redirect(url_for('admin_dashboard'))
            else:
                log_admin_action("login_failed", f"Failed login attempt from {request.remote_addr}")
                return render_template('login.html', error="Неверные учетные данные")
        
        return render_template('login.html')
    
    # Выход администратора
    @app.route('/admin/logout')
    def admin_logout():
        session.pop('admin_logged_in', None)
        log_admin_action("logout", "Admin logged out")
        return redirect(url_for('admin_login'))
    
    # Проверка авторизации администратора
    def require_admin():
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login'))
        return None
    
    # Панель администратора
    @app.route('/admin/dashboard')
    def admin_dashboard():
        auth_check = require_admin()
        if auth_check:
            return auth_check
        
        try:
            stats = db.get_stats()
            pending_requests = db.request.get_pending()
            return render_template('dashboard.html', stats=stats, requests=pending_requests)
        except Exception as e:
            log_error(e, "Error loading admin dashboard")
            return "Ошибка загрузки панели администратора", 500
    
    # Управление пользователями
    @app.route('/admin/users')
    def admin_users():
        auth_check = require_admin()
        if auth_check:
            return auth_check
        
        try:
            users = db.user.get_all()
            return render_template('users.html', users=users)
        except Exception as e:
            log_error(e, "Error loading users page")
            return "Ошибка загрузки страницы пользователей", 500
    
    # История запросов
    @app.route('/admin/requests')
    def admin_requests():
        auth_check = require_admin()
        if auth_check:
            return auth_check
        
        try:
            requests = db.request.get_all(limit=100)
            return render_template('requests.html', requests=requests)
        except Exception as e:
            log_error(e, "Error loading requests page")
            return "Ошибка загрузки страницы запросов", 500
    
    # API для проверки разрешений устройства
    @app.route('/api/devices/check', methods=['POST'])
    def check_device():
        try:
            data = request.get_json()
            username = data.get('username')
            vid = data.get('vid')
            pid = data.get('pid')
            serial = data.get('serial', '')
            
            if not all([username, vid, pid]):
                return jsonify({'error': 'Недостаточно данных'}), 400
            
            # Получаем или создаем пользователя
            user = db.user.get_or_create(username)
            
            # Получаем или создаем устройство
            device = db.device.get_or_create(vid, pid, serial)
            
            # Проверяем разрешение
            permission = db.permission.check_permission(user['id'], device['id'])
            
            if permission is True:
                log_request(username, "device_check", f"{vid}:{pid}:{serial}", "allowed")
                return jsonify({'status': 'allowed'})
            elif permission is False:
                log_request(username, "device_check", f"{vid}:{pid}:{serial}", "denied")
                return jsonify({'status': 'denied'})
            else:
                log_request(username, "device_check", f"{vid}:{pid}:{serial}", "unknown")
                return jsonify({'status': 'unknown'})
                
        except Exception as e:
            log_error(e, "Error checking device permission")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для создания запроса на разрешение
    @app.route('/api/requests', methods=['POST'])
    def create_request():
        try:
            data = request.get_json()
            username = data.get('username')
            vid = data.get('vid')
            pid = data.get('pid')
            serial = data.get('serial', '')
            device_info = data.get('device_info', '')
            
            if not all([username, vid, pid]):
                return jsonify({'error': 'Недостаточно данных'}), 400
            
            # Получаем или создаем пользователя и устройство
            user = db.user.get_or_create(username)
            device = db.device.get_or_create(vid, pid, serial)
            
            # Проверяем, нет ли уже ожидающего запроса
            existing_request = db.request.check_existing(user['id'], device['id'])
            if existing_request:
                return jsonify({'request_id': existing_request['id'], 'status': 'pending'})
            
            # Создаем новый запрос
            request_id = db.request.create(user['id'], device['id'], device_info)
            
            # Отправляем уведомление администратору через WebSocket
            request_data = db.request.get_by_id(request_id)
            socketio.emit('device_request', request_data, room='admin')
            
            log_request(username, "request_created", f"{vid}:{pid}:{serial}", "pending")
            
            return jsonify({'request_id': request_id, 'status': 'pending'})
            
        except Exception as e:
            log_error(e, "Error creating device request")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для одобрения запроса
    @app.route('/api/requests/<int:request_id>/approve', methods=['POST'])
    def approve_request(request_id):
        auth_check = require_admin()
        if auth_check:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        try:
            # Получаем запрос
            req = db.request.get_by_id(request_id)
            if not req:
                return jsonify({'error': 'Запрос не найден'}), 404
            
            # Одобряем запрос
            db.request.approve(request_id)
            
            # Создаем разрешение
            db.permission.set_permission(req['user_id'], req['device_id'], True)
            
            # Уведомляем клиента
            socketio.emit('request_approved', {
                'request_id': request_id,
                'username': req['username']
            }, room=f"user_{req['username']}")
            
            log_admin_action("approve_request", f"Request {request_id} approved for {req['username']}")
            
            return jsonify({'status': 'approved'})
            
        except Exception as e:
            log_error(e, f"Error approving request {request_id}")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для отклонения запроса
    @app.route('/api/requests/<int:request_id>/deny', methods=['POST'])
    def deny_request(request_id):
        auth_check = require_admin()
        if auth_check:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        try:
            # Получаем запрос
            req = db.request.get_by_id(request_id)
            if not req:
                return jsonify({'error': 'Запрос не найден'}), 404
            
            # Отклоняем запрос
            db.request.deny(request_id)
            
            # Уведомляем клиента
            socketio.emit('request_denied', {
                'request_id': request_id,
                'username': req['username']
            }, room=f"user_{req['username']}")
            
            log_admin_action("deny_request", f"Request {request_id} denied for {req['username']}")
            
            return jsonify({'status': 'denied'})
            
        except Exception as e:
            log_error(e, f"Error denying request {request_id}")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для получения статистики
    @app.route('/api/stats')
    def get_stats():
        auth_check = require_admin()
        if auth_check:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        try:
            stats = db.get_stats()
            return jsonify(stats)
        except Exception as e:
            log_error(e, "Error getting stats")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для получения списка запросов
    @app.route('/api/requests')
    def get_requests():
        auth_check = require_admin()
        if auth_check:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        try:
            status = request.args.get('status')
            username = request.args.get('username')
            date_from = request.args.get('date_from')
            date_to = request.args.get('date_to')
            limit = int(request.args.get('limit', 100))
            
            requests = db.request.get_filtered(
                status=status,
                username=username,
                date_from=date_from,
                date_to=date_to,
                limit=limit
            )
            
            return jsonify({'requests': requests})
        except Exception as e:
            log_error(e, "Error getting requests")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для получения списка пользователей
    @app.route('/api/users')
    def get_users():
        auth_check = require_admin()
        if auth_check:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        try:
            users = db.user.get_all_with_device_count()
            return jsonify({'users': users})
        except Exception as e:
            log_error(e, "Error getting users")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для получения устройств пользователя
    @app.route('/api/users/<username>/devices')
    def get_user_devices(username):
        auth_check = require_admin()
        if auth_check:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        try:
            user = db.user.get_by_username(username)
            if not user:
                return jsonify({'error': 'Пользователь не найден'}), 404
            
            devices = db.permission.get_user_devices(user['id'])
            return jsonify({'devices': devices})
        except Exception as e:
            log_error(e, f"Error getting devices for user {username}")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для добавления устройства пользователю
    @app.route('/api/users/<username>/devices', methods=['POST'])
    def add_user_device(username):
        auth_check = require_admin()
        if auth_check:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        try:
            data = request.get_json()
            device_id = data.get('device_id')
            device_name = data.get('name', '')
            
            if not device_id:
                return jsonify({'error': 'Не указан ID устройства'}), 400
            
            user = db.user.get_by_username(username)
            if not user:
                return jsonify({'error': 'Пользователь не найден'}), 404
            
            # Парсим device_id (формат: VID:PID:SERIAL)
            parts = device_id.split(':')
            if len(parts) < 2:
                return jsonify({'error': 'Неверный формат ID устройства'}), 400
            
            vid = parts[0]
            pid = parts[1]
            serial = parts[2] if len(parts) > 2 else ''
            
            # Создаем или получаем устройство
            device = db.device.get_or_create(vid, pid, serial, device_name)
            
            # Добавляем разрешение
            db.permission.set_permission(user['id'], device['id'], True)
            
            log_admin_action("add_device", f"Device {device_id} added to user {username}")
            
            return jsonify({'status': 'success'})
            
        except Exception as e:
            log_error(e, f"Error adding device to user {username}")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для удаления устройства у пользователя
    @app.route('/api/users/<username>/devices/<device_id>', methods=['DELETE'])
    def remove_user_device(username, device_id):
        auth_check = require_admin()
        if auth_check:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        try:
            user = db.user.get_by_username(username)
            if not user:
                return jsonify({'error': 'Пользователь не найден'}), 404
            
            # Парсим device_id
            parts = device_id.split(':')
            if len(parts) < 2:
                return jsonify({'error': 'Неверный формат ID устройства'}), 400
            
            vid = parts[0]
            pid = parts[1]
            serial = parts[2] if len(parts) > 2 else ''
            
            device = db.device.get_by_identifiers(vid, pid, serial)
            if not device:
                return jsonify({'error': 'Устройство не найдено'}), 404
            
            # Удаляем разрешение
            db.permission.remove_permission(user['id'], device['id'])
            
            log_admin_action("remove_device", f"Device {device_id} removed from user {username}")
            
            return jsonify({'status': 'success'})
            
        except Exception as e:
            log_error(e, f"Error removing device from user {username}")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500
    
    # API для экспорта запросов
    @app.route('/api/requests/export')
    def export_requests():
        auth_check = require_admin()
        if auth_check:
            return jsonify({'error': 'Требуется авторизация'}), 401
        
        try:
            from flask import make_response
            import csv
            from io import StringIO
            
            status = request.args.get('status')
            username = request.args.get('username')
            date_from = request.args.get('date_from')
            date_to = request.args.get('date_to')
            
            requests = db.request.get_filtered(
                status=status,
                username=username,
                date_from=date_from,
                date_to=date_to,
                limit=None
            )
            
            # Создаем CSV
            output = StringIO()
            writer = csv.writer(output)
            
            # Заголовки
            writer.writerow(['Username', 'Device Name', 'Device ID', 'Request Time', 'Status', 'Admin'])
            
            # Данные
            for req in requests:
                writer.writerow([
                    req.get('username', ''),
                    req.get('device_name', ''),
                    req.get('device_id', ''),
                    req.get('request_time', ''),
                    req.get('status', ''),
                    req.get('admin_username', '')
                ])
            
            output.seek(0)
            
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = 'attachment; filename=usb_requests.csv'
            
            return response
            
        except Exception as e:
            log_error(e, "Error exporting requests")
            return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

def register_socketio_events():
    """Регистрация WebSocket событий"""
    
    @socketio.on('connect')
    def handle_connect():
        logger.info(f"WebSocket connection from {request.remote_addr}")
    
    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info(f"WebSocket disconnection from {request.remote_addr}")
    
    @socketio.on('join_admin')
    def handle_join_admin():
        if session.get('admin_logged_in'):
            join_room('admin')
            logger.info("Admin joined WebSocket room")
    
    @socketio.on('join_user')
    def handle_join_user(data):
        username = data.get('username')
        if username:
            join_room(f"user_{username}")
            logger.info(f"User {username} joined WebSocket room")

def create_ssl_context():
    """Создание SSL контекста для HTTPS"""
    cert_path = app.config.get('SSL_CERT_PATH')
    key_path = app.config.get('SSL_KEY_PATH')
    
    # Проверяем наличие сертификатов
    if not os.path.exists(cert_path):
        logger.error(f"SSL сертификат не найден: {cert_path}")
        logger.error("Запустите: bash scripts/ssl/generate_certs.sh")
        sys.exit(1)
    
    if not os.path.exists(key_path):
        logger.error(f"SSL ключ не найден: {key_path}")
        logger.error("Запустите: bash scripts/ssl/generate_certs.sh")
        sys.exit(1)
    
    try:
        # Создаем SSL контекст
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(cert_path, key_path)
        
        # Настройки безопасности
        context.set_ciphers('ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20:!aNULL:!MD5:!DSS')
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.maximum_version = ssl.TLSVersion.TLSv1_3
        
        logger.info(f"SSL контекст создан успешно")
        logger.info(f"Сертификат: {cert_path}")
        logger.info(f"Ключ: {key_path}")
        
        return context
        
    except Exception as e:
        logger.error(f"Ошибка создания SSL контекста: {e}")
        sys.exit(1)

def main():
    """Основная функция запуска сервера"""
    # Получаем конфигурацию из переменных окружения
    config_name = os.environ.get('FLASK_ENV', 'development')
    
    # Создаем приложение
    app = create_app(config_name)
    
    # Настройки сервера
    host = app.config.get('HOST', '0.0.0.0')
    port = app.config.get('PORT', 443)
    debug = app.config.get('DEBUG', False)
    
    # Создаем SSL контекст (обязательно для безопасности)
    ssl_context = create_ssl_context()
    
    logger.info(f"🔒 Запуск HTTPS сервера на {host}:{port} (debug={debug})")
    logger.info("⚠️  HTTP отключен для безопасности - только HTTPS!")
    
    # Запускаем только HTTPS сервер
    socketio.run(app, host=host, port=port, debug=debug, ssl_context=ssl_context, allow_unsafe_werkzeug=True)

if __name__ == '__main__':
    main()
