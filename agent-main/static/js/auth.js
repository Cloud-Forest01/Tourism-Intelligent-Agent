/**
 * 认证页面 JavaScript - 智慧旅行 Agent
 * 处理用户登录、注册、表单验证等
 */

// ========== 全局变量 ==========
const API_BASE_URL = window.location.origin;
let isAuthenticated = false;

// ========== 页面加载完成 ==========
document.addEventListener('DOMContentLoaded', function() {
    // 检查是否已登录
    checkAuthStatus();

    // 绑定表单提交事件
    document.getElementById('loginFormElement').addEventListener('submit', handleLogin);
    document.getElementById('registerFormElement').addEventListener('submit', handleRegister);

    // 绑定密码强度检测
    document.getElementById('regPassword').addEventListener('input', checkPasswordStrength);

    // 绑定密码确认验证
    document.getElementById('regPasswordConfirm').addEventListener('input', validatePasswordConfirm);
});

// ========== 认证状态检查 ==========
async function checkAuthStatus() {
    // 检查当前页面是否是登录页面（通过 body 的 class 或 data 属性）
    const isLoginPage = document.body.classList.contains('auth-page') ||
                       document.documentElement.getAttribute('data-page') === 'login';

    // 如果不在登录页面，不执行检查
    if (!isLoginPage) {
        return;
    }

    const token = localStorage.getItem('access_token');
    if (token) {
        try {
            const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            if (response.ok) {
                const user = await response.json();
                // 已登录，跳转到主页
                // 设置 Cookie 以便后端识别
                document.cookie = `access_token=${token}; path=/; max-age=${7*24*60*60}`;
                window.location.href = '/';
            } else {
                // Token 无效，清除本地存储
                localStorage.removeItem('access_token');
                localStorage.removeItem('user_info');
            }
        } catch (error) {
            console.error('检查认证状态失败:', error);
        }
    }
}

// ========== 表单切换 ==========
function showLoginForm() {
    document.getElementById('registerForm').classList.remove('active');
    document.getElementById('loginForm').classList.add('active');
}

function showRegisterForm() {
    document.getElementById('loginForm').classList.remove('active');
    document.getElementById('registerForm').classList.add('active');
}

// ========== 密码显示/隐藏切换 ==========
function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    const button = input.nextElementSibling;
    const icon = button.querySelector('i');

    if (input.type === 'password') {
        input.type = 'text';
        icon.classList.remove('fa-eye');
        icon.classList.add('fa-eye-slash');
    } else {
        input.type = 'password';
        icon.classList.remove('fa-eye-slash');
        icon.classList.add('fa-eye');
    }
}

// ========== 密码强度检测 ==========
function checkPasswordStrength(event) {
    const password = event.target.value;
    const strengthFill = document.getElementById('strengthFill');
    const strengthText = document.getElementById('strengthText');

    if (!password) {
        strengthFill.className = 'strength-fill';
        strengthText.textContent = '密码强度';
        return;
    }

    // 计算密码强度
    let strength = 0;
    if (password.length >= 6) strength++;
    if (password.length >= 10) strength++;
    if (/[a-z]/.test(password) && /[A-Z]/.test(password)) strength++;
    if (/\d/.test(password)) strength++;
    if (/[^a-zA-Z0-9]/.test(password)) strength++;

    // 更新 UI
    if (strength <= 2) {
        strengthFill.className = 'strength-fill weak';
        strengthText.textContent = '弱';
    } else if (strength <= 3) {
        strengthFill.className = 'strength-fill medium';
        strengthText.textContent = '中等';
    } else {
        strengthFill.className = 'strength-fill strong';
        strengthText.textContent = '强';
    }
}

// ========== 密码确认验证 ==========
function validatePasswordConfirm(event) {
    const password = document.getElementById('regPassword').value;
    const confirm = event.target.value;

    if (confirm && password !== confirm) {
        event.target.setCustomValidity('密码不匹配');
    } else {
        event.target.setCustomValidity('');
    }
}

// ========== 显示/隐藏加载状态 ==========
function showLoading(text = '处理中...') {
    const overlay = document.getElementById('loadingOverlay');
    const loadingText = document.getElementById('loadingText');
    loadingText.textContent = text;
    overlay.classList.add('active');
}

