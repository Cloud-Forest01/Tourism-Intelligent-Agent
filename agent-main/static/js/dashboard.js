/**
 * 用户仪表板 JavaScript - 智慧旅行 Agent
 * 处理会话列表、创建会话、用户信息等
 */

// ========== 全局变量 ==========
const API_BASE_URL = window.location.origin;
let currentUser = null;
let currentFilter = 'active';
let conversations = [];
let currentSearchKeyword = ''; // ✅ 新增：当前搜索关键词

// ========== 页面加载完成 ==========
document.addEventListener('DOMContentLoaded', async function() {
    // 加载用户信息
    await loadUserInfo();

    // 加载会话列表（传入当前过滤器）
    await loadConversations(currentFilter);

    // 绑定事件
    bindEvents();
});

// ========== 加载用户信息 ==========
async function loadUserInfo() {
    const token = localStorage.getItem('access_token');
    if (!token) {
        window.location.href = '/auth.html';
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            currentUser = await response.json();

            // 保存用户信息到 localStorage
            const userInfoToSave = {
                user_id: currentUser.user_id,
                username: currentUser.username,
                nickname: currentUser.nickname,
                email: currentUser.email,
                avatar_url: currentUser.avatar_url
            };
            localStorage.setItem('user_info', JSON.stringify(userInfoToSave));

            console.log('用户信息已保存到localStorage:', userInfoToSave);

            updateUserInfoUI();

            // 加载会话列表
            await loadConversations(currentFilter);
        } else {
            // Token 无效，跳转登录
            logout();
        }
    } catch (error) {
        console.error('加载用户信息失败:', error);
        showToast('error', '加载失败', '无法加载用户信息');
    }
}

// ========== 更新用户信息 UI ==========
function updateUserInfoUI() {
    if (!currentUser) return;

    // 📊 从实际会话数据中统计（使用全局变量）
    const allConvs = window.allConversationsData || [];

    const activeCount = allConvs.filter(c =>
        c.status === 'active' || (!c.status && c.status !== 'archived' && c.status !== 'deleted')
    ).length;
    const archivedCount = allConvs.filter(c => c.status === 'archived').length;
    const deletedCount = allConvs.filter(c => c.status === 'deleted').length;  // ✅ 添加已删除统计
    const totalCount = allConvs.length;

    document.getElementById('activeConversations').textContent =
        `${activeCount}/${currentUser.max_conversations || 10}`;
    document.getElementById('totalPlans').textContent = totalCount;
    document.getElementById('archivedConversations').textContent = archivedCount;
    document.getElementById('deletedConversations').textContent = deletedCount;  // ✅ 更新已删除数量

    // 🌍 热门目的地 - 从实际会话中提取
    const destinations = {};
    allConvs.forEach(conv => {
        if (conv.destination) {
            destinations[conv.destination] = (destinations[conv.destination] || 0) + 1;
        }
    });

    // 按访问次数排序，取前5个
    const sortedDestinations = Object.entries(destinations)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([dest]) => dest);

    const tagsContainer = document.getElementById('favoriteDestinations');
    if (sortedDestinations.length > 0) {
        tagsContainer.innerHTML = sortedDestinations.map(dest =>
            `<span class="tag">${escapeHtml(dest)}</span>`
        ).join('');
    } else {
        tagsContainer.innerHTML = '<span class="tag-muted">暂无数据</span>';
    }

    console.log('📊 统计概览已更新:', {
        active: activeCount,
        archived: archivedCount,
        deleted: deletedCount,  // ✅ 添加已删除日志
        total: totalCount,
        destinations: sortedDestinations
    });
}

// ========== 加载会话列表 ==========
async function loadConversations(filter = 'active') {
    const token = localStorage.getItem('access_token');
    if (!token) return;

    try {
        // 从用户信息中获取user_id
        const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
        const userId = userInfo.user_id;

        if (!userId) {
            showToast('error', '未找到用户信息', '请重新登录');
            return;
        }

        const response = await fetch(
            `${API_BASE_URL}/api/conversations?user_id=${encodeURIComponent(userId)}`,
            {
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            }
        );

        if (response.ok) {
            const data = await response.json();
            console.log('会话列表完整响应:', data);  // 调试日志
            console.log('data.data:', data.data);  // 调试日志
            console.log('data.data.conversations:', data.data?.conversations);  // 调试日志

            const allConversations = data.data?.conversations || [];
            console.log('会话数量:', allConversations.length);  // 调试日志

            // 保存所有会话到全局变量（用于统计概览）
            window.allConversationsData = allConversations;

            // 根据状态筛选会话
            if (filter === 'active') {
                conversations = allConversations.filter(conv => conv.status !== 'archived' && conv.status !== 'deleted');
            } else if (filter === 'archived') {
                conversations = allConversations.filter(conv => conv.status === 'archived');
            } else if (filter === 'deleted') {
                conversations = allConversations.filter(conv => conv.status === 'deleted');
            } else {
                conversations = allConversations;
            }

            console.log('筛选后会话数量:', conversations.length);  // 调试日志
            renderConversations(conversations);
            updateEmptyState();
            updateUserInfoUI(); // ✅ 更新统计概览
        } else {
            console.error('API响应错误:', response.status);
            showToast('error', '加载失败', '无法加载会话列表');
        }
    } catch (error) {
        console.error('加载会话失败:', error);
        showToast('error', '网络错误', '请检查网络连接');
    }
}

