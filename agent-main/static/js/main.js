// ==================== 全局变量 ====================
let currentUser = null;
let currentCarouselIndex = 0;
const carouselItems = 8; // 景点卡片数量

// AI助手当前模式：'form' 或 'chat'
let currentAIMode = 'form';

// ==================== 认证辅助函数 ====================
/**
 * 获取包含认证token的请求头
 * @param {Object} extraHeaders - 额外的请求头
 * @returns {Object} 包含Authorization的请求头对象
 */
function getAuthHeaders(extraHeaders = {}) {
    const token = localStorage.getItem('access_token');
    const headers = {
        'Content-Type': 'application/json',
        ...extraHeaders
    };

    // 如果有token，添加Authorization头
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    return headers;
}

// ==================== 页面加载完成后执行 ====================
document.addEventListener('DOMContentLoaded', function() {
    initializeTabs();
    initializeScrollEffects();
    checkUserSession();
    initializeCarousel();
});

// ==================== 模式切换 ====================
function switchMode(mode) {
    // ✅ 修复：使用正确的元素ID
    const formModeBtn = document.getElementById('form-mode-btn');
    const chatModeBtn = document.getElementById('chat-mode-btn');
    const formModeView = document.getElementById('form-mode-view');
    const chatModeView = document.getElementById('chat-mode-view');

    // 检查元素是否存在
    if (!formModeView || !chatModeView) {
        console.warn('⚠️ AI助手视图元素未找到，可能不在主页');
        return;
    }

    if (mode === 'form') {
        // 显示表单模式
        if (formModeBtn) formModeBtn.classList.add('active');
        if (chatModeBtn) chatModeBtn.classList.remove('active');
        formModeView.style.display = 'block';
        chatModeView.style.display = 'none';
    } else {
        // 显示对话模式
        if (chatModeBtn) chatModeBtn.classList.add('active');
        if (formModeBtn) formModeBtn.classList.remove('active');
        chatModeView.style.display = 'block';
        formModeView.style.display = 'none';
    }
}

// ==================== 对话功能 ====================
let chatHistory = [];

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message) return;

    // 添加用户消息
    addChatMessage(message, 'user');
    input.value = '';

    // 显示加载状态
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot-message loading';
    loadingDiv.innerHTML = '<i class="fas fa-ellipsis-h"></i>';
    document.getElementById('chat-messages').appendChild(loadingDiv);

    try {
        // 调用后端API
        const response = await fetch('/api/trip/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ prompt: message })
        });

        const data = await response.json();

        // 移除加载状态
        loadingDiv.remove();

        if (data.success) {
            addChatMessage(data.response, 'bot');

            // ✅ 刷新会话列表（方案1：立即刷新）
            await loadConversations();
        } else {
            addChatMessage('抱歉，处理您的请求时遇到了问题。', 'bot');
        }
    } catch (error) {
        loadingDiv.remove();
        addChatMessage('网络连接失败，请稍后重试。', 'bot');
    }
}