function hideLoading() {
    document.getElementById('loadingOverlay').classList.remove('active');
}

// ========== Toast 通知 ==========
function showToast(type, title, message, duration = 3000) {
    const toast = document.getElementById('toast');
    const toastIcon = document.getElementById('toastIcon');
    const toastTitle = document.getElementById('toastTitle');
    const toastMessage = document.getElementById('toastMessage');

    // 设置类型
    toast.className = `toast ${type}`;

    // 设置图标
    const icons = {
        success: 'fa-check-circle',
        error: 'fa-times-circle',
        warning: 'fa-exclamation-circle',
        info: 'fa-info-circle'
    };
    toastIcon.className = `fas ${icons[type] || icons.info}`;

    // 设置内容
    toastTitle.textContent = title;
    toastMessage.textContent = message;

    // 显示
    setTimeout(() => toast.classList.add('show'), 10);

    // 自动隐藏
    setTimeout(() => {
        toast.classList.remove('show');
    }, duration);
}

function hideToast() {
    document.getElementById('toast').classList.remove('show');
}

// ========== API 请求封装 ==========
async function apiRequest(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json'
        }
    };

    const finalOptions = {
        ...defaultOptions,
        ...options,
        headers: {
            ...defaultOptions.headers,
            ...options.headers
        }
    };

    try {
        const response = await fetch(`${API_BASE_URL}${url}`, finalOptions);
        const data = await response.json();
        return { response, data };
    } catch (error) {
        console.error('API 请求失败:', error);
        throw error;
    }
}

// ========== 处理登录 ==========
async function handleLogin(event) {
    event.preventDefault();

    const formData = new FormData(event.target);
    const loginData = {
        username: formData.get('username'),
        password: formData.get('password')
    };

    // 验证
    if (!loginData.username || !loginData.password) {
        showToast('error', '验证失败', '请填写所有必填字段');
        return;
    }

    showLoading('登录中...');

    try {
        const { response, data } = await apiRequest('/api/auth/login', {
            method: 'POST',
            body: JSON.stringify(loginData)
        });

        if (response.ok && data.success) {
            // 保存 token 和用户信息
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('user_info', JSON.stringify(data.user));

            // 记住我功能
            const rememberMe = document.getElementById('rememberMe').checked;
            if (rememberMe) {
                localStorage.setItem('remember_username', loginData.username);
            } else {
                localStorage.removeItem('remember_username');
            }

            showToast('success', '登录成功', '欢迎回来！');

            // 延迟跳转
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
        } else {
            showToast('error', '登录失败', data.message || '用户名或密码错误');
        }
    } catch (error) {
        showToast('error', '网络错误', '请检查网络连接后重试');
    } finally {
        hideLoading();
    }
}

// ========== 处理注册 ==========
async function handleRegister(event) {
    event.preventDefault();

    // 先隐藏之前的错误提示
    hideRegisterError();

    const formData = new FormData(event.target);
    const password = formData.get('password');
    const passwordConfirm = formData.get('passwordConfirm');
    const username = formData.get('username');

    // 验证密码匹配
    if (password !== passwordConfirm) {
        showToast('error', '验证失败', '两次输入的密码不一致');
        return;
    }

    const registerData = {
        username: username,
        password: password,
        email: formData.get('email') || null,
        nickname: formData.get('nickname') || '旅行者'
    };

    showLoading('注册中...');

    try {
        const { response, data } = await apiRequest('/api/auth/register', {
            method: 'POST',
            body: JSON.stringify(registerData)
        });

        if (response.ok && data.success) {
            // 保存 token 和用户信息
            localStorage.setItem('access_token', data.access_token);
            localStorage.setItem('user_info', JSON.stringify({
                user_id: data.user_id,
                username: registerData.username
            }));

            showToast('success', '注册成功', '欢迎加入智慧旅行 Agent！');

            // 延迟跳转
            setTimeout(() => {
                window.location.href = '/';
            }, 1000);
        } else {
            // ✅ 显示详细的错误提示
            showRegisterError(data.message || '注册失败，请重试');
        }
    } catch (error) {
        console.error('注册错误:', error);
        showToast('error', '网络错误', '请检查网络连接后重试');
    } finally {
        hideLoading();
    }
}