// ========== 渲染会话列表 ==========
async function renderConversations(convs) {
    const container = document.getElementById('conversationsList');

    console.log('渲染会话列表:', convs);  // 调试日志

    if (!convs || convs.length === 0) {
        container.innerHTML = '';
        // ✅ 使用统一的空状态更新函数
        updateEmptyState();
        return;
    }

    // ✅ 隐藏空状态
    const emptyState = document.getElementById('emptyState');
    if (emptyState) {
        emptyState.style.display = 'none';
    }

    // 如果是已删除状态，需要获取过期信息
    let expirationData = {};
    if (currentFilter === 'deleted') {
        expirationData = await loadExpirationInfo(convs);
    }

    container.innerHTML = convs.map(conv => {
        // 后端返回的字段映射
        const convId = conv.id || conv.conversation_id || '';
        const title = conv.title || conv.destination || '未命名会话';
        const destination = conv.destination || '未知目的地';
        const updatedAt = conv.updated_at || conv.date || new Date().toISOString();
        const messageCount = conv.message_count || 0;

        // 默认状态为active（后端没有返回status字段）
        const status = conv.status || 'active';

        console.log('渲染会话:', { convId, title, status, destination });  // 调试日志

        // 根据状态决定显示哪些操作按钮
        let actionButtons = '';
        if (status === 'archived') {
            // 归档状态：显示恢复、导出、删除按钮
            actionButtons = `
                <button class="conv-action-btn" onclick="event.stopPropagation(); exportConversation('${convId}', '${escapeHtml(title)}')" title="导出会话">
                    <i class="fas fa-download"></i>
                </button>
                <button class="conv-action-btn success" onclick="event.stopPropagation(); restoreConversation('${convId}')" title="恢复会话">
                    <i class="fas fa-box-open"></i>
                </button>
                <button class="conv-action-btn danger" onclick="event.stopPropagation(); deleteConversation('${convId}')" title="删除">
                    <i class="fas fa-trash"></i>
                </button>
            `;
        } else if (status === 'deleted') {
            // 已删除状态：显示恢复、永久删除按钮
            actionButtons = `
                <button class="conv-action-btn success" onclick="event.stopPropagation(); restoreConversation('${convId}')" title="恢复会话">
                    <i class="fas fa-undo"></i>
                </button>
                <button class="conv-action-btn danger" onclick="event.stopPropagation(); deleteConversation('${convId}')" title="永久删除">
                    <i class="fas fa-trash-alt"></i>
                </button>
            `;
        } else {
            // 活跃状态：显示导出、重命名、归档、删除按钮
            actionButtons = `
                <button class="conv-action-btn" onclick="event.stopPropagation(); exportConversation('${convId}', '${escapeHtml(title)}')" title="导出会话">
                    <i class="fas fa-download"></i>
                </button>
                <button class="conv-action-btn" onclick="event.stopPropagation(); showRenameModal('${convId}', '${escapeHtml(title)}')" title="重命名">
                    <i class="fas fa-edit"></i>
                </button>
                <button class="conv-action-btn warning" onclick="event.stopPropagation(); archiveConversation('${convId}')" title="归档">
                    <i class="fas fa-archive"></i>
                </button>
                <button class="conv-action-btn danger" onclick="event.stopPropagation(); deleteConversation('${convId}')" title="删除">
                    <i class="fas fa-trash"></i>
                </button>
            `;
        }

        // 添加过期警告（仅deleted状态）
        let expirationWarning = '';
        if (status === 'deleted' && expirationData[convId]) {
            const expInfo = expirationData[convId];
            const daysRemaining = expInfo.days_remaining;
            const deleteDate = expInfo.will_be_deleted_on;

            if (daysRemaining <= 1) {
                expirationWarning = `
                    <div class="conv-expiration-warning urgent">
                        <i class="fas fa-exclamation-triangle"></i>
                        <span>即将在24小时内永久删除</span>
                    </div>
                `;
            } else if (daysRemaining <= 3) {
                expirationWarning = `
                    <div class="conv-expiration-warning warning">
                        <i class="fas fa-clock"></i>
                        <span>剩余${daysRemaining}天将被删除（${deleteDate}）</span>
                    </div>
                `;
            } else {
                expirationWarning = `
                    <div class="conv-expiration-warning info">
                        <i class="fas fa-info-circle"></i>
                        <span>剩余${daysRemaining}天将被删除（${deleteDate}）</span>
                    </div>
                `;
            }
        }

        return `
        <div class="conversation-card ${status}" data-id="${convId}" onclick="openConversation('${convId}')" data-status="${status}">
            <div class="conv-actions">
                ${actionButtons}
            </div>
            <div class="conv-header">
                <div>
                    <h3 class="conv-title">${escapeHtml(title)}</h3>
                    <div class="conv-destination">
                        <i class="fas fa-map-marker-alt"></i>
                        ${escapeHtml(destination)}
                    </div>
                </div>
                <span class="conv-badge ${status}">${getStatusText(status)}</span>
            </div>
            ${expirationWarning}
            <div class="conv-meta">
                <div class="conv-meta-item">
                    <i class="fas fa-comment"></i>
                    <span>${messageCount} 条消息</span>
                </div>
                <div class="conv-meta-item">
                    <i class="fas fa-clock"></i>
                    <span>${formatDate(updatedAt)}</span>
                </div>
            </div>
        </div>
        `;
    }).join('');
}