// 新的AI助手消息发送函数
async function sendAIMessage() {
    const input = document.getElementById('ai-input');
    const message = input.value.trim();

    if (!message) return;

    // 添加用户消息
    addAIMessage(message, 'user');
    input.value = '';

    // 显示加载状态
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot-message';
    loadingDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <p><i class="fas fa-ellipsis-h fa-bounce"></i></p>
        </div>
    `;
    document.getElementById('ai-messages').appendChild(loadingDiv);

    // 滚动到底部
    const messagesContainer = document.getElementById('ai-messages');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    try {
        // 调用后端API
        const response = await fetch('/api/trip/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ prompt: message })
        });

        const data = await response.json();

        // 移除加载状态
        loadingDiv.remove();

        if (data.success) {
            addAIMessage(data.response, 'bot');

            // ✅ 刷新会话列表（方案1：立即刷新）
            await loadConversations();
        } else {
            addAIMessage('抱歉，处理您的请求时遇到了问题。', 'bot');
        }
    } catch (error) {
        loadingDiv.remove();
        addAIMessage('网络连接失败，请稍后重试。', 'bot');
    }
}

// 添加AI助手消息
function addAIMessage(text, type) {
    const messagesDiv = document.getElementById('ai-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;

    if (type === 'user') {
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-user"></i>
            </div>
            <div class="message-content">
                <p>${text}</p>
                <span class="message-time">刚刚</span>
            </div>
        `;
    } else {
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <p>${text}</p>
                <span class="message-time">刚刚</span>
            </div>
        `;
    }

    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// 快捷消息
function sendQuickMessage(message) {
    document.getElementById('ai-input').value = message;
    sendAIMessage();
}

// 上传文件（占位函数）
function attachFile() {
    showNotification('文件上传功能开发中', 'info');
}

function addChatMessage(text, type) {
    const messagesDiv = document.getElementById('chat-messages');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;

    if (type === 'user') {
        messageDiv.innerHTML = `<span>${text}</span>`;
    } else {
        messageDiv.innerHTML = `<i class="fas fa-robot"></i><span>${text}</span>`;
    }

    messagesDiv.appendChild(messageDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// 监听回车键发送消息
document.addEventListener('DOMContentLoaded', () => {
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                sendChatMessage();
            }
        });
    }
});

// ==================== 景点轮播 ====================
function initializeCarousel() {
    const track = document.getElementById('attractions-track');
    if (!track) return;

    // 自动轮播
    setInterval(() => {
        moveCarousel(1);
    }, 5000);
}

function moveCarousel(direction) {
    const track = document.getElementById('attractions-track');
    if (!track) return;

    const cardWidth = 300; // 卡片宽度 + 间距
    const visibleCards = Math.floor(track.parentElement.offsetWidth / cardWidth);
    const maxIndex = carouselItems - visibleCards;

    currentCarouselIndex += direction;

    if (currentCarouselIndex < 0) {
        currentCarouselIndex = maxIndex;
    } else if (currentCarouselIndex > maxIndex) {
        currentCarouselIndex = 0;
    }

    const translateX = -(currentCarouselIndex * cardWidth);
    track.style.transform = `translateX(${translateX}px)`;
    track.style.transition = 'transform 0.5s ease';
}

// ==================== 标签切换 ====================
function initializeTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', function() {
            // 移除所有active类
            tabBtns.forEach(b => b.classList.remove('active'));
            // 添加active类到当前按钮
            this.classList.add('active');

            // 可以在这里添加切换不同表单的逻辑
            const tabType = this.getAttribute('data-tab');
            console.log('切换到标签:', tabType);
        });
    });
}

// ==================== 搜索处理 ====================
function handleSearch() {
    const destination = document.getElementById('destination-input').value;
    const startDate = document.querySelectorAll('.search-inputs input[type="date"]')[0]?.value;
    const endDate = document.querySelectorAll('.search-inputs input[type="date"]')[1]?.value;
    const budget = document.getElementById('budget-input')?.value;

    if (!destination) {
        showNotification(currentLang === 'zh' ? '请输入目的地' : 'Please enter destination', 'warning');
        return;
    }

    // 保存搜索条件到sessionStorage
    const searchData = {
        destination: destination,
        startDate: startDate,
        endDate: endDate,
        budget: budget
    };
    sessionStorage.setItem('searchData', JSON.stringify(searchData));

    // 跳转到规划页面
    window.location.href = `/planner?destination=${encodeURIComponent(destination)}`;
}

// ==================== 目的地选择 ====================
function selectDestination(destination) {
    showNotification(`已选择目的地: ${destination}`, 'success');

    // 延迟跳转到规划页面
    setTimeout(() => {
        window.location.href = `/planner?destination=${encodeURIComponent(destination)}`;
    }, 1000);
}

// ==================== 登录模态框 ====================
function showLoginModal() {
    // TODO: 实现登录模态框
    showNotification(currentLang === 'zh' ? '登录功能开发中' : 'Login feature coming soon', 'info');
}

// ==================== 移动端菜单 ====================
function toggleMobileMenu() {
    const navMenu = document.querySelector('.nav-menu');
    const navActions = document.querySelector('.nav-actions');

    navMenu.classList.toggle('mobile-active');
    navActions.classList.toggle('mobile-active');

    // 简单的实现:在移动端切换显示
    if (navMenu.style.display === 'flex') {
        navMenu.style.display = '';
        navActions.style.display = '';
    } else {
        navMenu.style.display = 'flex';
        navMenu.style.flexDirection = 'column';
        navMenu.style.position = 'absolute';
        navMenu.style.top = '100%';
        navMenu.style.left = '0';
        navMenu.style.right = '0';
        navMenu.style.background = 'white';
        navMenu.style.padding = '1rem';
        navMenu.style.boxShadow = '0 4px 6px -1px rgba(0, 0, 0, 0.1)';

        navActions.style.display = 'flex';
        navActions.style.flexDirection = 'column';
        navActions.style.position = 'absolute';
        navActions.style.top = 'calc(100% + 200px)';
        navActions.style.left = '0';
        navActions.style.right = '0';
        navActions.style.background = 'white';
        navActions.style.padding = '1rem';
    }
}

// ==================== 滚动效果 ====================
function initializeScrollEffects() {
    const navbar = document.querySelector('.navbar');

    window.addEventListener('scroll', () => {
        if (window.scrollY > 50) {
            navbar.style.boxShadow = '0 4px 6px -1px rgba(0, 0, 0, 0.1)';
        } else {
            navbar.style.boxShadow = '0 1px 2px 0 rgba(0, 0, 0, 0.05)';
        }
    });

    // 平滑滚动到锚点
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function(e) {
            const href = this.getAttribute('href');
            if (href !== '#') {
                e.preventDefault();
                const target = document.querySelector(href);
                if (target) {
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });
}

// ==================== 用户会话 ====================
function checkUserSession() {
    // 检查本地存储的用户信息
    const userStr = localStorage.getItem('currentUser');
    if (userStr) {
        try {
            currentUser = JSON.parse(userStr);
            updateUIForLoggedInUser();
        } catch (e) {
            console.error('解析用户信息失败:', e);
        }
    }
}

function updateUIForLoggedInUser() {
    const loginBtn = document.querySelector('.btn-login');
    if (loginBtn && currentUser) {
        loginBtn.textContent = currentUser.username || '用户';
        loginBtn.onclick = () => showUserMenu();
    }
}

function showUserMenu() {
    // 可以实现用户菜单,这里简单显示通知
    showNotification(`欢迎回来, ${currentUser.username}!`, 'success');
}

// ==================== 通知系统 ====================
function showNotification(message, type = 'info') {
    // 检查是否已存在通知容器
    let container = document.getElementById('notification-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.style.cssText = `
            position: fixed;
            top: 100px;
            right: 20px;
            z-index: 10000;
            max-width: 400px;
        `;
        document.body.appendChild(container);
    }

    // 创建通知元素
    const notification = document.createElement('div');
    const bgColor = {
        'success': '#10B981',
        'warning': '#F59E0B',
        'error': '#EF4444',
        'info': '#3B82F6'
    }[type] || '#3B82F6';

    notification.style.cssText = `
        background: ${bgColor};
        color: white;
        padding: 1rem 1.5rem;
        margin-bottom: 1rem;
        border-radius: 0.5rem;
        box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
        animation: slideInRight 0.3s ease;
        display: flex;
        align-items: center;
        gap: 0.75rem;
        font-weight: 500;
    `;

    notification.innerHTML = `
        <i class="fas fa-${type === 'success' ? 'check-circle' : type === 'warning' ? 'exclamation-triangle' : type === 'error' ? 'times-circle' : 'info-circle'}"></i>
        <span>${message}</span>
    `;

    container.appendChild(notification);

    // 3秒后自动移除
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// 添加通知动画
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// ==================== API调用 ====================
async function callAPI(endpoint, method = 'GET', data = null) {
    try {
        const options = {
            method: method,
            headers: {
                'Content-Type': 'application/json'
            }
        };

        if (data) {
            options.body = JSON.stringify(data);
        }

        const response = await fetch(endpoint, options);
        const result = await response.json();

        if (!response.ok) {
            throw new Error(result.message || '请求失败');
        }

        return result;
    } catch (error) {
        console.error('API调用失败:', error);
        showNotification(`操作失败: ${error.message}`, 'error');
        throw error;
    }
}

// ==================== 工具函数 ====================

// formatDate 函数定义在第1931行，支持更多格式

// 计算天数差
function daysBetween(startDate, endDate) {
    const start = new Date(startDate);
    const end = new Date(endDate);
    const timeDiff = end.getTime() - start.getTime();
    return Math.ceil(timeDiff / (1000 * 3600 * 24));
}

// 防抖函数
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 节流函数
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func.apply(this, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// ==================== 加载动画 ====================
function showLoading(message = '加载中...') {
    const loader = document.createElement('div');
    loader.id = 'global-loader';
    loader.style.cssText = `
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        z-index: 9999;
        flex-direction: column;
        gap: 1rem;
    `;

    loader.innerHTML = `
        <div style="
            width: 50px;
            height: 50px;
            border: 4px solid rgba(255, 255, 255, 0.3);
            border-top-color: white;
            border-radius: 50%;
            animation: spin 1s linear infinite;
        "></div>
        <div style="color: white; font-weight: 500;">${message}</div>
    `;

    document.body.appendChild(loader);
}

function hideLoading() {
    const loader = document.getElementById('global-loader');
    if (loader) {
        loader.remove();
    }
}

// 添加旋转动画
const spinStyle = document.createElement('style');
spinStyle.textContent = `
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
`;
document.head.appendChild(spinStyle);

console.log('🚀 下一站Youth主页已加载完成');

// ==================== 旅行规划表单功能 ====================

// 初始化默认日期
document.addEventListener('DOMContentLoaded', function() {
    // 设置默认日期
    const today = new Date();
    const startDate = new Date(today);
    startDate.setDate(today.getDate() + 7);
    const endDate = new Date(today);
    endDate.setDate(today.getDate() + 10);

    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');

    if (startDateInput) {
        startDateInput.value = formatDate(startDate);
    }
    if (endDateInput) {
        endDateInput.value = formatDate(endDate);
    }

    // ✅ 初始化偏好计数显示
    updatePreferenceCount();

    // 用户ID已在 checkUserSession() 和 initializeConversationManagement() 中加载
});

// 更新偏好选择数量
function updatePreferenceCount() {
    const checkboxes = document.querySelectorAll('.preferences-grid input[type="checkbox"]');
    let count = 0;

    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            count++;
        }
    });

    const countDisplay = document.getElementById('preference-count');
    if (countDisplay) {
        // ✅ 修改：不限制数量，移除"已达上限"提示
        countDisplay.textContent = count === 0 ? '未选择偏好（将按经典路线推荐）' : `已选择${count}个偏好`;
        countDisplay.style.color = count === 0 ? '#9CA3AF' : '#6366F1';
    }

    // ✅ 移除3个限制：允许任意选择数量
    // 原来的限制逻辑已删除
}

// 提交旅行规划表单
async function submitTravelPlan() {
    // 获取表单数据
    const destination = document.getElementById('destination').value.trim();
    const startDate = document.getElementById('start-date').value;
    const endDate = document.getElementById('end-date').value;
    const budget = document.getElementById('budget').value;
    const travelers = parseInt(document.getElementById('travelers').value) || 1;
    const requirements = document.getElementById('requirements').value.trim();
    const deepThinking = document.getElementById('deep-thinking-form-chat').checked;

    // 获取选中的偏好
    const preferences = [];
    document.querySelectorAll('.preferences-grid input[type="checkbox"]:checked').forEach(checkbox => {
        preferences.push(checkbox.value);
    });

    // 验证表单
    if (!destination) {
        showNotification('请输入目的地', 'warning');
        return;
    }

    if (!startDate || !endDate) {
        showNotification('请选择旅行日期', 'warning');
        return;
    }

    if (new Date(startDate) > new Date(endDate)) {
        showNotification('结束日期不能早于开始日期', 'warning');
        return;
    }

    // 人数验证
    if (travelers < 1 || travelers > 20) {
        showNotification('人数必须在1-20人之间', 'warning');
        return;
    }

    // ✅ 移除偏好验证：允许不选择偏好（一键规划功能可能不添加偏好）
    // if (preferences.length === 0) {
    //     showNotification('请至少选择一个旅行偏好', 'warning');
    //     return;
    // }

    // 构建提示词
    let prompt = `请帮我规划一次${destination}的旅行：\n`;
    prompt += `📅 时间：${startDate} 至 ${endDate}（共${daysBetween(startDate, endDate)}天）\n`;
    prompt += `👥 人数：${travelers}人\n`;
    prompt += `💰 预算：${budget}元\n`;

    // ✅ 根据是否选择偏好，给出不同的提示
    if (preferences.length > 0) {
        prompt += `🎯 偏好：${preferences.join('、')}\n`;
    } else {
        prompt += `🎯 路线风格：经典路线推荐（必去景点+经典体验）\n`;
    }

    if (requirements) {
        prompt += `💬 其他要求：${requirements}\n`;
    }

    // ✅ 根据是否有偏好，调整攻略要求
    if (preferences.length === 0) {
        prompt += `\n请为我们生成详细的经典穷游攻略，包括：\n`;
        prompt += `- 每日经典行程安排（必去景点+地标建筑）\n`;
        prompt += `- 经典拍照打卡点推荐\n`;
        prompt += `- 学生优惠信息\n`;
        prompt += `- 平价美食推荐（本地特色）\n`;
        prompt += `- 预算明细\n`;
        prompt += `- 住宿建议（${travelers > 1 ? '考虑' + travelers + '人拼房' : '单人出行'}）`;
    } else {
        prompt += `\n请为我们生成详细的穷游攻略，包括：\n`;
        prompt += `- 每日行程安排\n`;
        prompt += `- 学生优惠景点推荐\n`;
        prompt += `- 平价美食推荐\n`;
        prompt += `- 预算明细\n`;
        prompt += `- 住宿建议（${travelers > 1 ? '考虑' + travelers + '人拼房' : '单人出行'}）`;
    }

    // 在表单模式的聊天窗口显示用户的问题
    addMessageToChat('form-messages', prompt, 'user');

    // ✅ 显示AI进度条
    aiProgressManager.show();
    aiProgressManager.startProgress();

    // 显示加载状态
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot-message';
    loadingDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <p><i class="fas fa-ellipsis-h fa-bounce"></i> 正在为您规划${destination}之旅...</p>
        </div>
    `;
    document.getElementById('form-messages').appendChild(loadingDiv);

    // 滚动到底部
    scrollToBottom('form-messages');

    try {
        // 调用后端API - 使用非流式端点（更好的用户体验）
        const response = await fetch('/api/trip/plan', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                destination: destination,
                start_date: startDate,
                end_date: endDate,
                preferences: preferences,
                budget: budget,
                travelers: travelers,
                user_requirements: requirements,
                user_id: userId,
                deep_thinking: deepThinking
            })
        });

        const data = await response.json();

        // 移除加载状态
        loadingDiv.remove();

        if (data.success) {
            // 显示AI回复
            const responseText = data.data?.plan || data.response || '未收到响应';
            console.log('✅ 行程规划完成，响应长度:', responseText?.length);
            addMessageToChat('form-messages', responseText, 'bot');

            // ✅ 保存当前会话ID，用于后续"新建会话"操作
            if (data.data?.conversation_id) {
                window.currentFormConversationId = data.data.conversation_id;
                console.log('✅ 已保存会话ID:', data.data.conversation_id);
            }

            // ✅ 刷新会话列表（方案1：立即刷新）
            await loadConversations();

            // 隐藏AI进度条
            aiProgressManager.hide();

            showNotification('旅行规划生成成功！', 'success');
        } else {
            addMessageToChat('form-messages', '抱歉，处理您的请求时遇到了问题。', 'bot');
            showNotification('生成失败，请稍后重试', 'error');
            // 隐藏AI进度条
            aiProgressManager.hide();
        }
    } catch (error) {
        loadingDiv.remove();
        // 隐藏AI进度条
        aiProgressManager.hide();
        console.error('表单规划失败:', error);
        addMessageToChat('form-messages', `❌ 网络连接失败: ${error.message}`, 'bot');
        showNotification('网络连接失败', 'error');
    }
}

