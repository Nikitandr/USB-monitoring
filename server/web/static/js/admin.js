// Admin Dashboard JavaScript Functions

// Global variables
let currentUser = null;
let pendingRequests = [];

// Initialize the application
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
});

function initializeApp() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    var tooltipList = tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Load initial data
    loadDashboardData();
    
    // Set up periodic refresh
    setInterval(loadDashboardData, 30000); // Refresh every 30 seconds
}

// API Helper Functions
function makeRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
        },
        credentials: 'same-origin'
    };
    
    const finalOptions = Object.assign({}, defaultOptions, options);
    
    return fetch(url, finalOptions)
        .then(response => {
            if (!response.ok) {
                throw new Error('Network response was not ok: ' + response.statusText);
            }
            return response.json();
        })
        .catch(error => {
            console.error('API request failed:', error);
            showNotification('API request failed: ' + error.message, 'error');
            throw error;
        });
}

// Dashboard Functions
function loadDashboardData() {
    if (window.location.pathname === '/dashboard') {
        loadStats();
        loadPendingRequests();
    }
}

function loadStats() {
    makeRequest('/api/stats')
        .then(data => {
            updateStatsCards(data);
        })
        .catch(error => {
            console.error('Failed to load stats:', error);
        });
}

function updateStatsCards(stats) {
    const elements = {
        totalUsers: document.getElementById('total-users'),
        totalDevices: document.getElementById('total-devices'),
        pendingRequests: document.getElementById('pending-requests'),
        todayRequests: document.getElementById('today-requests')
    };
    
    if (elements.totalUsers) elements.totalUsers.textContent = stats.total_users || 0;
    if (elements.totalDevices) elements.totalDevices.textContent = stats.total_devices || 0;
    if (elements.pendingRequests) elements.pendingRequests.textContent = stats.pending_requests || 0;
    if (elements.todayRequests) elements.todayRequests.textContent = stats.today_requests || 0;
}

function loadPendingRequests() {
    makeRequest('/api/requests?status=pending')
        .then(data => {
            pendingRequests = data.requests || [];
            updatePendingRequestsTable();
        })
        .catch(error => {
            console.error('Failed to load pending requests:', error);
        });
}

function updatePendingRequestsTable() {
    const tbody = document.getElementById('pending-requests-tbody');
    if (!tbody) return;
    
    if (pendingRequests.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No pending requests</td></tr>';
        return;
    }
    
    tbody.innerHTML = pendingRequests.map(request => {
        const requestTime = new Date(request.request_time).toLocaleString();
        return '<tr>' +
            '<td>' + escapeHtml(request.username) + '</td>' +
            '<td>' + escapeHtml(request.device_name || 'Unknown Device') + '</td>' +
            '<td><code>' + escapeHtml(request.device_id) + '</code></td>' +
            '<td>' + requestTime + '</td>' +
            '<td><span class="badge status-pending">Pending</span></td>' +
            '<td>' +
                '<button class="btn btn-approve btn-action" onclick="approveRequest(' + request.id + ')">' +
                    '<i class="fas fa-check"></i> Approve' +
                '</button>' +
                '<button class="btn btn-deny btn-action" onclick="denyRequest(' + request.id + ')">' +
                    '<i class="fas fa-times"></i> Deny' +
                '</button>' +
            '</td>' +
        '</tr>';
    }).join('');
}

// Request Management Functions
function approveRequest(requestId) {
    if (!confirm('Are you sure you want to approve this request?')) {
        return;
    }
    
    const button = event.target.closest('button');
    const originalContent = button.innerHTML;
    button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Approving...';
    button.disabled = true;
    
    makeRequest('/api/requests/' + requestId + '/approve', {
        method: 'POST'
    })
    .then(data => {
        showNotification('Request approved successfully', 'success');
        loadPendingRequests();
    })
    .catch(error => {
        button.innerHTML = originalContent;
        button.disabled = false;
        showNotification('Failed to approve request', 'error');
    });
}

