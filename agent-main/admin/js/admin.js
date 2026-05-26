/**
 * 管理员系统主脚本
 */

// API基础URL
const API_BASE = '/api/admin';

// 获取认证令牌
function getAuthToken() {
    return localStorage.getItem('admin_token') || sessionStorage.getItem('admin_token');
}

// 通用API请求函数
async function apiRequest(endpoint, options = {}) {
    const token = getAuthToken();
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers
    };

    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    try {
        const response = await fetch(`${API_BASE}${endpoint}`, {
            ...options,
            headers
        });

        if (response.status === 401) {
            // Token过期或无效，跳转到登录页
            localStorage.removeItem('admin_token');
            sessionStorage.removeItem('admin_token');
            window.location.href = '/admin/login.html';
            return;
        }

        const data = await response.json();
        return data;
    } catch (error) {
        console.error('API请求失败:', error);
        throw error;
    }
}

// 显示/隐藏加载指示器
function showLoading() {
    document.getElementById('loadingOverlay').style.display = 'flex';
}

function hideLoading() {
    document.getElementById('loadingOverlay').style.display = 'none';
}

// 显示提示消息
function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('show');
    }, 10);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => {
            document.body.removeChild(toast);
        }, 300);
    }, 3000);
}

// 退出登录
function logout() {
    if (confirm('确定要退出登录吗？')) {
        localStorage.removeItem('admin_token');
        sessionStorage.removeItem('admin_token');
        window.location.href = '/admin/login.html';
    }
}