// 切换会话侧边栏
let conversationSidebarVisible = false;

function toggleConversationSidebar() {
    conversationSidebarVisible = !conversationSidebarVisible;

    // 这里可以实现会话列表的显示/隐藏
    showNotification(
        conversationSidebarVisible ? '会话列表已展开' : '会话列表已收起',
        'info'
    );

    // TODO: 实现实际的侧边栏UI
}

// ==================== AI模式切换功能 ====================

/**
 * 切换AI助手模式
 * @param {string} mode - 'form' 或 'chat'
 */
function switchAIMode(mode) {
    currentAIMode = mode;

    const formModeBtn = document.getElementById('form-mode-btn');
    const chatModeBtn = document.getElementById('chat-mode-btn');
    const formModeView = document.getElementById('form-mode-view');
    const chatModeView = document.getElementById('chat-mode-view');

    if (mode === 'form') {
        // 显示表单模式
        formModeBtn.classList.add('active');
        chatModeBtn.classList.remove('active');
        formModeView.style.display = 'block';
        chatModeView.style.display = 'none';
        showNotification('已切换到表单模式', 'success');
    } else {
        // 显示对话模式
        chatModeBtn.classList.add('active');
        formModeBtn.classList.remove('active');
        chatModeView.style.display = 'block';
        formModeView.style.display = 'none';
        showNotification('已切换到对话模式', 'success');
    }

    // ✅ 刷新会话列表（方案1：Tab切换时刷新）
    loadConversations();
}

/**
 * 新建表单会话 - 保存当前表单生成的会话，清空表单
 * 功能：不切换模式，只是保存会话并重置表单，让用户可以开始新的规划
 */
async function createFormConversation() {
    // 检查是否有已生成的会话
    if (window.currentFormConversationId) {
        console.log('✅ 当前会话已保存到数据库，ID:', window.currentFormConversationId);
        showNotification('当前规划已保存，可以开始新的规划', 'success');
    } else {
        console.log('ℹ️ 当前没有已生成的会话');
        showNotification('已清空表单，可以开始新的规划', 'info');
    }

    // 清空表单模式的聊天记录
    const formMessages = document.getElementById('form-messages');
    if (formMessages) {
        // 只保留欢迎消息和快捷选项
        const welcomeMessage = formMessages.querySelector('.message.bot-message');
        const quickOptions = formMessages.querySelector('.quick-options');
        formMessages.innerHTML = '';
        if (welcomeMessage) {
            formMessages.appendChild(welcomeMessage.cloneNode(true));
        }
        if (quickOptions) {
            formMessages.appendChild(quickOptions.cloneNode(true));
        }
    }

    // 清空表单
    document.getElementById('destination').value = '';
    document.getElementById('start-date').value = '';
    document.getElementById('end-date').value = '';
    document.getElementById('requirements').value = '';
    // 重置偏好选择
    document.querySelectorAll('.preferences-grid input[type="checkbox"]').forEach(cb => {
        cb.checked = false;
    });
    updatePreferenceCount();

    // 重置当前会话ID
    window.currentFormConversationId = null;
}

/**
 * 根据当前模式发送消息
 * @param {string} message - 消息内容
 * @param {string} targetMode - 目标模式 ('form' 或 'chat')
 */
function sendQuickMessageByMode(message, targetMode) {
    // 如果不在目标模式，先切换
    if (currentAIMode !== targetMode) {
        switchAIMode(targetMode);
    }

    // 根据目标模式发送消息
    if (targetMode === 'form') {
        sendFormAIMessageWithText(message);
    } else {
        sendChatAIMessageWithText(message);
    }
}