// ========== 加载过期信息 ==========
async function loadExpirationInfo(convs) {
    const token = localStorage.getItem('access_token');
    const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
    const userId = userInfo.user_id;

    const expirationData = {};

    // 并发获取所有会话的过期信息
    const promises = convs.map(async (conv) => {
        const convId = conv.id || conv.conversation_id;
        try {
            const response = await fetch(
                `${API_BASE_URL}/api/conversations/${convId}/expiration?user_id=${encodeURIComponent(userId)}`,
                {
                    headers: {
                        'Authorization': `Bearer ${token}`
                    }
                }
            );

            if (response.ok) {
                const data = await response.json();
                if (data.success && data.data) {
                    expirationData[convId] = data.data;
                }
            }
        } catch (error) {
            console.error(`获取会话 ${convId} 过期信息失败:`, error);
        }
    });

    await Promise.all(promises);
    return expirationData;
}

// ========== 更新空状态 ==========
function updateEmptyState(searchKeyword = null) {
    const emptyState = document.getElementById('emptyState');
    const container = document.getElementById('conversationsList');
    const emptyTitle = document.getElementById('emptyStateTitle');
    const emptyMessage = document.getElementById('emptyStateMessage');
    const emptyBtn = document.getElementById('emptyStateBtn');

    const keyword = searchKeyword !== null ? searchKeyword : currentSearchKeyword;
    const hasResults = container.children.length > 0;

    if (!hasResults) {
        emptyState.style.display = 'block';

        // 根据是否有搜索关键词显示不同的提示
        if (keyword) {
            // 搜索无结果
            if (emptyTitle) emptyTitle.textContent = '未找到匹配的会话';
            if (emptyMessage) emptyMessage.textContent = `没有找到包含 "${escapeHtml(keyword)}" 的会话，请尝试其他关键词`;
            if (emptyBtn) emptyBtn.style.display = 'none';
        } else {
            // 没有会话 - 根据当前过滤器显示不同的提示
            if (currentFilter === 'deleted') {
                // 回收站为空
                if (emptyTitle) emptyTitle.textContent = '回收站为空';
                if (emptyMessage) emptyMessage.textContent = '回收站中没有待删除的会话';
                if (emptyBtn) emptyBtn.style.display = 'none'; // 回收站不显示新建按钮
            } else if (currentFilter === 'archived') {
                // 归档为空
                if (emptyTitle) emptyTitle.textContent = '暂无归档会话';
                if (emptyMessage) emptyMessage.textContent = '您还没有归档任何会话';
                if (emptyBtn) emptyBtn.style.display = 'none'; // 归档不显示新建按钮
            } else {
                // 活跃会话为空
                if (emptyTitle) emptyTitle.textContent = '暂无会话';
                if (emptyMessage) emptyMessage.textContent = '点击"新建会话"开始规划您的旅行';
                if (emptyBtn) emptyBtn.style.display = 'inline-block';
            }
        }
    } else {
        emptyState.style.display = 'none';
    }
}

