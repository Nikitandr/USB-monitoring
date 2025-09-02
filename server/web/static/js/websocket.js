// Socket.IO Client for Real-time Notifications

class SocketIOClient {
    constructor() {
        this.socket = null;
        this.isConnected = false;
        this.messageHandlers = new Map();
        
        this.init();
    }
    
    init() {
        this.connect();
        this.setupConnectionStatusIndicator();
    }
    
    connect() {
        try {
            // Use Socket.IO client library (should be loaded from CDN)
            if (typeof io === 'undefined') {
                console.error('Socket.IO client library not loaded');
                this.updateConnectionStatus(false);
                return;
            }
            
            console.log('Connecting to Socket.IO server...');
            this.socket = io();
            
            this.socket.on('connect', this.onConnect.bind(this));
            this.socket.on('disconnect', this.onDisconnect.bind(this));
            this.socket.on('connect_error', this.onError.bind(this));
            
            // Listen for custom events
            this.socket.on('device_request', this.handleDeviceRequest.bind(this));
            this.socket.on('request_approved', this.handleRequestApproved.bind(this));
            this.socket.on('request_denied', this.handleRequestDenied.bind(this));
            
        } catch (error) {
            console.error('Failed to create Socket.IO connection:', error);
            this.updateConnectionStatus(false);
        }
    }
    
    onConnect() {
        console.log('Socket.IO connected');
        this.isConnected = true;
        this.updateConnectionStatus(true);
        
        // Join admin room if we're on admin pages
        if (this.isAdminPage()) {
            this.socket.emit('join_admin');
            console.log('Joined admin room');
        }
    }
    
    onDisconnect(reason) {
        console.log('Socket.IO disconnected:', reason);
        this.isConnected = false;
        this.updateConnectionStatus(false);
    }
    
    onError(error) {
        console.error('Socket.IO error:', error);
        this.updateConnectionStatus(false);
    }
    
    isAdminPage() {
        const path = window.location.pathname;
        return path.includes('/admin/') || path === '/';
    }
    
    handleDeviceRequest(data) {
        console.log('New device request:', data);
        
        // Show notification
        this.showNotification(
            `New USB request from ${data.username} for device: ${data.name || data.vid + ':' + data.pid}`,
            'info',
            true // persistent
        );
        
        // Update dashboard if we're on the dashboard page
        if (window.location.pathname.includes('/dashboard')) {
            this.refreshDashboard();
        }
        
        // Play notification sound
        this.playNotificationSound();
    }
    
    handleRequestApproved(data) {
        console.log('Request approved:', data);
        
        this.showNotification(
            `Request from ${data.username} has been approved`,
            'success'
        );
        
        this.refreshPages();
    }
    
    handleRequestDenied(data) {
        console.log('Request denied:', data);
        
        this.showNotification(
            `Request from ${data.username} has been denied`,
            'warning'
        );
        
        this.refreshPages();
    }
    
    refreshDashboard() {
        // Reload dashboard statistics and pending requests
        if (typeof loadStats === 'function') {
            loadStats();
        }
        if (typeof loadPendingRequests === 'function') {
            loadPendingRequests();
        }
        
        // If no specific functions available, reload the page
        setTimeout(() => {
            if (window.location.pathname.includes('/dashboard')) {
                window.location.reload();
            }
        }, 1000);
    }
    
    refreshPages() {
        // Update relevant pages
        if (window.location.pathname.includes('/dashboard')) {
            this.refreshDashboard();
        }
        
        if (window.location.pathname.includes('/requests')) {
            if (typeof loadRequestHistory === 'function') {
                loadRequestHistory();
            } else {
                setTimeout(() => window.location.reload(), 1000);
            }
        }
    }
    
    showNotification(message, type = 'info', persistent = false) {
        // Use Bootstrap toast if available
        if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            this.showBootstrapToast(message, type);
            return;
        }
        
        // Fallback notification implementation
        const container = this.getNotificationContainer();
        if (!container) return;
        
        const alertClass = type === 'error' ? 'alert-danger' : 
                         type === 'success' ? 'alert-success' : 
                         type === 'warning' ? 'alert-warning' : 'alert-info';
        
        const notification = document.createElement('div');
        notification.className = `alert ${alertClass} alert-dismissible fade show`;
        notification.innerHTML = 
            `<strong>Notification:</strong> ${this.escapeHtml(message)}
             <button type="button" class="btn-close" data-bs-dismiss="alert"></button>`;
        
        container.appendChild(notification);
        