/**
 * ==================== AI消息发送（统一函数） ====================
 */

/**
 * 统一的发送AI消息函数
 * @param {string} message - 用户消息内容
 * @param {string} containerId - 消息容器ID ('form-messages' 或 'chat-messages')
 * @param {string} thinkingCheckboxId - 深度思考复选框ID
 * @param {string|null} conversationId - 会话ID（可为null表示独立对话）
 * @param {boolean} showSuccessNotification - 是否显示成功通知
 */
async function sendAIMessageToContainer(message, containerId, thinkingCheckboxId, conversationId, showSuccessNotification = true) {
    addMessageToChat(containerId, message, 'user');

    // ✅ 显示AI进度条
    aiProgressManager.show();
    aiProgressManager.startProgress();

    // 显示加载状态
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message bot-message';
    loadingDiv.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <p><i class="fas fa-ellipsis-h fa-bounce"></i> 正在思考...</p>
            <span class="message-time">刚刚</span>
        </div>
    `;
    document.getElementById(containerId).appendChild(loadingDiv);
    scrollToBottom(containerId);

    try {
        // 获取深度思考状态
        const deepThinking = document.getElementById(thinkingCheckboxId)?.checked || false;

        // 调用后端聊天API
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
                message: message,
                user_id: userId,
                conversation_id: conversationId,
                deep_thinking: deepThinking
            })
        });

        const data = await response.json();

        // 移除加载状态
        loadingDiv.remove();

        if (data.success) {
            // 显示AI回复
            const responseText = data.data?.response || data.response || '未收到响应';
            console.log('✅ 对话完成，响应长度:', responseText?.length);
            addMessageToChat(containerId, responseText, 'bot');

            // ✅ 保存会话ID（仅当conversationId不为null时）
            if (conversationId === null && data.data?.conversation_id) {
                if (containerId === 'form-messages') {
                    window.currentFormConversationId = data.data.conversation_id;
                } else {
                    currentConversationId = data.data.conversation_id;
                }
                console.log('✅ 已保存会话ID:', data.data.conversation_id);
            }

            // ✅ 刷新会话列表（方案1：立即刷新）
            await loadConversations();

            // 隐藏AI进度条
            aiProgressManager.hide();

            if (showSuccessNotification) {
                showNotification('回复成功', 'success');
            }
        } else {
            addMessageToChat(containerId, '抱歉，处理您的请求时遇到了问题。', 'bot');
            showNotification('回复失败，请稍后重试', 'error');
            // 隐藏AI进度条
            aiProgressManager.hide();
        }
    } catch (error) {
        loadingDiv.remove();
        // 隐藏AI进度条
        aiProgressManager.hide();
        console.error('聊天请求失败:', error);
        addMessageToChat(containerId, `❌ 网络连接失败: ${error.message}`, 'bot');
        showNotification('网络连接失败', 'error');
    }
}

/**
 * 表单模式发送消息（使用统一函数）
 */
async function sendFormAIMessageWithText(message) {
    await sendAIMessageToContainer(
        message,
        'form-messages',
        'deep-thinking-form-chat',
        null,  // 表单模式使用独立的对话
        false  // 不显示成功通知（避免打扰）
    );
}

/**
 * 对话模式发送消息（使用统一函数）
 */
async function sendChatAIMessageWithText(message) {
    await sendAIMessageToContainer(
        message,
        'chat-messages',
        'deep-thinking',
        currentConversationId,
        true  // 显示成功通知
    );
}

/**
 * 表单模式 - 从输入框发送消息
 */
function sendFormAIMessage() {
    const input = document.getElementById('form-input');
    const message = input.value.trim();

    if (!message) return;

    sendFormAIMessageWithText(message);
    input.value = '';
}

/**
 * 对话模式 - 从输入框发送消息
 */
function sendChatAIMessage() {
    const input = document.getElementById('chat-input');
    const message = input.value.trim();

    if (!message) return;

    sendChatAIMessageWithText(message);
    input.value = '';
}

/**
 * 添加消息到聊天窗口（支持 Markdown 渲染）
 * @param {string} containerId - 聊天容器ID
 * @param {string} text - 消息内容
 * @param {string} type - 'user' 或 'bot'
 */
function addMessageToChat(containerId, text, type) {
    const messagesDiv = document.getElementById(containerId);
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${type}-message`;

    if (type === 'user') {
        // 用户消息：纯文本显示
        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-user"></i>
            </div>
            <div class="message-content">
                <p>${escapeHtml(text)}</p>
                <span class="message-time">刚刚</span>
            </div>
        `;
    } else {
        // Bot 消息：渲染 Markdown
        let renderedContent = text;

        // 检查是否加载了 marked 库
        if (typeof marked !== 'undefined') {
            try {
                // 配置 marked 选项
                marked.setOptions({
                    breaks: true,      // 支持 GitHub 风格的换行
                    gfm: true,         // GitHub Flavored Markdown
                    tables: true,      // 支持表格
                    sanitize: false    // 我们手动用 DOMPurify 清理
                });

                // 渲染 Markdown
                const rawHtml = marked.parse(text);

                // 使用 DOMPurify 清理 HTML（防止 XSS）
                if (typeof DOMPurify !== 'undefined') {
                    renderedContent = DOMPurify.sanitize(rawHtml);
                } else {
                    renderedContent = rawHtml;
                }
            } catch (e) {
                console.error('Markdown 渲染失败:', e);
                renderedContent = escapeHtml(text);
            }
        } else {
            // 如果没有 marked 库，显示纯文本并转义
            renderedContent = escapeHtml(text).replace(/\n/g, '<br>');
        }

        messageDiv.innerHTML = `
            <div class="message-avatar">
                <i class="fas fa-robot"></i>
            </div>
            <div class="message-content">
                <div class="markdown-body">${renderedContent}</div>
                <span class="message-time">刚刚</span>
            </div>
        `;

        // 添加图片加载错误处理
        setTimeout(() => {
            const images = messageDiv.querySelectorAll('.markdown-body img');
            images.forEach(img => {
                img.addEventListener('error', function() {
                    this.style.display = 'none';
                    const placeholder = document.createElement('div');
                    placeholder.className = 'image-placeholder';
                    placeholder.innerHTML = `
                        <div style="padding: 2rem; text-align: center; background: #f6f8fa; border-radius: 6px; margin: 12px 0;">
                            <i class="fas fa-image" style="font-size: 2rem; color: #9ca3af; margin-bottom: 0.5rem;"></i>
                            <p style="color: #6a737d; font-size: 0.875rem;">图片加载失败</p>
                            <a href="${this.src}" target="_blank" style="color: #0969da; font-size: 0.75rem;">在新窗口打开</a>
                        </div>
                    `;
                    this.parentNode.insertBefore(placeholder, this);
                });
            });
        }, 0);
    }

    messagesDiv.appendChild(messageDiv);
    scrollToBottom(containerId);
}

/**
 * 滚动到底部
 * @param {string} containerId - 容器ID
 */
function scrollToBottom(containerId) {
    const container = document.getElementById(containerId);
    if (container) {
        container.scrollTop = container.scrollHeight;
    }
}

// ==================== 会话管理功能 ====================

/**
 * 会话管理相关变量
 */
let currentConversationId = null;
let conversations = [];
let userId = 'anonymous'; // 默认匿名用户，可以从localStorage获取

/**
 * 初始化会话管理
 */
function initializeConversationManagement() {
    // 从localStorage获取用户信息
    const userInfoStr = localStorage.getItem('user_info');
    if (userInfoStr) {
        try {
            const userInfo = JSON.parse(userInfoStr);
            if (userInfo.user_id) {
                userId = userInfo.user_id;
                console.log('✅ 已加载用户ID:', userId);
            }
        } catch (e) {
            console.error('解析用户信息失败:', e);
        }
    }

    // 加载会话列表
    loadConversations();
}

/**
 * 加载会话列表
 */
async function loadConversations() {
    console.log('🔄 开始加载会话列表, userId:', userId);

    // 如果是匿名用户，显示空列表
    if (userId === 'anonymous' || !userId) {
        console.warn('⚠️ 用户未登录，跳过加载会话列表');
        renderEmptyConversationList();
        return;
    }

    try {
        // 获取Token
        const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');

        const response = await fetch(`/api/conversations?user_id=${userId}`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { 'Authorization': `Bearer ${token}` } : {})
            }
        });
        console.log('📡 API响应状态:', response.status);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('📦 API响应数据:', data);

        // ✅ 修复：检查响应格式
        if (data.success && data.data && data.data.conversations) {
            // ✅ 只保留活跃和归档的会话，过滤掉已删除的
            conversations = data.data.conversations.filter(conv =>
                conv.status !== 'deleted'
            );
            console.log('✅ 过滤后会话数量:', conversations.length);
            renderConversationList();
        } else {
            console.error('❌ 加载会话列表失败:', data.message);
            renderEmptyConversationList();
        }
    } catch (error) {
        console.error('❌ 加载会话列表出错:', error);
        showNotification(`加载会话失败: ${error.message}`, 'error');
        renderEmptyConversationList();
    }
}

/**
 * 渲染会话列表
 */
function renderConversationList() {
    const listContainer = document.getElementById('conversations-list');
    if (!listContainer) return;

    if (conversations.length === 0) {
        renderEmptyConversationList();
        return;
    }

    console.log('🎨 渲染会话列表, 会话数量:', conversations.length);

    listContainer.innerHTML = conversations.map(conv => {
        // ✅ 修复：支持多种ID字段名（id 或 conversation_id）
        const convId = conv.id || conv.conversation_id;
        const convTitle = conv.title || conv.destination || '新对话';
        const convDate = conv.created_at || conv.updated_at || new Date().toISOString();

        return `
            <div class="conversation-item ${convId === currentConversationId ? 'active' : ''}"
                 onclick="switchConversation('${convId}')"
                 data-conversation-id="${convId}">
                <div class="conversation-title">${escapeHtml(convTitle)}</div>
                <div class="conversation-meta">
                    <span class="conversation-date">${formatDate(convDate)}</span>
                </div>
                <button class="conversation-delete-btn"
                        onclick="event.stopPropagation(); deleteConversationFromMain('${convId}')"
                        title="删除会话">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
    }).join('');

    console.log('✅ 会话列表渲染完成');
}