function denyRequest(requestId) {
    if (!confirm('Are you sure you want to deny this request?')) {
        return;
    }
    
    const button = event.target.closest('button');
    const originalContent = button.innerHTML;
    button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status"></span> Denying...';
    button.disabled = true;
    
    makeRequest('/api/requests/' + requestId + '/deny', {
        method: 'POST'
    })
    .then(data => {
        showNotification('Request denied successfully', 'success');
        loadPendingRequests();
    })
    .catch(error => {
        button.innerHTML = originalContent;
        button.disabled = false;
        showNotification('Failed to deny request', 'error');
    });
}

// User Management Functions
function loadUsers() {
    makeRequest('/api/users')
        .then(data => {
            updateUsersTable(data.users || []);
        })
        .catch(error => {
            console.error('Failed to load users:', error);
        });
}

function updateUsersTable(users) {
    const tbody = document.getElementById('users-tbody');
    if (!tbody) return;
    
    if (users.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No users found</td></tr>';
        return;
    }
    
    tbody.innerHTML = users.map(user => {
        const createdDate = new Date(user.created_at).toLocaleDateString();
        return '<tr>' +
            '<td>' + escapeHtml(user.username) + '</td>' +
            '<td>' + escapeHtml(user.full_name || '') + '</td>' +
            '<td>' + (user.device_count || 0) + '</td>' +
            '<td>' + createdDate + '</td>' +
            '<td>' +
                '<button class="btn btn-primary btn-sm" onclick="viewUserDevices(\'' + user.username + '\')">' +
                    '<i class="fas fa-eye"></i> View Devices' +
                '</button>' +
                '<button class="btn btn-secondary btn-sm ms-1" onclick="editUser(\'' + user.username + '\')">' +
                    '<i class="fas fa-edit"></i> Edit' +
                '</button>' +
            '</td>' +
        '</tr>';
    }).join('');
}

function viewUserDevices(username) {
    currentUser = username;
    makeRequest('/api/users/' + encodeURIComponent(username) + '/devices')
        .then(data => {
            showUserDevicesModal(username, data.devices || []);
        })
        .catch(error => {
            showNotification('Failed to load user devices', 'error');
        });
}

function showUserDevicesModal(username, devices) {
    const modal = document.getElementById('userDevicesModal');
    const modalTitle = modal.querySelector('.modal-title');
    const devicesList = document.getElementById('userDevicesList');
    
    modalTitle.textContent = 'Devices for ' + username;
    
    if (devices.length === 0) {
        devicesList.innerHTML = '<div class="text-center text-muted p-3">No devices found for this user</div>';
    } else {
        devicesList.innerHTML = devices.map(device => {
            return '<div class="device-item">' +
                '<div class="device-info">' +
                    '<strong>' + escapeHtml(device.name || 'Unknown Device') + '</strong>' +
                    '<small>ID: ' + escapeHtml(device.device_id) + '</small>' +
                    '<small>Added: ' + new Date(device.created_at).toLocaleDateString() + '</small>' +
                '</div>' +
                '<button class="btn btn-danger btn-sm" onclick="removeUserDevice(\'' + device.device_id + '\')">' +
                    '<i class="fas fa-trash"></i>' +
                '</button>' +
            '</div>';
        }).join('');
    }
    
    const bootstrapModal = new bootstrap.Modal(modal);
    bootstrapModal.show();
}

function removeUserDevice(deviceId) {
    if (!confirm('Are you sure you want to remove this device from the user\'s whitelist?')) {
        return;
    }
    
    makeRequest('/api/users/' + encodeURIComponent(currentUser) + '/devices/' + encodeURIComponent(deviceId), {
        method: 'DELETE'
    })
    .then(data => {
        showNotification('Device removed successfully', 'success');
        viewUserDevices(currentUser); // Refresh the modal
    })
    .catch(error => {
        showNotification('Failed to remove device', 'error');
    });
}

function showAddDeviceModal() {
    const modal = document.getElementById('addDeviceModal');
    const form = document.getElementById('addDeviceForm');
    form.reset();
    
    const bootstrapModal = new bootstrap.Modal(modal);
    bootstrapModal.show();
}