// ========== 获取状态文本 ==========
function getStatusText(status) {
    const statusMap = {
        'active': '活跃',
        'archived': '已归档',
        'deleted': '回收站'
    };
    return statusMap[status] || status;
}

// ========== 格式化日期 ==========
function formatDate(dateString) {
    if (!dateString) return '未知时间';

    const date = new Date(dateString);
    const now = new Date();
    const diff = now - date;

    // 小于1小时
    if (diff < 3600000) {
        const minutes = Math.floor(diff / 60000);
        return minutes === 0 ? '刚刚' : `${minutes} 分钟前`;
    }

    // 小于1天
    if (diff < 86400000) {
        const hours = Math.floor(diff / 3600000);
        return `${hours} 小时前`;
    }

    // 小于7天
    if (diff < 604800000) {
        const days = Math.floor(diff / 86400000);
        return `${days} 天前`;
    }

    // 显示完整日期
    return date.toLocaleDateString('zh-CN', {
        year: 'numeric',
        month: 'long',
        day: 'numeric'
    });
}

// ========== 绑定事件 ==========
function bindEvents() {
    // 过滤器按钮
    document.querySelectorAll('.filter-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            currentFilter = this.dataset.filter;
            loadConversations(currentFilter);
        });
    });

    // 搜索框
    const searchInput = document.getElementById('searchInput');
    const searchClear = document.getElementById('searchClear');
    const searchBtn = document.getElementById('searchBtn'); // ✅ 新增：搜索按钮
    let clearSearchBtn = document.getElementById('clearSearchBtn');

    // ✅ 输入时自动搜索（防抖）
    if (searchInput) {
        searchInput.addEventListener('input', debounce(function() {
            const keyword = searchInput.value.trim();  // ✅ 使用外部变量而不是this
            handleSearch(keyword);
        }, 300));
    }

    // ✅ 新增：点击搜索按钮执行搜索
    if (searchBtn) {
        searchBtn.addEventListener('click', function() {
            const keyword = searchInput.value.trim();
            handleSearch(keyword);
            // 添加视觉反馈
            searchBtn.style.transform = 'translateY(-50%) scale(0.95)';
            setTimeout(() => {
                searchBtn.style.transform = 'translateY(-50%) scale(1)';
            }, 150);
        });
    }

    // ✅ 新增：按回车键执行搜索
    if (searchInput) {
        searchInput.addEventListener('keypress', function(event) {
            if (event.key === 'Enter') {
                const keyword = searchInput.value.trim();
                handleSearch(keyword);
                if (searchBtn) {
                    searchBtn.click(); // 触发按钮点击动画
                }
            }
        });
    }

    // ✅ 清空按钮事件（搜索框内的X）
    if (searchClear) {
        searchClear.addEventListener('click', function() {
            clearSearch();
        });
    }

    // ✅ 使用事件委托处理清除搜索链接（因为按钮会被动态重建）
    document.addEventListener('click', function(event) {
        if (event.target.id === 'clearSearchBtn' ||
            event.target.classList.contains('clear-search-link')) {
            event.preventDefault();
            clearSearch();
        }
    });
}