/**
 * 渲染空会话列表
 */
function renderEmptyConversationList() {
    const listContainer = document.getElementById('conversations-list');
    if (!listContainer) return;

    // ✅ 如果是匿名用户，显示登录提示
    if (userId === 'anonymous' || !userId) {
        listContainer.innerHTML = `
            <div class="conversation-empty">
                <i class="fas fa-user-circle" style="font-size: 2rem; color: #ddd; margin-bottom: 0.5rem;"></i>
                <p style="color: #999; font-size: 0.875rem;">请先登录以查看会话历史</p>
            </div>
        `;
        return;
    }

    listContainer.innerHTML = `
        <div class="conversation-empty">
            <i class="fas fa-comments" style="font-size: 2rem; color: #ddd; margin-bottom: 0.5rem;"></i>
            <p style="color: #999; font-size: 0.875rem;">暂无会话记录</p>
        </div>
    `;
}

/**
 * 删除会话（软删除 - 移至回收站）
 * @param {string} conversationId - 会话ID
 */
async function deleteConversationFromMain(conversationId) {
    if (!confirm('确定要删除这个会话吗？删除后可在"我的会话"-"回收站"中恢复（保留7天）')) {
        return;
    }

    try {
        const response = await fetch(`/api/conversations/${conversationId}?user_id=${userId}`, {
            method: 'DELETE'
        });
        const data = await response.json();

        if (data.success) {
            // 显示成功提示
            showNotification('会话已移至回收站，可在"我的会话"中恢复（7天后自动清理）', 'success');

            // 如果删除的是当前会话，清空聊天并显示欢迎界面
            if (conversationId === currentConversationId) {
                currentConversationId = null;

                // 清空聊天显示区域（显示欢迎消息和快捷选项）
                const chatMessagesDiv = document.getElementById('chat-messages');
                if (chatMessagesDiv) {
                    // 创建全新的欢迎消息
                    chatMessagesDiv.innerHTML = `
                        <div class="message bot-message">
                            <div class="message-avatar">
                                <i class="fas fa-robot"></i>
                            </div>
                            <div class="message-content">
                                <p>你好！我是小You，你的智能旅行助手 ✨<br><br>我们可以聊聊：<br>🌍 目的地推荐<br>🎒 旅行攻略<br>💰 省钱技巧<br>🏛️ 景点介绍<br>🍜 美食推荐<br><br>想聊什么，尽管问我！</p>
                                <span class="message-time">刚刚</span>
                            </div>
                        </div>

                        <!-- 快捷选项 -->
                        <div class="quick-options">
                            <div class="quick-option" onclick="sendQuickMessageByMode('帮我规划云南之旅', 'chat')">
                                <i class="fas fa-mountain"></i>
                                <span>云南之旅</span>
                            </div>
                            <div class="quick-option" onclick="sendQuickMessageByMode('推荐成都美食攻略', 'chat')">
                                <i class="fas fa-utensils"></i>
                                <span>成都美食</span>
                            </div>
                            <div class="quick-option" onclick="sendQuickMessageByMode('预算2000元的国内穷游推荐', 'chat')">
                                <i class="fas fa-wallet"></i>
                                <span>穷游推荐</span>
                            </div>
                            <div class="quick-option" onclick="sendQuickMessageByMode('适合大学生的周边游', 'chat')">
                                <i class="fas fa-graduation-cap"></i>
                                <span>周边游</span>
                            </div>
                        </div>
                    `;
                }
            }

            // 重新加载会话列表
            await loadConversations();
        } else {
            showNotification(data.message || '删除失败', 'error');
        }
    } catch (error) {
        console.error('删除会话出错:', error);
        showNotification('删除会话失败', 'error');
    }
}

/**
 * 创建新会话
 * 功能：保留当前进行的对话，重置会话ID，清空聊天显示，准备开始新对话
 */
async function createNewChat() {
    try {
        // 检查当前是否有正在进行的对话
        const hasCurrentConversation = currentConversationId !== null;
        const messagesDiv = document.getElementById('chat-messages');
        const hasMessages = messagesDiv && messagesDiv.querySelectorAll('.message').length > 2; // 排除欢迎消息和快捷选项

        if (hasCurrentConversation && hasMessages) {
            // 当前有对话，提示用户
            console.log('ℹ️ 保留当前会话：', currentConversationId);
            // 不需要额外操作，会话已经保存在后端了
        }

        // 清空聊天显示区域（显示欢迎消息和快捷选项）
        const chatMessagesDiv = document.getElementById('chat-messages');
        if (chatMessagesDiv) {
            // 创建全新的欢迎消息
            chatMessagesDiv.innerHTML = `
                <div class="message bot-message">
                    <div class="message-avatar">
                        <i class="fas fa-robot"></i>
                    </div>
                    <div class="message-content">
                        <p>你好！我是小You，你的智能旅行助手 ✨<br><br>我们可以聊聊：<br>🌍 目的地推荐<br>🎒 旅行攻略<br>💰 省钱技巧<br>🏛️ 景点介绍<br>🍜 美食推荐<br><br>想聊什么，尽管问我！</p>
                        <span class="message-time">刚刚</span>
                    </div>
                </div>

                <!-- 快捷选项 -->
                <div class="quick-options">
                    <div class="quick-option" onclick="sendQuickMessageByMode('帮我规划云南之旅', 'chat')">
                        <i class="fas fa-mountain"></i>
                        <span>云南之旅</span>
                    </div>
                    <div class="quick-option" onclick="sendQuickMessageByMode('推荐成都美食攻略', 'chat')">
                        <i class="fas fa-utensils"></i>
                        <span>成都美食</span>
                    </div>
                    <div class="quick-option" onclick="sendQuickMessageByMode('预算2000元的国内穷游推荐', 'chat')">
                        <i class="fas fa-wallet"></i>
                        <span>穷游推荐</span>
                    </div>
                    <div class="quick-option" onclick="sendQuickMessageByMode('适合大学生的周边游', 'chat')">
                        <i class="fas fa-graduation-cap"></i>
                        <span>周边游</span>
                    </div>
                </div>
            `;
        }

        // 重置会话ID，下次发送消息时会自动创建新会话
        currentConversationId = null;

        // 清空输入框
        const chatInput = document.getElementById('chat-input');
        if (chatInput) {
            chatInput.value = '';
            chatInput.focus();
        }

        // 显示成功提示
        showNotification('✅ 新会话已准备就绪，请开始对话', 'success');

        // 重新加载会话列表（显示最新状态）
        await loadConversations();
    } catch (error) {
        console.error('创建新会话出错:', error);
        showNotification('准备新会话失败', 'error');
    }
}