function addDeviceToUser() {
    const form = document.getElementById('addDeviceForm');
    const formData = new FormData(form);
    
    const deviceData = {
        device_id: formData.get('deviceId'),
        name: formData.get('deviceName')
    };
    
    makeRequest('/api/users/' + encodeURIComponent(currentUser) + '/devices', {
        method: 'POST',
        body: JSON.stringify(deviceData)
    })
    .then(data => {
        showNotification('Device added successfully', 'success');
        bootstrap.Modal.getInstance(document.getElementById('addDeviceModal')).hide();
        viewUserDevices(currentUser); // Refresh the modal
    })
    .catch(error => {
        showNotification('Failed to add device', 'error');
    });
}

// Request History Functions
function loadRequestHistory() {
    const filters = getRequestFilters();
    const queryParams = new URLSearchParams(filters).toString();
    
    makeRequest('/api/requests?' + queryParams)
        .then(data => {
            updateRequestHistoryTable(data.requests || []);
        })
        .catch(error => {
            console.error('Failed to load request history:', error);
        });
}

function getRequestFilters() {
    const filters = {};
    
    const usernameFilter = document.getElementById('usernameFilter');
    const statusFilter = document.getElementById('statusFilter');
    const dateFromFilter = document.getElementById('dateFromFilter');
    const dateToFilter = document.getElementById('dateToFilter');
    
    if (usernameFilter && usernameFilter.value) filters.username = usernameFilter.value;
    if (statusFilter && statusFilter.value) filters.status = statusFilter.value;
    if (dateFromFilter && dateFromFilter.value) filters.date_from = dateFromFilter.value;
    if (dateToFilter && dateToFilter.value) filters.date_to = dateToFilter.value;
    
    return filters;
}

function updateRequestHistoryTable(requests) {
    const tbody = document.getElementById('requests-tbody');
    if (!tbody) return;
    
    if (requests.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">No requests found</td></tr>';
        return;
    }
    
    tbody.innerHTML = requests.map(request => {
        const requestTime = new Date(request.request_time).toLocaleString();
        const statusClass = 'status-' + request.status.toLowerCase();
        const statusText = request.status.charAt(0).toUpperCase() + request.status.slice(1);
        
        return '<tr>' +
            '<td>' + escapeHtml(request.username) + '</td>' +
            '<td>' + escapeHtml(request.device_name || 'Unknown Device') + '</td>' +
            '<td><code>' + escapeHtml(request.device_id) + '</code></td>' +
            '<td>' + requestTime + '</td>' +
            '<td><span class="badge ' + statusClass + '">' + statusText + '</span></td>' +
            '<td>' + escapeHtml(request.admin_username || '-') + '</td>' +
        '</tr>';
    }).join('');
}

function applyFilters() {
    loadRequestHistory();
}

function clearFilters() {
    const form = document.getElementById('filterForm');
    if (form) {
        form.reset();
        loadRequestHistory();
    }
}

function exportRequests() {
    const filters = getRequestFilters();
    const queryParams = new URLSearchParams(filters).toString();
    
    window.open('/api/requests/export?' + queryParams, '_blank');
}

// Utility Functions
function escapeHtml(text) {
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

function showNotification(message, type = 'info') {
    const container = document.getElementById('notification-container');
    if (!container) return;
    
    const alertClass = type === 'error' ? 'alert-danger' : 
                     type === 'success' ? 'alert-success' : 
                     type === 'warning' ? 'alert-warning' : 'alert-info';
    
    const notification = document.createElement('div');
    notification.className = 'alert ' + alertClass + ' alert-dismissible notification show';
    notification.innerHTML = 
        '<strong>' + (type === 'error' ? 'Error!' : type === 'success' ? 'Success!' : 'Info!') + '</strong> ' +
        escapeHtml(message) +
        '<button type="button" class="btn-close" data-bs-dismiss="alert"></button>';
    
    container.appendChild(notification);
    
    // Auto-remove after 5 seconds
    setTimeout(function() {
        if (notification.parentNode) {
            notification.classList.remove('show');
            notification.classList.add('hide');
            setTimeout(function() {
                if (notification.parentNode) {
                    notification.parentNode.removeChild(notification);
                }
            }, 300);
        }
    }, 5000);
}

// Page-specific initialization
if (window.location.pathname === '/users') {
    document.addEventListener('DOMContentLoaded', function() {
        loadUsers();
    });
}

if (window.location.pathname === '/requests') {
    document.addEventListener('DOMContentLoaded', function() {
        loadRequestHistory();
    });
}