// ========== ✅ 重构：处理搜索（跨所有状态搜索）==========
function handleSearch(keyword) {
    currentSearchKeyword = keyword;
    const searchClear = document.getElementById('searchClear');
    const searchResultsCount = document.getElementById('searchResultsCount');

    // 显示/隐藏清空按钮
    if (searchClear) {
        searchClear.style.display = keyword ? 'flex' : 'none';
    }

    // 执行过滤
    if (!keyword) {
        // 清空搜索，恢复当前标签的会话
        renderConversations(conversations);
        updateEmptyState();

        // 隐藏搜索结果计数
        if (searchResultsCount) {
            searchResultsCount.style.display = 'none';
        }
        return;
    }

    // ✅ 关键改进：从全局所有会话中搜索，而不是仅当前标签
    const allConversations = window.allConversationsData || [];

    // 过滤会话 - 搜索标题和目的地
    const filtered = allConversations.filter(conv => {
        const titleMatch = conv.title && conv.title.toLowerCase().includes(keyword.toLowerCase());
        const destinationMatch = conv.destination && conv.destination.toLowerCase().includes(keyword.toLowerCase());
        return titleMatch || destinationMatch;
    });

    console.log(`🔍 搜索 "${keyword}":`, {
        '总会话数': allConversations.length,
        '当前标签会话数': conversations.length,
        '搜索结果数': filtered.length,
        '搜索结果状态分布': filtered.reduce((acc, conv) => {
            acc[conv.status || 'active'] = (acc[conv.status || 'active'] || 0) + 1;
            return acc;
        }, {})
    });

    // 渲染结果
    renderConversations(filtered);

    // 显示搜索结果计数（包含状态分布信息）
    if (searchResultsCount) {
        searchResultsCount.style.display = 'flex';

        // 如果有结果，显示状态分布提示
        if (filtered.length > 0) {
            const statusCount = filtered.reduce((acc, conv) => {
                const status = conv.status || 'active';
                acc[status] = (acc[status] || 0) + 1;
                return acc;
            }, {});

            // 更新搜索结果提示文本
            const statusText = Object.entries(statusCount)
                .map(([status, count]) => {
                    const statusName = status === 'active' ? '活跃' :
                                     status === 'archived' ? '归档' : '回收站';
                    return `${statusName}${count}个`;
                })
                .join('、');

            searchResultsCount.innerHTML = `
                <i class="fas fa-search"></i>
                找到 <strong>${filtered.length}</strong> 个结果
                <span style="margin-left: 8px; color: #666; font-size: 14px;">(${statusText})</span>
                <button class="clear-search-link" id="clearSearchBtn">清除搜索</button>
            `;
        } else {
            // 无结果时也显示计数（0）
            searchResultsCount.innerHTML = `
                <i class="fas fa-search"></i>
                找到 <strong>0</strong> 个结果
                <button class="clear-search-link" id="clearSearchBtn">清除搜索</button>
            `;
        }
    }

    // 更新空状态
    updateEmptyState(keyword);
}

// ========== ✅ 改进：清除搜索（恢复到当前标签）==========
function clearSearch() {
    const searchInput = document.getElementById('searchInput');
    const searchClear = document.getElementById('searchClear');
    const searchResultsCount = document.getElementById('searchResultsCount');

    // 清空搜索框
    if (searchInput) {
        searchInput.value = '';
    }

    // 隐藏清空按钮
    if (searchClear) {
        searchClear.style.display = 'none';
    }

    // 隐藏搜索结果计数
    if (searchResultsCount) {
        searchResultsCount.style.display = 'none';
        // 恢复原始HTML结构（以便后续动态更新）
        searchResultsCount.innerHTML = `
            <i class="fas fa-search"></i>
            找到 <strong id="resultsCount">0</strong> 个结果
            <button class="clear-search-link" id="clearSearchBtn">清除搜索</button>
        `;
    }

    // 清空关键词
    currentSearchKeyword = '';

    // 重新显示当前标签的所有会话（保持当前过滤器状态）
    loadConversations(currentFilter);
}

// ========== 过滤会话（保留原函数以兼容）==========
function filterConversations(keyword) {
    handleSearch(keyword);
}

// ========== 防抖函数 ==========
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

// ========== 打开会话 ==========
function openConversation(conversationId) {
    // 检查会话状态
    const allConversations = window.allConversationsData || [];
    const conversation = allConversations.find(c => (c.id || c.conversation_id) === conversationId);

    if (conversation) {
        const status = conversation.status || 'active';

        // 如果是已删除状态的会话，提示用户需要先恢复
        if (status === 'deleted') {
            showToast('warning', '无法打开', '该会话在回收站中，请先恢复后再打开');
            return;
        }

        // 如果是已归档状态的会话，提示用户
        if (status === 'archived') {
            showToast('info', '会话已归档', '正在打开已归档的会话...');
        }
    }

    // 跳转到规划页面，并带上会话ID
    window.location.href = `/?conversation=${conversationId}`;
}

// ========== 归档会话 ==========
async function archiveConversation(conversationId) {
    if (!confirm('确定要归档此会话吗？')) return;

    const token = localStorage.getItem('access_token');
    const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
    const userId = userInfo.user_id;

    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}/archive?user_id=${encodeURIComponent(userId)}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            showToast('success', '归档成功', '会话已归档');
            await loadConversations(currentFilter);
        } else {
            const data = await response.json();
            showToast('error', '归档失败', data.message || '操作失败');
        }
    } catch (error) {
        showToast('error', '网络错误', '请检查网络连接');
    }
}