/**
 * 切换会话
 * @param {string} conversationId - 会话ID
 */
async function switchConversation(conversationId) {
    try {
        // 获取Token
        const token = localStorage.getItem('access_token') || sessionStorage.getItem('access_token');
        const headers = {
            'Content-Type': 'application/json',
            ...(token ? { 'Authorization': `Bearer ${token}` } : {})
        };

        // 并行获取会话信息和消息列表
        const [convResponse, msgResponse] = await Promise.all([
            fetch(`/api/conversations/${conversationId}`, { headers }),
            fetch(`/api/conversations/${conversationId}/messages?limit=100&offset=0`, { headers })
        ]);

        const convData = await convResponse.json();
        const msgData = await msgResponse.json();

        if (convData.success && convData.data.conversation) {
            const conversation = convData.data.conversation;

            // 🔒 归档会话检查
            if (conversation.status === 'archived') {
                showNotification('⚠️ 该会话已归档，只能查看历史记录，无法继续对话。请在仪表板中恢复会话后再使用。', 'warning');
                // 仍然允许加载历史消息，但标记为只读
                currentConversationId = null; // 不设置当前会话ID，禁止发送消息
            } else if (conversation.status === 'deleted') {
                showNotification('❌ 该会话已删除，无法访问。请在仪表板中恢复会话。', 'error');
                return; // 完全阻止访问
            } else {
                currentConversationId = conversationId; // 正常会话，允许操作
            }

            // 渲染消息（如果有的话）
            if (msgData.success && msgData.data && msgData.data.messages) {
                const messages = msgData.data.messages;

                // ✅ 清空消息区域（CSS flex布局已控制高度，无需maxHeight）
                const messagesDiv = document.getElementById('chat-messages');
                if (messagesDiv) {
                    messagesDiv.innerHTML = '';
                }

                // ✅ 优先显示最新的攻略（最后2条消息）
                const filteredMessages = messages.slice(-2);
                renderConversationMessages(filteredMessages);

                // ✅ 如果有更多历史消息，添加"查看完整历史"按钮
                if (messages.length > 2) {
                    if (messagesDiv) {
                        const loadMoreBtn = document.createElement('button');
                        loadMoreBtn.className = 'load-more-btn';
                        loadMoreBtn.innerHTML = '<i class="fas fa-history"></i> 查看完整对话历史 (' + messages.length + ' 条消息)';
                        loadMoreBtn.style.cssText = `
                            display: block;
                            width: 100%;
                            padding: 12px 20px;
                            margin: 10px 0;
                            background: #f0f7ff;
                            border: 1px solid #d0e3ff;
                            border-radius: 8px;
                            color: #0969da;
                            font-size: 14px;
                            cursor: pointer;
                            transition: all 0.3s;
                        `;
                        loadMoreBtn.onmouseover = () => {
                            loadMoreBtn.style.background = '#e1efff';
                        };
                        loadMoreBtn.onmouseout = () => {
                            loadMoreBtn.style.background = '#f0f7ff';
                        };
                        loadMoreBtn.onclick = () => {
                            renderConversationMessages(messages);
                            loadMoreBtn.remove();
                            showNotification('已显示完整对话历史', 'success');
                        };
                        messagesDiv.insertBefore(loadMoreBtn, messagesDiv.firstChild);
                    }
                }

                // ✅ 确保滚动到底部（延迟执行确保DOM更新完成）
                setTimeout(() => {
                    if (messagesDiv) {
                        messagesDiv.scrollTop = messagesDiv.scrollHeight;
                    }
                }, 100);

                // 如果是归档会话，添加提示横幅
                if (conversation.status === 'archived') {
                    if (messagesDiv) {
                        const banner = document.createElement('div');
                        banner.className = 'archived-banner';
                        banner.style.cssText = `
                            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                            color: white;
                            padding: 16px 20px;
                            border-radius: 8px;
                            margin: 10px 0;
                            display: flex;
                            align-items: center;
                            justify-content: space-between;
                            box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
                        `;
                        banner.innerHTML = `
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <i class="fas fa-archive" style="font-size: 24px;"></i>
                                <div>
                                    <div style="font-weight: 600; margin-bottom: 4px;">会话已归档</div>
                                    <div style="font-size: 13px; opacity: 0.9;">此会话为只读状态，无法添加新消息</div>
                                </div>
                            </div>
                            <button onclick="window.location.href='/dashboard.html'" style="background: white; color: #667eea; border: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; cursor: pointer;">
                                恢复会话
                            </button>
                        `;
                        messagesDiv.insertBefore(banner, messagesDiv.firstChild);
                    }
                }

                showNotification(`已加载：${conversation.title}`, 'success');
            } else {
                // ✅ 没有消息历史，显示欢迎界面（和新建会话一致）
                const messagesDiv = document.getElementById('chat-messages');
                if (messagesDiv) {
                    messagesDiv.innerHTML = `
                        <div class="message bot-message">
                            <div class="message-avatar">
                                <i class="fas fa-robot"></i>
                            </div>
                            <div class="message-content">
                                <p>你好！我是小You，你的智能旅行助手 ✨<br><br>我们可以聊聊：<br>🌍 目的地推荐<br>🎒 旅行攻略<br>💰 省钱技巧<br>🏛️ 景点介绍<br>🍜 美食推荐<br><br>想聊什么，尽管问我！</p>
                                <span class="message-time">刚刚</span>
                            </div>
                        </div>

                        <!-- 快捷选项 -->
                        <div class="quick-options">
                            <div class="quick-option" onclick="sendQuickMessageByMode('帮我规划云南之旅', 'chat')">
                                <i class="fas fa-mountain"></i>
                                <span>云南之旅</span>
                            </div>
                            <div class="quick-option" onclick="sendQuickMessageByMode('推荐成都美食攻略', 'chat')">
                                <i class="fas fa-utensils"></i>
                                <span>成都美食</span>
                            </div>
                            <div class="quick-option" onclick="sendQuickMessageByMode('预算2000元的国内穷游推荐', 'chat')">
                                <i class="fas fa-wallet"></i>
                                <span>穷游推荐</span>
                            </div>
                            <div class="quick-option" onclick="sendQuickMessageByMode('适合大学生的周边游', 'chat')">
                                <i class="fas fa-graduation-cap"></i>
                                <span>周边游</span>
                            </div>
                        </div>
                    `;
                }
                showNotification(`已切换到：${conversation.title}`, 'info');
            }

            // 更新列表高亮
            renderConversationList();
        } else {
            showNotification('加载会话失败', 'error');
        }
    } catch (error) {
        console.error('切换会话出错:', error);
        showNotification('切换会话失败', 'error');
    }
}

/**
 * 检测消息是否为表单生成的提示词
 * @param {string} content - 消息内容
 * @returns {boolean} 是否为表单提示词
 */