// 格式化日期
function formatDate(dateString) {
    if (!dateString) return '-';
    const date = new Date(dateString);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// 格式化数字（添加千位分隔符）
function formatNumber(num) {
    return num.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// 导出数据
async function exportData() {
    showLoading();
    try {
        // 导出用户列表
        const response = await apiRequest('/users?limit=100');
        if (response.success) {
            const data = response.data.users;

            // 转换为CSV
            const headers = ['用户ID', '用户名', '邮箱', '注册时间', '会话数'];
            const csvContent = [
                headers.join(','),
                ...data.map(user => [
                    user.user_id,
                    user.username,
                    user.email,
                    formatDate(user.created_at),
                    user.session_count
                ].join(','))
            ].join('\n');

            // 下载文件
            const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
            const link = document.createElement('a');
            const url = URL.createObjectURL(blob);
            link.setAttribute('href', url);
            link.setAttribute('download', `用户列表_${new Date().toISOString().split('T')[0]}.csv`);
            link.style.visibility = 'hidden';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            showToast('数据导出成功', 'success');
        }
    } catch (error) {
        showToast('数据导出失败: ' + error.message, 'error');
    } finally {
        hideLoading();
    }
}

// 同步数据
async function syncData() {
    if (!confirm('确定要从 JSON 文件同步数据到数据库吗？\n\n这可能需要几分钟时间，期间请不要关闭页面。')) {
        return;
    }

    // 创建同步进度弹窗
    const modal = document.createElement('div');
    modal.className = 'loading-overlay';
    modal.style.cssText = `
        display: flex;
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.7);
        justify-content: center;
        align-items: center;
        z-index: 9999;
    `;
    modal.innerHTML = `
        <div style="background: white; padding: 30px; border-radius: 8px; text-align: center; max-width: 500px;">
            <div class="spinner" style="margin: 0 auto 20px;"></div>
            <h3 style="margin: 0 0 15px; color: #2c3e50;">正在同步数据...</h3>
            <p style="margin: 0; color: #7f8c8d; font-size: 14px;">这可能需要几分钟，请耐心等待</p>
            <div id="syncProgress" style="margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 4px; max-height: 300px; overflow-y: auto; text-align: left; font-family: monospace; font-size: 12px;"></div>
        </div>
    `;
    document.body.appendChild(modal);

    try {
        const response = await apiRequest('/sync-data', {
            method: 'POST'
        });

        document.body.removeChild(modal);

        if (response.success) {
            showToast('数据同步成功！', 'success');

            // 显示同步结果
            const resultModal = document.createElement('div');
            resultModal.className = 'loading-overlay';
            resultModal.style.cssText = modal.style.cssText;
            resultModal.innerHTML = `
                <div style="background: white; padding: 30px; border-radius: 8px; text-align: center; max-width: 600px;">
                    <div style="width: 60px; height: 60px; margin: 0 auto 20px; background: #10b981; border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                        <i class="fas fa-check" style="color: white; font-size: 30px;"></i>
                    </div>
                    <h3 style="margin: 0 0 15px; color: #2c3e50;">同步完成！</h3>
                    <div style="text-align: left; background: #f8f9fa; padding: 15px; border-radius: 4px; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 12px; white-space: pre-wrap;">${response.output}</div>
                    <button onclick="this.closest('.loading-overlay').remove(); initDashboard();" style="margin-top: 20px; padding: 10px 30px; background: #3498db; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 14px;">确定</button>
                </div>
            `;
            document.body.appendChild(resultModal);

            // 刷新仪表板数据
            setTimeout(() => {
                if (document.getElementById('totalUsers')) {
                    initDashboard();
                }
            }, 1000);
        } else {
            showToast('同步失败: ' + response.message, 'error');
        }
    } catch (error) {
        if (document.body.contains(modal)) {
            document.body.removeChild(modal);
        }
        showToast('同步失败: ' + error.message, 'error');
    }
}

// 仪表板页面
async function initDashboard() {
    showLoading();
    try {
        const response = await apiRequest('/dashboard');
        if (response.success) {
            const stats = response.data;

            // 更新统计卡片
            document.getElementById('totalUsers').textContent = formatNumber(stats.users.total);
            document.getElementById('activeUsers24h').querySelector('span').textContent =
                formatNumber(stats.users.active_24h);

            document.getElementById('totalSessions').textContent = formatNumber(stats.sessions.total);
            document.getElementById('activeSessions').textContent = formatNumber(stats.sessions.active);
            document.getElementById('archivedSessions').textContent = formatNumber(stats.sessions.archived);

            document.getElementById('totalMessages').textContent = formatNumber(stats.messages.total);

            // 绘制趋势图表
            if (stats.trends && stats.trends.daily_sessions) {
                drawTrendChart(stats.trends.daily_sessions);
            }
        }
    } catch (error) {
        console.error('加载仪表板数据失败:', error);
        showToast('加载数据失败', 'error');
    } finally {
        hideLoading();
    }
}

// 绘制趋势图表
function drawTrendChart(data) {
    const ctx = document.getElementById('trendChart').getContext('2d');

    // 准备数据
    const labels = data.map(item => {
        const date = new Date(item.date);
        return `${date.getMonth() + 1}/${date.getDate()}`;
    }).reverse();
    const values = data.map(item => item.count).reverse();

    new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: '每日会话数',
                data: values,
                borderColor: '#3498db',
                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                fill: true,
                tension: 0.4,
                pointRadius: 6,
                pointHoverRadius: 8,
                pointBackgroundColor: '#3498db',
                pointBorderColor: '#fff',
                pointBorderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                },
                tooltip: {
                    backgroundColor: 'rgba(44, 62, 80, 0.9)',
                    padding: 12,
                    titleFont: {
                        size: 14,
                        weight: 'bold'
                    },
                    bodyFont: {
                        size: 13
                    },
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            return `会话数: ${context.parsed.y}`;
                        }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    grid: {
                        color: 'rgba(0, 0, 0, 0.05)'
                    },
                    ticks: {
                        stepSize: 1
                    }
                },
                x: {
                    grid: {
                        display: false
                    }
                }
            }
        }
    });
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', function() {
    // 检查是否在仪表板页面
    if (document.getElementById('totalUsers')) {
        initDashboard();
    }

    // 更新侧边栏高亮
    const currentPath = window.location.pathname;
    document.querySelectorAll('.sidebar-menu .menu-item').forEach(item => {
        const href = item.getAttribute('href');
        if (href && currentPath.includes(href)) {
            item.classList.add('active');
        } else {
            item.classList.remove('active');
        }
    });
});

// 自动刷新统计数据（每5分钟）
if (document.getElementById('totalUsers')) {
    setInterval(initDashboard, 5 * 60 * 1000);
}