// ========== 删除会话 ==========
async function deleteConversation(conversationId) {
    const status = currentFilter;

    console.log('🔍 当前过滤器:', status);  // 调试日志
    console.log('🔍 会话ID:', conversationId);  // 调试日志

    // 根据当前状态显示不同的确认提示
    let confirmMessage = '';
    if (status === 'deleted') {
        confirmMessage = '确定要永久删除此会话吗？此操作不可恢复！';
    } else {
        confirmMessage = '确定要删除此会话吗？删除后可在"回收站"中恢复（保留7天）';
    }

    if (!confirm(confirmMessage)) return;

    const token = localStorage.getItem('access_token');
    const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
    const userId = userInfo.user_id;

    try {
        // 构建删除URL
        let deleteUrl = `${API_BASE_URL}/api/conversations/${conversationId}?user_id=${encodeURIComponent(userId)}`;

        // 如果是在"已删除"标签下，则是永久删除
        if (status === 'deleted') {
            deleteUrl += '&permanently=true';
            console.log('🗑️ 永久删除会话:', conversationId);  // 调试日志
        } else {
            console.log('📦 软删除会话:', conversationId);  // 调试日志
        }

        console.log('删除URL:', deleteUrl);  // 调试日志

        const response = await fetch(deleteUrl, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const successMessage = status === 'deleted'
                ? '会话已永久删除'
                : '会话已移至回收站，可在"回收站"中恢复（7天后自动清理）';

            showToast('success', '删除成功', successMessage);
            await loadConversations(currentFilter);

            // 更新用户信息
            await loadUserInfo();
        } else {
            const data = await response.json();
            showToast('error', '删除失败', data.message || '操作失败');
        }
    } catch (error) {
        console.error('删除会话失败:', error);
        showToast('error', '网络错误', '请检查网络连接');
    }
}

// ========== 恢复会话 ==========
async function restoreConversation(conversationId) {
    if (!confirm('确定要恢复此会话吗？')) return;

    const token = localStorage.getItem('access_token');
    const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
    const userId = userInfo.user_id;

    if (!userId) {
        showToast('error', '恢复失败', '未找到用户信息，请重新登录');
        return;
    }

    try {
        // 修复：添加 user_id 作为 Query 参数
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}/restore?user_id=${encodeURIComponent(userId)}`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            showToast('success', '恢复成功', '会话已恢复到活跃列表');
            await loadConversations('active');
            // 更新用户信息
            await loadUserInfo();
        } else {
            const data = await response.json();
            showToast('error', '恢复失败', data.message || '操作失败');
        }
    } catch (error) {
        console.error('恢复会话错误:', error);
        showToast('error', '网络错误', '请检查网络连接');
    }
}

// ========== 重命名会话模态框 ==========
let currentRenameId = null;

function showRenameModal(conversationId, currentTitle) {
    currentRenameId = conversationId;

    // 创建重命名模态框
    const modalHtml = `
        <div class="modal" id="renameModal" style="display: flex;">
            <div class="modal-overlay" onclick="closeRenameModal()"></div>
            <div class="modal-content small">
                <div class="modal-header">
                    <h3><i class="fas fa-edit"></i> 重命名</h3>
                    <button class="modal-close" onclick="closeRenameModal()">
                        <i class="fas fa-times"></i>
                    </button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label for="newTitle">会话标题</label>
                        <input type="text" id="newTitle" class="form-control" value="${currentTitle}" placeholder="输入新的标题">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" onclick="closeRenameModal()">取消</button>
                    <button class="btn btn-primary" onclick="submitRename()">保存</button>
                </div>
            </div>
        </div>
    `;

    // 移除旧模态框
    const oldModal = document.getElementById('renameModal');
    if (oldModal) oldModal.remove();

    // 添加新模态框
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // 聚焦输入框
    const input = document.getElementById('newTitle');
    if (input) {
        input.focus();
        input.select();
    }
}

// ========== 关闭重命名模态框 ==========
function closeRenameModal() {
    const modal = document.getElementById('renameModal');
    if (modal) modal.remove();
    currentRenameId = null;
}

// ========== 提交重命名 ==========
async function submitRename() {
    if (!currentRenameId) return;

    const newTitle = document.getElementById('newTitle').value.trim();
    if (!newTitle) {
        alert('请输入会话标题');
        return;
    }

    const token = localStorage.getItem('access_token');
    const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
    const userId = userInfo.user_id;

    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations/${currentRenameId}/rename`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                user_id: userId,
                new_title: newTitle
            })
        });

        if (response.ok) {
            showToast('success', '重命名成功', '会话标题已更新');
            closeRenameModal();
            await loadConversations(currentFilter);
        } else {
            const data = await response.json();
            showToast('error', '重命名失败', data.message || '操作失败');
        }
    } catch (error) {
        showToast('error', '网络错误', '请检查网络连接');
    }
}