function isFormPromptMessage(content) {
    if (!content || typeof content !== 'string') return false;

    // 检测特征关键词（只有后端生成的提示词才包含）
    const keywords = [
        '⚠️ **核心约束**',
        '🚨 **输出语言规范**',
        '📝 **排版要求**',
        '穷游原则：高性价比、学生优惠、实用避坑',
        '严禁技术性说明'
    ];

    // 只要包含任一关键词，就认为是表单提示词
    return keywords.some(keyword => content.includes(keyword));
}

/**
 * 从表单提示词中提取简短摘要
 * @param {string} content - 完整的表单提示词
 * @returns {string} 提取的摘要信息
 */
function extractFormPromptSummary(content) {
    if (!content) return '📋 旅行规划表单提交';

    let summary = '📋 旅行规划表单提交\n';

    try {
        // 使用正则表达式提取关键信息
        const destination = content.match(/目的地[：:]\s*([^\n]+)/)?.[1]?.trim();
        const dateRange = content.match(/时间[：:]\s*([^\n]+)/)?.[1]?.trim();
        const days = content.match(/（(\d+)天）/)?.[1] || content.match(/(\d+)天/)?.[1];
        const travelers = content.match(/(\d+)人/)?.[1];
        const budget = content.match(/预算[：:]([^\n]+)/)?.[1]?.trim();

        // 拼接成简短摘要
        if (destination) summary += `📍 目的地：${destination}\n`;
        if (dateRange) summary += `📅 时间：${dateRange}\n`;
        if (days) summary += `⏰ 天数：${days}天\n`;
        if (travelers) summary += `👥 人数：${travelers}人\n`;
        if (budget) summary += `💰 预算：${budget}`;

        // 提取偏好信息
        const preferencesMatch = content.match(/偏好[：:]\s*([^\n]+)/)?.[1]?.trim();
        if (preferencesMatch) {
            summary += `\n🎯 偏好：${preferencesMatch}`;
        }
    } catch (e) {
        console.error('提取表单摘要失败:', e);
    }

    return summary;
}

/**
 * 渲染会话消息（分批异步渲染，避免阻塞UI）
 * @param {Array} messages - 消息列表
 */
function renderConversationMessages(messages) {
    const messagesDiv = document.getElementById('chat-messages');
    if (!messagesDiv) return;

    // ✅ 清空现有消息（包括快捷选项）
    messagesDiv.innerHTML = '';

    // ✅ 如果没有消息，直接返回
    if (!messages || messages.length === 0) {
        return;
    }

    // ✅ 显示加载提示
    const loadingHint = document.createElement('div');
    loadingHint.className = 'loading-hint';
    loadingHint.style.cssText = 'text-align: center; padding: 10px; color: #999; font-size: 14px;';
    loadingHint.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 正在加载历史消息...';
    messagesDiv.appendChild(loadingHint);

    // ✅ 过滤掉 system 消息（工具执行日志等，不需要显示给用户）
    const filteredMessages = messages.filter(msg => msg.role !== 'system');
    console.log(`📊 历史消息过滤: 原始 ${messages.length} 条 -> 过滤后 ${filteredMessages.length} 条`);

    // ✅ 分批渲染参数
    const BATCH_SIZE = 2;  // 每批渲染2条消息（旅行攻略内容较长）
    let currentIndex = 0;
    let imageHandlers = [];  // 收集图片错误处理器

    /**
     * 渲染单条消息
     */
    function renderSingleMessage(msg) {
        const messageDiv = document.createElement('div');
        messageDiv.className = msg.role === 'user' ? 'message user-message' : 'message bot-message';

        const avatarDiv = document.createElement('div');
        avatarDiv.className = 'message-avatar';
        avatarDiv.innerHTML = msg.role === 'user' ? '<i class="fas fa-user"></i>' : '<i class="fas fa-robot"></i>';

        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';

        if (msg.role === 'user') {
            // ✅ 智能过滤：检测并转换表单提示词
            let displayContent = msg.content;
            if (isFormPromptMessage(msg.content)) {
                console.log('🔍 检测到表单提示词，转换为简短摘要');
                displayContent = extractFormPromptSummary(msg.content);
            }

            // 用户消息：纯文本显示
            contentDiv.innerHTML = `
                <p>${escapeHtml(displayContent)}</p>
                <span class="message-time">${formatTime(msg.timestamp)}</span>
            `;
        } else {
            // Bot 消息：渲染 Markdown
            let renderedContent = msg.content;

            // 检查是否加载了 marked 库
            if (typeof marked !== 'undefined') {
                try {
                    // 配置 marked 选项
                    marked.setOptions({
                        breaks: true,      // 支持 GitHub 风格的换行
                        gfm: true,         // GitHub Flavored Markdown
                        tables: true,      // 支持表格
                        sanitize: false    // 我们手动用 DOMPurify 清理
                    });

                    // 渲染 Markdown
                    const rawHtml = marked.parse(renderedContent);

                    // 使用 DOMPurify 清理 HTML（防止 XSS）
                    if (typeof DOMPurify !== 'undefined') {
                        renderedContent = DOMPurify.sanitize(rawHtml);
                    } else {
                        renderedContent = rawHtml;
                    }
                } catch (e) {
                    console.error('Markdown 渲染失败:', e);
                    renderedContent = escapeHtml(msg.content);
                }
            } else {
                // 如果没有 marked 库，显示纯文本并转义
                renderedContent = escapeHtml(msg.content).replace(/\n/g, '<br>');
            }

            contentDiv.innerHTML = `
                <div class="markdown-body">${renderedContent}</div>
                <span class="message-time">${formatTime(msg.timestamp)}</span>
            `;

            // ✅ 收集图片错误处理器（稍后统一绑定）
            imageHandlers.push(() => {
                const images = messageDiv.querySelectorAll('.markdown-body img');
                images.forEach(img => {
                    img.addEventListener('error', function() {
                        this.style.display = 'none';
                        const placeholder = document.createElement('div');
                        placeholder.className = 'image-placeholder';
                        placeholder.innerHTML = `
                            <div style="padding: 2rem; text-align: center; background: #f6f8fa; border-radius: 6px; margin: 12px 0;">
                                <i class="fas fa-image" style="font-size: 2rem; color: #9ca3af; margin-bottom: 0.5rem;"></i>
                                <p style="color: #6a737d; font-size: 0.875rem;">图片加载失败</p>
                                <a href="${this.src}" target="_blank" style="color: #0969da; font-size: 0.75rem;">在新窗口打开</a>
                            </div>
                        `;
                        this.parentNode.insertBefore(placeholder, this);
                    });
                });
            });
        }

        messageDiv.appendChild(avatarDiv);
        messageDiv.appendChild(contentDiv);
        return messageDiv;
    }

    /**
     * 分批渲染函数
     */
    function renderBatch() {
        const endIndex = Math.min(currentIndex + BATCH_SIZE, filteredMessages.length);

        // 移除加载提示（第一批渲染前）
        if (currentIndex === 0 && loadingHint.parentNode) {
            loadingHint.remove();
        }

        // 渲染当前批次
        for (let i = currentIndex; i < endIndex; i++) {
            const messageDiv = renderSingleMessage(filteredMessages[i]);
            messagesDiv.appendChild(messageDiv);
        }

        currentIndex = endIndex;

        // 如果还有消息，使用 requestAnimationFrame 继续渲染下一批
        if (currentIndex < filteredMessages.length) {
            requestAnimationFrame(renderBatch);
        } else {
            // ✅ 全部渲染完成，绑定图片错误处理器
            imageHandlers.forEach(handler => handler());
            imageHandlers = [];

            // ✅ 滚动到底部（确保看到最新消息）
            messagesDiv.scrollTop = messagesDiv.scrollHeight;
        }
    }

    // ✅ 开始分批渲染
    requestAnimationFrame(renderBatch);
}

/**
 * 格式化日期
 * @param {string} dateString - 日期字符串
 * @returns {string} 格式化后的日期
 */