        // Auto-remove after delay unless persistent
        if (!persistent) {
            setTimeout(() => {
                if (notification.parentNode) {
                    notification.classList.remove('show');
                    setTimeout(() => {
                        if (notification.parentNode) {
                            notification.parentNode.removeChild(notification);
                        }
                    }, 300);
                }
            }, 5000);
        }
    }
    
    showBootstrapToast(message, type = 'info') {
        // Create toast container if it doesn't exist
        let toastContainer = document.getElementById('toast-container');
        if (!toastContainer) {
            toastContainer = document.createElement('div');
            toastContainer.id = 'toast-container';
            toastContainer.className = 'toast-container position-fixed top-0 end-0 p-3';
            toastContainer.style.zIndex = '1055';
            document.body.appendChild(toastContainer);
        }
        
        const toastId = 'toast-' + Date.now();
        const bgClass = type === 'error' ? 'bg-danger' : 
                       type === 'success' ? 'bg-success' : 
                       type === 'warning' ? 'bg-warning' : 'bg-info';
        
        const toastHtml = `
            <div id="${toastId}" class="toast ${bgClass} text-white" role="alert">
                <div class="toast-header ${bgClass} text-white">
                    <strong class="me-auto">USB Monitor</strong>
                    <small>now</small>
                    <button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button>
                </div>
                <div class="toast-body">
                    ${this.escapeHtml(message)}
                </div>
            </div>
        `;
        
        toastContainer.insertAdjacentHTML('beforeend', toastHtml);
        
        const toastElement = document.getElementById(toastId);
        const toast = new bootstrap.Toast(toastElement);
        toast.show();
        
        // Remove from DOM after it's hidden
        toastElement.addEventListener('hidden.bs.toast', () => {
            toastElement.remove();
        });
    }
    
    getNotificationContainer() {
        let container = document.getElementById('notification-container');
        if (!container) {
            container = document.createElement('div');
            container.id = 'notification-container';
            container.className = 'position-fixed top-0 end-0 p-3';
            container.style.zIndex = '1050';
            document.body.appendChild(container);
        }
        return container;
    }
    
    playNotificationSound() {
        try {
            // Create a simple notification sound
            const audioContext = new (window.AudioContext || window.webkitAudioContext)();
            const oscillator = audioContext.createOscillator();
            const gainNode = audioContext.createGain();
            
            oscillator.connect(gainNode);
            gainNode.connect(audioContext.destination);
            
            oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
            oscillator.frequency.setValueAtTime(600, audioContext.currentTime + 0.1);
            
            gainNode.gain.setValueAtTime(0.3, audioContext.currentTime);
            gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.2);
            
            oscillator.start(audioContext.currentTime);
            oscillator.stop(audioContext.currentTime + 0.2);
        } catch (error) {
            console.log('Could not play notification sound:', error);
        }
    }
    
    setupConnectionStatusIndicator() {
        // Create connection status indicator in the bottom right
        let statusContainer = document.getElementById('connection-status');
        if (!statusContainer) {
            statusContainer = document.createElement('div');
            statusContainer.id = 'connection-status';
            statusContainer.className = 'position-fixed bottom-0 end-0 p-3';
            statusContainer.style.zIndex = '1040';
            statusContainer.innerHTML = `
                <div class="card shadow-sm" style="min-width: 150px;">
                    <div class="card-body p-2">
                        <small class="d-flex align-items-center">
                            <span class="status-indicator me-2"></span>
                            <span id="connection-text">Connecting...</span>
                        </small>
                    </div>
                </div>
            `;
            document.body.appendChild(statusContainer);
            
            // Add CSS for status indicator
            const style = document.createElement('style');
            style.textContent = `
                .status-indicator {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    display: inline-block;
                }
                .status-connected {
                    background-color: #28a745;
                    box-shadow: 0 0 5px #28a745;
                }
                .status-disconnected {
                    background-color: #dc3545;
                    box-shadow: 0 0 5px #dc3545;
                }
            `;
            document.head.appendChild(style);
        }
    }
    
    updateConnectionStatus(connected) {
        const indicator = document.querySelector('.status-indicator');
        const text = document.getElementById('connection-text');
        
        if (indicator && text) {
            if (connected) {
                indicator.className = 'status-indicator status-connected me-2';
                text.textContent = 'Connected';
            } else {
                indicator.className = 'status-indicator status-disconnected me-2';
                text.textContent = 'Disconnected';
            }
        }
    }
    
    // Utility function
    escapeHtml(text) {
        if (typeof text !== 'string') return text;
        const map = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#039;'
        };
        return text.replace(/[&<>"']/g, function(m) { return map[m]; });
    }
    
    // Public methods
    disconnect() {
        if (this.socket) {
            this.socket.disconnect();
        }
    }
    
    reconnect() {
        if (this.socket) {
            this.socket.connect();
        }
    }
    
    getConnectionState() {
        return {
            connected: this.isConnected,
            socketId: this.socket ? this.socket.id : null
        };
    }
    
    // Event handler registration
    on(eventType, handler) {
        if (this.socket) {
            this.socket.on(eventType, handler);
        }
    }
    
    off(eventType, handler) {
        if (this.socket) {
            this.socket.off(eventType, handler);
        }
    }
    
    emit(eventType, data) {
        if (this.socket && this.isConnected) {
            this.socket.emit(eventType, data);
        }
    }
}

// Global Socket.IO instance
let socketClient = null;

// Initialize Socket.IO when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize Socket.IO for admin pages (not login page)
    if (!window.location.pathname.includes('/login')) {
        // Wait a bit for Socket.IO library to load
        setTimeout(() => {
            socketClient = new SocketIOClient();
            
            // Make it globally available
            window.socketClient = socketClient;
        }, 100);
    }
});

// Handle page visibility changes
document.addEventListener('visibilitychange', function() {
    if (socketClient) {
        if (document.hidden) {
            console.log('Page hidden, Socket.IO connection maintained');
        } else {
            console.log('Page visible, checking Socket.IO connection');
            if (!socketClient.isConnected) {
                socketClient.reconnect();
            }
        }
    }
});

// Handle beforeunload to clean up connection
window.addEventListener('beforeunload', function() {
    if (socketClient) {
        socketClient.disconnect();
    }
});