// ========== 导出会话 ==========
async function exportConversation(conversationId, title) {
    const token = localStorage.getItem('access_token');
    if (!token) {
        showToast('error', '未登录', '请先登录');
        return;
    }

    try {
        // 获取会话详情
        const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
        const userId = userInfo.user_id;

        const [convResponse, msgResponse] = await Promise.all([
            fetch(`${API_BASE_URL}/api/conversations/${conversationId}?user_id=${encodeURIComponent(userId)}`, {
                headers: { 'Authorization': `Bearer ${token}` }
            }),
            fetch(`${API_BASE_URL}/api/conversations/${conversationId}/messages?limit=100&offset=0`, {
                headers: { 'Authorization': `Bearer ${token}` }
            })
        ]);

        if (!convResponse.ok || !msgResponse.ok) {
            showToast('error', '导出失败', '无法获取会话数据');
            return;
        }

        const convData = await convResponse.json();
        const msgData = await msgResponse.json();

        const conversation = convData.data.conversation;
        const messages = msgData.data.messages || [];

        // 构建导出内容
        let content = `旅行规划会话导出\n`;
        content += `${'='.repeat(50)}\n\n`;
        content += `会话标题: ${conversation.title || title}\n`;
        content += `目的地: ${conversation.destination || '未知'}\n`;
        content += `创建时间: ${formatDate(conversation.created_at)}\n`;
        content += `消息数量: ${messages.length} 条\n`;
        content += `\n${'='.repeat(50)}\n\n`;

        // 添加旅行偏好
        if (conversation.trip_preferences) {
            const prefs = conversation.trip_preferences;
            content += `📋 旅行偏好\n`;
            content += `${'-'.repeat(30)}\n`;
            if (prefs.destination) content += `目的地: ${prefs.destination}\n`;
            if (prefs.start_date && prefs.end_date) {
                content += `时间: ${prefs.start_date} 至 ${prefs.end_date}\n`;
            }
            if (prefs.days_count) content += `天数: ${prefs.days_count}天\n`;
            if (prefs.travelers) content += `人数: ${prefs.travelers}人\n`;
            if (prefs.budget) content += `预算: ${prefs.budget}元\n`;
            if (prefs.selected_preferences && prefs.selected_preferences.length > 0) {
                content += `偏好: ${prefs.selected_preferences.join('、')}\n`;
            }
            content += `\n${'='.repeat(50)}\n\n`;
        }

        // 添加对话内容
        content += `💬 对话记录\n`;
        content += `${'='.repeat(50)}\n\n`;

        // 用于重新编号的计数器
        let displayIndex = 0;

        messages.forEach((msg) => {
            // ✅ 过滤掉 system 角色的消息（工具调用日志、系统消息等）
            if (msg.role === 'system') return;

            // ✅ 过滤掉包含工具调用日志的 AI 消息
            if (msg.role === 'assistant' && isToolExecutionLog(msg.content)) return;

            displayIndex++;
            const role = msg.role === 'user' ? '用户' : 'AI助手';
            const timestamp = msg.timestamp ? formatDate(msg.timestamp) : '未知时间';

            content += `[${displayIndex}] ${role} (${timestamp})\n`;
            content += `${'-'.repeat(30)}\n`;

            // 检测并过滤表单提示词
            let displayContent = msg.content;
            if (msg.role === 'user' && isFormPromptMessage(msg.content)) {
                displayContent = extractFormPromptSummary(msg.content);
            }

            content += `${displayContent}\n\n`;
        });

        content += `\n${'='.repeat(50)}\n`;
        content += `导出时间: ${new Date().toLocaleString('zh-CN')}\n`;

        // 创建下载
        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `旅行会话_${title}_${new Date().toISOString().slice(0, 10)}.txt`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast('success', '导出成功', '会话已导出为TXT文件');
    } catch (error) {
        console.error('导出会话失败:', error);
        showToast('error', '导出失败', '请稍后重试');
    }
}

// 检测消息是否为工具调用日志（需要过滤掉）
function isToolExecutionLog(content) {
    if (!content || typeof content !== 'string') return false;

    // 工具调用日志的特征关键词
    const toolLogPatterns = [
        '执行步骤',
        '工具:',
        '工具名称',
        '"status":',
        '"geocodes":',
        '"pois":',
        '"forecasts":',
        '"infocode":',
        '"success": true',
        '"success":false'
    ];

    // 如果内容以"执行步骤"开头，且包含多个JSON特征，则判定为工具日志
    if (content.startsWith('执行步骤')) {
        const matchCount = toolLogPatterns.filter(pattern => content.includes(pattern)).length;
        return matchCount >= 2; // 匹配2个以上特征则认为是工具日志
    }

    // 如果内容主要是JSON格式的API返回结果
    if (content.includes('"pois"') && content.includes('"location"')) {
        return true;
    }

    return false;
}