function formatDate(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;

    // 小于1小时
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return minutes < 1 ? '刚刚' : `${minutes}分钟前`;
    }

    // 今天
    if (date.toDateString() === now.toDateString()) {
        return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    }

    // 昨天
    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (date.toDateString() === yesterday.toDateString()) {
        return '昨天';
    }

    // 更早
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

/**
 * 格式化时间
 * @param {string} dateString - 日期字符串
 * @returns {string} 格式化后的时间
 */
function formatTime(dateString) {
    const date = new Date(dateString);
    return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

/**
 * HTML转义
 * @param {string} text - 文本
 * @returns {string} 转义后的文本
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ==================== 一键规划功能 ====================

/**
 * 从热门景点卡片一键规划
 * @param {string} destination - 目的地
 * @param {string} budget - 预算范围
 * @param {string} highlights - 亮点描述
 */
function quickPlan(destination, budget, highlights) {
    // 切换到表单模式
    switchMode('form');

    // 填充表单
    const destinationInput = document.getElementById('destination');
    const budgetInput = document.getElementById('budget');

    if (destinationInput) {
        destinationInput.value = destination;
    }

    if (budgetInput) {
        // 提取预算数字（取平均值）
        const budgetMatch = budget.match(/(\d+)-(\d+)/);
        if (budgetMatch) {
            const avgBudget = Math.floor((parseInt(budgetMatch[1]) + parseInt(budgetMatch[2])) / 2);
            budgetInput.value = avgBudget.toString();
        }
    }

    // ✅ 修改：从点击当天开始计算3天
    const today = new Date();
    const startDate = new Date(today);
    startDate.setDate(today.getDate());  // 今天开始
    const endDate = new Date(today);
    endDate.setDate(today.getDate() + 2);  // 今天+2天=共3天（今天、明天、后天）

    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');

    if (startDateInput) {
        startDateInput.value = formatDate(startDate);
    }
    if (endDateInput) {
        endDateInput.value = formatDate(endDate);
    }

    // ✅ 清空所有偏好选择（不添加任何偏好）
    const checkboxes = document.querySelectorAll('.preferences-grid input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            checkbox.checked = false;
        }
    });

    // 更新偏好计数显示
    updatePreferenceCount();

    // ✅ 将亮点描述填充到"其他要求"字段
    const requirementsInput = document.getElementById('requirements');
    if (requirementsInput && highlights) {
        requirementsInput.value = `想体验：${highlights}`;
    }

    // ❌ 移除滚动操作，避免导致布局问题
    // const formSection = document.querySelector('.travel-planning-form');
    // if (formSection) {
    //     formSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
    // }

    // 显示提示
    showNotification(`✅ 已为您设置 ${destination} 的3天穷游行程（从今天开始，${today.toLocaleDateString('zh-CN')} 至 ${endDate.toLocaleDateString('zh-CN')}），点击"开始规划"即可生成攻略！`, 'success');

    // 可选：自动打开对话模式并发送消息
    // setTimeout(() => {
    //     const message = `帮我规划${destination}之旅，预算${budget}，想玩：${highlights}`;
    //     sendChatAIMessageWithText(message);
    // }, 500);
}

/**
 * 格式化日期为 YYYY-MM-DD
 * 支持多种输入格式：Date对象、ISO字符串、时间戳
 */
function formatDate(date) {
    // 处理 null/undefined
    if (!date) {
        return '未知日期';
    }

    // 如果是字符串，转换为 Date 对象
    let dateObj;
    if (typeof date === 'string') {
        // 尝试解析 ISO 格式字符串 (如 "2025-01-15T10:30:00")
        dateObj = new Date(date);
    } else if (date instanceof Date) {
        dateObj = date;
    } else if (typeof date === 'number') {
        // 时间戳
        dateObj = new Date(date);
    } else {
        return '无效日期';
    }

    // 检查日期是否有效
    if (isNaN(dateObj.getTime())) {
        return '无效日期';
    }

    const year = dateObj.getFullYear();
    const month = String(dateObj.getMonth() + 1).padStart(2, '0');
    const day = String(dateObj.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
}

// ==================== AI进度条管理（方案1：简约卡片风格）====================

/**
 * AI进度条管理类
 */
class AIProgressManager {
    constructor() {
        this.progressCard = document.getElementById('aiProgressCard');
        this.progressFill = document.getElementById('aiProgressFill');
        this.progressPercent = document.getElementById('aiProgressPercent');
        this.progressTitle = document.querySelector('.ai-progress-title');

        this.currentProgress = 0;
        this.progressInterval = null;
        this.baseSpeed = 0.5; // 基础速度（每次增加的百分比）
        this.randomOffset = 0; // 随机偏移量
        this.isActive = false;

        console.log('✅ AI进度管理器已初始化');
    }

    /**
     * 显示进度条（AI开始运行时调用）
     */
    show() {
        if (!this.progressCard) {
            console.error('❌ AI进度条元素未找到');
            return;
        }

        // 重置状态
        this.reset();
        this.isActive = true;

        // 生成随机偏移量（0.3 - 0.8之间，让每次速度不同）
        this.randomOffset = 0.3 + Math.random() * 0.5;

        // 显示进度条
        this.progressCard.style.display = 'block';
        this.progressCard.classList.remove('completed');

        console.log('🔔 AI进度条已显示');
    }

    /**
     * 隐藏进度条（AI回答完成时调用）
     */
    hide() {
        if (!this.progressCard || !this.isActive) {
            return;
        }

        this.isActive = false;

        // 停止进度更新
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }

        // 显示完成状态
        this.progressFill.style.width = '100%';
        this.progressPercent.textContent = '100%';
        this.progressTitle.textContent = '✅ 思考完成！';
        this.progressCard.classList.add('completed');

        // 3秒后隐藏
        setTimeout(() => {
            if (this.progressCard) {
                this.progressCard.style.display = 'none';
                this.reset();
            }
        }, 3000);

        console.log('✅ AI进度条已完成并隐藏');
    }

    /**
     * 开始进度动画
     */
    startProgress() {
        if (this.progressInterval) {
            clearInterval(this.progressInterval);
        }

        // 每200ms更新一次进度
        this.progressInterval = setInterval(() => {
            this.updateProgress();
        }, 200);

        console.log('⏳ AI进度动画已开始');
    }

    /**
     * 更新进度（带随机性）
     */
    updateProgress() {
        if (!this.isActive || this.currentProgress >= 99) {
            return;
        }

        // 计算新的进度值（基础速度 + 随机波动）
        const increment = this.baseSpeed + (Math.random() - 0.5) * this.randomOffset;
        this.currentProgress = Math.min(99, this.currentProgress + increment);

        // 更新UI
        this.progressFill.style.width = `${this.currentProgress}%`;
        this.progressPercent.textContent = `${Math.round(this.currentProgress)}%`;

        // 动态更新标题文字
        if (this.currentProgress < 30) {
            this.progressTitle.textContent = '🤔 小You正在思考...';
        } else if (this.currentProgress < 60) {
            this.progressTitle.textContent = '🔍 小You正在搜索...';
        } else if (this.currentProgress < 90) {
            this.progressTitle.textContent = '✨ 小You正在整理...';
        } else {
            this.progressTitle.textContent = '🎯 小You正在完善...';
        }
    }

    /**
     * 重置进度条状态
     */
    reset() {
        this.currentProgress = 0;
        this.progressFill.style.width = '0%';
        this.progressPercent.textContent = '0%';
        this.progressTitle.textContent = '🤔 小You正在思考...';
        this.progressCard.classList.remove('completed');

        if (this.progressInterval) {
            clearInterval(this.progressInterval);
            this.progressInterval = null;
        }
    }
}

// 创建全局进度管理器实例
const aiProgressManager = new AIProgressManager();

// ==================== 页面加载时初始化 ====================
document.addEventListener('DOMContentLoaded', function() {
    // 原有初始化代码...
    initializeTabs();
    initializeScrollEffects();
    checkUserSession();
    initializeCarousel();

    // 新增：初始化会话管理
    initializeConversationManagement();
});
