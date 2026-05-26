/**
 * 用户认证和菜单管理
 * 处理登录状态、用户菜单、个人资料等功能
 * 使用命名空间避免全局变量冲突
 */

// ==================== 命名空间 ====================
(function() {
    'use strict';

    // 创建 UserAuth 命名空间
    window.UserAuth = window.UserAuth || {};

    // 私有变量
    const API_BASE_URL = window.location.origin;
    let currentUser = null;
    let isAuthenticated = false;

    // ==================== 初始化 ====================

    /**
     * 页面加载时初始化用户状态
     * @param {boolean} requireLogin - 是否需要登录才能访问页面（默认false）
     */
    async function initializeUserAuth(requireLogin = false) {
        console.log('[user-auth.js] 初始化用户认证系统，requireLogin=', requireLogin);
        await checkLoginStatus();

        // 如果需要登录但用户未登录，跳转到登录页面
        if (requireLogin && !isAuthenticated) {
            console.warn('[user-auth.js] 页面需要登录，但用户未登录，跳转到登录页面');
            const currentPath = window.location.pathname;
            sessionStorage.setItem('redirect_after_login', currentPath);
            window.location.href = '/auth.html';
            return;
        }

        setupClickOutsideHandler();
    }

    // 立即初始化（默认不需要登录）
    console.log('[user-auth.js] 文件已加载');
    initializeUserAuth(false);

    /**
     * 检查登录状态
     */
    async function checkLoginStatus() {
        const token = localStorage.getItem('access_token');

        if (!token) {
            // 未登录
            setLoggedOutState();
            return;
        }

        // 验证token并获取用户信息
        try {
            const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.ok) {
                const user = await response.json();
                setLoggedInState(user);
            } else {
                // Token无效，清除本地存储
                localStorage.removeItem('access_token');
                localStorage.removeItem('user_info');
                setLoggedOutState();
            }
        } catch (error) {
            console.error('检查登录状态失败:', error);
            setLoggedOutState();
        }
    }

    /**
     * 设置已登录状态
     */
    function setLoggedInState(user) {
        currentUser = user;
        isAuthenticated = true;

        // 更新头像按钮
        const avatarBtn = document.getElementById('avatarBtn');
        if (avatarBtn) {
            if (user.avatar_url) {
                // 使用用户头像
                avatarBtn.innerHTML = `<img src="${user.avatar_url}" class="user-avatar-img" alt="用户头像">`;
            } else {
                // 使用默认头像（首字母）
                const initial = user.username ? user.username.charAt(0).toUpperCase() : 'U';
                avatarBtn.innerHTML = `<span style="font-size: 18px; font-weight: bold;">${initial}</span>`;
            }
            avatarBtn.title = `${user.nickname || user.username}`;
        }

        // 保存用户信息到localStorage
        localStorage.setItem('user_info', JSON.stringify(user));
    }

    /**
     * 设置未登录状态
     */
    function setLoggedOutState() {
        currentUser = null;
        isAuthenticated = false;

        // 重置头像按钮为默认图标
        const avatarBtn = document.getElementById('avatarBtn');
        if (avatarBtn) {
            avatarBtn.innerHTML = '<i class="fas fa-user-circle"></i>';
            avatarBtn.title = '点击登录';
        }

        // 清除用户信息
        localStorage.removeItem('user_info');
    }

    /**
     * 设置点击外部关闭下拉菜单的处理器
     */
    function setupClickOutsideHandler() {
        document.addEventListener('click', function(event) {
            const dropdown = document.getElementById('dropdownMenu');
            const avatarBtn = document.getElementById('avatarBtn');

            // 如果点击的不是下拉菜单或头像按钮，关闭菜单
            if (dropdown && !dropdown.classList.contains('show')) return;

            const userMenu = document.getElementById('userMenu');
            if (userMenu && !userMenu.contains(event.target)) {
                closeDropdown();
            }
        });
    }

    // ==================== 下拉菜单控制 ====================

    /**
     * 处理头像点击事件
     */
    function handleAvatarClick() {
        console.log('[user-auth.js] handleAvatarClick 被调用');
        console.log('[user-auth.js] isAuthenticated:', isAuthenticated);

        if (isAuthenticated) {
            // 已登录，切换下拉菜单
            console.log('[user-auth.js] 用户已登录，切换下拉菜单');
            toggleDropdown();
        } else {
            // 未登录，显示登录提示
            console.log('[user-auth.js] 用户未登录，显示登录提示');
            showLoginPrompt();
        }
    }

    /**
     * 切换下拉菜单显示状态
     */
    function toggleDropdown() {
        const dropdown = document.getElementById('dropdownMenu');
        if (dropdown) {
            dropdown.classList.toggle('show');
        }
    }

    /**
     * 关闭下拉菜单
     */
    function closeDropdown() {
        const dropdown = document.getElementById('dropdownMenu');
        if (dropdown) {
            dropdown.classList.remove('show');
        }
    }

    // ==================== 登录提示弹窗 ====================

    /**
     * 显示登录提示弹窗
     */
    function showLoginPrompt() {
        const modal = document.getElementById('loginPromptModal');
        if (modal) {
            modal.classList.add('show');
        }
    }

    /**
     * 关闭登录提示弹窗
     */
    function closeLoginPrompt() {
        const modal = document.getElementById('loginPromptModal');
        if (modal) {
            modal.classList.remove('show');
        }
    }

    /**
     * 跳转到登录页面
     */
    function goToLogin() {
        closeLoginPrompt();
        window.location.href = '/auth.html';
    }

    // ==================== 退出登录 ====================

    /**
     * 处理退出登录点击事件
     */
    function handleLogout(event) {
        event.preventDefault();
        closeDropdown();

        if (isAuthenticated) {
            showConfirmModal();
        } else {
            showLoginPrompt();
        }
    }

    /**
     * 显示退出确认对话框
     */
    function showConfirmModal() {
        const modal = document.getElementById('confirmModal');
        if (modal) {
            modal.classList.add('show');
        }
    }

    /**
     * 关闭退出确认对话框
     */
    function closeConfirmModal() {
        const modal = document.getElementById('confirmModal');
        if (modal) {
            modal.classList.remove('show');
        }
    }

    /**
     * 确认退出登录
     */
    function confirmLogout() {
        // 清除本地存储
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_info');

        // 关闭对话框
        closeConfirmModal();

        // 跳转到登录页
        window.location.href = '/auth.html';
    }

    // ==================== 导航到个人资料 ====================

    /**
     * 导航到个人资料页面（带登录检查）
     */
    function navigateToProfile(event) {
        event.preventDefault();
        closeDropdown();

        if (isAuthenticated) {
            // 已登录，跳转到个人资料页面
            window.location.href = '/profile.html';
        } else {
            // 未登录，显示登录提示
            showLoginPrompt();
        }
    }

    // ==================== 工具函数 ====================

    /**
     * 显示通知消息
     */
    function showNotification(message, type = 'info') {
        const colors = {
            'success': '#10B981',
            'warning': '#F59E0B',
            'error': '#EF4444',
            'info': '#3B82F6'
        };
        console.log(`[${type.toUpperCase()}] ${message}`);

        // 如果页面已有 main.js 的 showNotificationMessage，使用它
        if (typeof showNotificationMessage === 'function') {
            showNotificationMessage(message, type);
            return;
        }

        // 否则使用简单的 alert（临时方案）
        // 仅在开发环境使用，生产环境会被上面的 showNotificationMessage 替代
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            // 开发环境：在控制台显示
            console.debug(`Notification: ${message} (${type})`);
        }
    }

    // ==================== 密码重置功能 ====================

    /**
     * 打开重置密码弹窗
     */
    function openResetPasswordModal() {
        const modal = document.getElementById('resetPasswordModal');
        if (modal) {
            modal.classList.add('show');
            // 清空表单
            document.getElementById('resetPasswordForm').reset();
        }
    }

    /**
     * 关闭重置密码弹窗
     */
    function closeResetPasswordModal() {
        const modal = document.getElementById('resetPasswordModal');
        if (modal) {
            modal.classList.remove('show');
        }
    }

    /**
     * 处理密码重置表单提交
     */
    async function handleResetPassword(event) {
        event.preventDefault();

        const form = event.target;
        const identifier = form.identifier.value.trim();
        const newPassword = form.new_password.value;
        const confirmPassword = form.confirm_password.value;

        // 验证密码
        if (newPassword !== confirmPassword) {
            showNotification('两次输入的密码不一致', 'error');
            return;
        }

        if (newPassword.length < 6) {
            showNotification('密码长度至少为6位', 'error');
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/api/auth/reset-password`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    identifier: identifier,
                    new_password: newPassword
                })
            });

            const data = await response.json();

            if (data.success) {
                showNotification('密码重置成功！请使用新密码登录', 'success');
                closeResetPasswordModal();
            } else {
                showNotification(data.message || '密码重置失败', 'error');
            }
        } catch (error) {
            console.error('密码重置失败:', error);
            showNotification('网络错误，请稍后重试', 'error');
        }
    }

    // ==================== 导出全局函数 ====================
    // 将所有需要从 HTML 调用的函数挂载到 window 对象上
    window.handleAvatarClick = handleAvatarClick;
    window.handleLogout = handleLogout;
    window.navigateToProfile = navigateToProfile;
    window.closeLoginPrompt = closeLoginPrompt;
    window.goToLogin = goToLogin;
    window.closeConfirmModal = closeConfirmModal;
    window.confirmLogout = confirmLogout;
    window.openResetPasswordModal = openResetPasswordModal;
    window.closeResetPasswordModal = closeResetPasswordModal;
    window.handleResetPassword = handleResetPassword;
    window.initializeUserAuth = initializeUserAuth;  // 导出初始化函数供页面调用

    // ==================== 页面加载时初始化 ====================
    document.addEventListener('DOMContentLoaded', function() {
        // 默认初始化（不要求登录）
        // 各个页面可以在自己的脚本中调用 initializeUserAuth(true) 来要求登录
        initializeUserAuth(false);
    });

})();