// 检测消息是否为表单提示词
function isFormPromptMessage(content) {
    if (!content || typeof content !== 'string') return false;

    const keywords = [
        '⚠️ **核心约束**',
        '🚨 **输出语言规范**',
        '📝 **排版要求**',
        '穷游原则：高性价比、学生优惠、实用避坑'
    ];

    return keywords.some(keyword => content.includes(keyword));
}

// 从表单提示词提取摘要
function extractFormPromptSummary(content) {
    if (!content) return '📋 旅行规划表单提交';

    let summary = '📋 旅行规划表单提交\n';

    try {
        const destination = content.match(/目的地[：:]\s*([^\n]+)/)?.[1]?.trim();
        const dateRange = content.match(/时间[：:]\s*([^\n]+)/)?.[1]?.trim();
        const days = content.match(/（(\d+)天）/)?.[1] || content.match(/(\d+)天/)?.[1];
        const travelers = content.match(/(\d+)人/)?.[1];
        const budget = content.match(/预算[：:]([^\n]+)/)?.[1]?.trim();

        if (destination) summary += `📍 目的地：${destination}\n`;
        if (dateRange) summary += `📅 时间：${dateRange}\n`;
        if (days) summary += `⏰ 天数：${days}天\n`;
        if (travelers) summary += `👥 人数：${travelers}人\n`;
        if (budget) summary += `💰 预算：${budget}`;

        const preferencesMatch = content.match(/偏好[：:]\s*([^\n]+)/)?.[1]?.trim();
        if (preferencesMatch) {
            summary += `\n🎯 偏好：${preferencesMatch}`;
        }
    } catch (e) {
        console.error('提取表单摘要失败:', e);
    }

    return summary;
}

// ========== 新建会话 ==========
function createNewConversation() {
    // 检查配额
    if (currentUser && currentUser.current_conversation_count >= currentUser.max_conversations) {
        showToast('warning', '配额已满', `您最多只能创建 ${currentUser.max_conversations} 个活跃会话，请先归档或删除旧会话`);
        return;
    }

    // 直接跳转到首页开始新对话
    window.location.href = '/';
}

// ========== 用户菜单切换 ==========
function toggleUserMenu() {
    const menu = document.getElementById('userMenu');
    const dropdownMenu = document.getElementById('dropdownMenu');
    if (dropdownMenu) {
        dropdownMenu.classList.toggle('show');
    }
}

// 点击外部关闭菜单
document.addEventListener('click', function(event) {
    const userMenu = document.getElementById('userMenu');
    const dropdownMenu = document.getElementById('dropdownMenu');

    if (userMenu && dropdownMenu && !userMenu.contains(event.target)) {
        dropdownMenu.classList.remove('show');
    }
});

// ========== Toast 通知 ==========
function showToast(type, title, message, duration = 3000) {
    const toast = document.getElementById('toast');
    const toastIcon = document.getElementById('toastIcon');
    const toastTitle = document.getElementById('toastTitle');
    const toastMessage = document.getElementById('toastMessage');

    toast.className = `toast ${type}`;

    const icons = {
        success: 'fa-check-circle',
        error: 'fa-times-circle',
        warning: 'fa-exclamation-circle',
        info: 'fa-info-circle'
    };
    toastIcon.className = `fas ${icons[type] || icons.info}`;

    toastTitle.textContent = title;
    toastMessage.textContent = message;

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => toast.classList.remove('show'), duration);
}

function hideToast() {
    document.getElementById('toast').classList.remove('show');
}

// ========== 退出登录 ==========
function confirmLogout() {
    // 清除本地存储
    localStorage.removeItem('access_token');
    localStorage.removeItem('user_info');

    // 关闭对话框
    const modal = document.getElementById('confirmModal');
    if (modal) modal.classList.remove('show');

    // 跳转到登录页
    window.location.href = '/auth.html';
}

function closeConfirmModal() {
    const modal = document.getElementById('confirmModal');
    if (modal) modal.classList.remove('show');
}

// ========== 显示退出确认对话框 ==========
function showConfirmModal() {
    const modal = document.getElementById('confirmModal');
    if (modal) modal.classList.add('show');
}

// ========== HTML 转义 ==========
function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