// ========== 显示注册错误 ==========
function showRegisterError(message) {
    const errorAlert = document.getElementById('registerErrorAlert');
    const errorMessage = document.getElementById('registerErrorMessage');
    const errorExamples = document.getElementById('registerErrorExamples');

    // 设置错误消息
    errorMessage.textContent = message;

    // 根据错误类型提供示例
    let examples = '';
    let errorLower = message.toLowerCase();

    if (errorLower.includes('用户名') || errorLower.includes('username')) {
        examples = `
            <strong>用户名要求：</strong>
            <ul>
                <li>长度：3-20个字符</li>
                <li>只能包含：字母（a-z, A-Z）、数字（0-9）、下划线（_）或连字符（-）</li>
                <li>✅ 正确示例：<code>user123</code>、<code>test_user</code>、<code>my-name</code></li>
                <li>❌ 错误示例：<code>user@123</code>、<code>用户名</code>、<code>user name</code></li>
            </ul>
        `;
    } else if (errorLower.includes('密码') || errorLower.includes('password')) {
        examples = `
            <strong>密码要求：</strong>
            <ul>
                <li>长度：至少6个字符，最多50个字符</li>
                <li>建议包含：字母、数字、特殊字符的组合</li>
                <li>✅ 正确示例：<code>password123</code>、<code>Mypass@2024</code></li>
                <li>❌ 错误示例：<code>12345</code>（太短）</li>
            </ul>
        `;
    } else if (errorLower.includes('邮箱') || errorLower.includes('email')) {
        examples = `
            <strong>邮箱要求（可选）：</strong>
            <ul>
                <li>必须是有效的邮箱格式</li>
                <li>✅ 正确示例：<code>user@example.com</code></li>
                <li>❌ 错误示例：<code>user@</code>、<code>@example.com</code></li>
            </ul>
        `;
    } else if (errorLower.includes('已存在') || errorLower.includes('already exists')) {
        examples = `
            <strong>提示：</strong>
            <ul>
                <li>该用户名已被注册，请更换其他用户名</li>
                <li>您可以尝试在原用户名后添加数字，如：<code>user123</code> → <code>user1234</code></li>
            </ul>
        `;
    } else {
        // 通用提示
        examples = `
            <strong>注册要求：</strong>
            <ul>
                <li>用户名：3-20个字符，只能包含字母、数字、下划线或连字符</li>
                <li>密码：至少6个字符</li>
                <li>邮箱：可选，填写时必须是有效邮箱格式</li>
            </ul>
        `;
    }

    errorExamples.innerHTML = examples;
    errorAlert.style.display = 'flex';

    // 滚动到错误提示
    errorAlert.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ========== 隐藏注册错误 ==========
function hideRegisterError() {
    const errorAlert = document.getElementById('registerErrorAlert');
    if (errorAlert) {
        errorAlert.style.display = 'none';
    }
}

// ========== 用户协议和隐私政策 ==========
function showTerms() {
    alert('用户协议\n\n1. 用户应遵守相关法律法规\n2. 禁止发布违法违规内容\n3. 平台保留最终解释权');
}

function showPrivacy() {
    alert('隐私政策\n\n1. 我们重视用户隐私保护\n2. 收集的信息仅用于改善服务\n3. 不会泄露用户个人信息');
}

// ========== 自动填充记住的用户名 ==========
window.addEventListener('load', function() {
    const rememberedUsername = localStorage.getItem('remember_username');
    if (rememberedUsername) {
        document.getElementById('loginUsername').value = rememberedUsername;
        document.getElementById('rememberMe').checked = true;
    }
});

// ========== 退出登录（供其他页面调用）==========
function logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_info');
    window.location.href = '/auth.html';
}

// ========== 游客模式 ==========
function enterAsGuest() {
    // 不需要登录，直接跳转到首页
    showToast('info', '游客模式', '您正在以游客身份浏览，部分功能可能受限');

    setTimeout(() => {
        window.location.href = '/';
    }, 500);
}

// ========== 导出函数供全局使用 ==========
window.authFunctions = {
    showLoginForm,
    showRegisterForm,
    togglePassword,
    logout,
    enterAsGuest,
    showToast
};
