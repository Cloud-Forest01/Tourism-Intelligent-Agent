/**
 * 个人资料页面逻辑
 */

const API_BASE_URL = window.location.origin;

// ==================== 页面加载初始化 ====================

document.addEventListener('DOMContentLoaded', async function() {
    await checkLoginAndLoadData();

    // 监听文件选择，显示预览
    const avatarFileInput = document.getElementById('editAvatarFile');
    if (avatarFileInput) {
        avatarFileInput.addEventListener('change', handleAvatarFileSelect);
    }
});

/**
 * 检查登录状态并加载数据
 */
async function checkLoginAndLoadData() {
    const token = localStorage.getItem('access_token');

    // 隐藏所有状态
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('notLoggedIn').style.display = 'none';
    document.getElementById('profileContent').style.display = 'none';

    if (!token) {
        // 未登录，显示提示
        document.getElementById('notLoggedIn').style.display = 'flex';
        return;
    }

    // 显示加载状态
    document.getElementById('loadingState').style.display = 'flex';

    try {
        // 获取用户信息
        const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const user = await response.json();
            await displayUserData(user);
        } else {
            // Token无效或过期
            throw new Error('认证失败');
        }
    } catch (error) {
        console.error('加载用户数据失败:', error);
        localStorage.removeItem('access_token');
        localStorage.removeItem('user_info');
        document.getElementById('loadingState').style.display = 'none';
        document.getElementById('notLoggedIn').style.display = 'flex';
    }
}

/**
 * 显示用户数据
 */
async function displayUserData(user) {
    // 隐藏加载状态，显示内容
    document.getElementById('loadingState').style.display = 'none';
    document.getElementById('profileContent').style.display = 'block';

    // 更新大头像
    const avatarSection = document.querySelector('.avatar-large');
    if (avatarSection) {
        if (user.avatar_url) {
            avatarSection.innerHTML = `<img src="${user.avatar_url}" class="avatar-large-img" alt="用户头像">`;
        } else {
            avatarSection.innerHTML = `<i class="fas fa-user"></i>`;
        }
    }

    // 基本信息
    document.getElementById('userGreeting').textContent = `你好，${user.nickname || user.username}`;
    document.getElementById('username').textContent = user.username;
    document.getElementById('nickname').textContent = user.nickname || '未设置';
    document.getElementById('email').textContent = user.email || '未设置';

    // 账户信息
    const subscriptionType = user.subscription_tier || 'free';
    const tierText = subscriptionType === 'admin' ? '管理员' : '免费用户';
    document.getElementById('subscriptionType').textContent = tierText;

    const maxConv = user.max_conversations || 10;
    const limitText = maxConv >= 9999 ? '无限制' : `${maxConv}个`;
    document.getElementById('conversationLimit').textContent = limitText;

    document.getElementById('conversationUsed').textContent = `${user.current_conversation_count || 0}个`;

    // ✅ 统计数据改为活跃会话数量（从API获取的会话中筛选）
    // 这个会在 loadRecentConversations 中更新
    document.getElementById('totalPlans').textContent = '加载中...';

    // 加载最近会话
    await loadRecentConversations();
}

/**
 * 加载最近会话
 */
async function loadRecentConversations() {
    const token = localStorage.getItem('access_token');
    const conversationsList = document.getElementById('conversationsList');

    try {
        // 从用户信息中获取user_id
        const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
        const userId = userInfo.user_id;

        if (!userId) {
            throw new Error('未找到用户ID');
        }

        const response = await fetch(`${API_BASE_URL}/api/conversations?user_id=${encodeURIComponent(userId)}`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            const data = await response.json();
            const conversations = data.data?.conversations || [];

            // ✅ 统计活跃会话数量（status !== 'archived' && status !== 'deleted'）
            const activeConversations = conversations.filter(conv =>
                conv.status !== 'archived' && conv.status !== 'deleted'
            );
            document.getElementById('totalPlans').textContent = activeConversations.length;

            if (conversations.length === 0) {
                conversationsList.innerHTML = `
                    <div class="empty-state">
                        <i class="fas fa-inbox"></i>
                        <p>暂无会话</p>
                    </div>
                `;
                return;
            }

            // 只显示最近3个
            const recentConversations = conversations.slice(0, 3);

            conversationsList.innerHTML = recentConversations.map(conv => `
                <div class="conversation-item">
                    <div class="conv-title">
                        <i class="fas fa-map-marker-alt"></i>
                        <span class="conv-title-text">${escapeHtml(conv.title)}</span>
                    </div>
                    <div class="conv-time">创建于 ${formatDateTime(conv.created_at)}</div>
                    <div class="conv-actions">
                        <button class="btn btn-secondary" onclick="viewConversation('${conv.conversation_id}')">
                            <i class="fas fa-eye"></i> 查看
                        </button>
                        <button class="btn btn-secondary" onclick="deleteConversation('${conv.conversation_id}')">
                            <i class="fas fa-trash"></i> 删除
                        </button>
                    </div>
                </div>
            `).join('');
        } else {
            throw new Error('加载会话失败');
        }
    } catch (error) {
        console.error('加载会话失败:', error);
        conversationsList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-exclamation-circle"></i>
                <p>加载失败，请刷新页面重试</p>
            </div>
        `;
    }
}

/**
 * 查看会话
 */
function viewConversation(conversationId) {
    // 跳转到主页并加载该会话
    window.location.href = `/?conversation=${conversationId}`;
}

/**
 * 删除会话
 */
async function deleteConversation(conversationId) {
    if (!confirm('确定要删除这个会话吗？')) {
        return;
    }

    const token = localStorage.getItem('access_token');

    try {
        const response = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}?user_id=${encodeURIComponent(getCurrentUserId())}`, {
            method: 'DELETE',
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        if (response.ok) {
            showNotification('会话已删除', 'success');
            // 重新加载会话列表
            await loadRecentConversations();
            // 重新加载用户信息（更新会话数）
            await checkLoginAndLoadData();
        } else {
            throw new Error('删除失败');
        }
    } catch (error) {
        console.error('删除会话失败:', error);
        showNotification('删除失败，请重试', 'error');
    }
}

/**
 * 获取当前用户ID
 */
function getCurrentUserId() {
    const userInfo = JSON.parse(localStorage.getItem('user_info') || '{}');
    return userInfo.user_id || '';
}

// ==================== 导航功能 ====================

/**
 * 返回主页
 */
function goBack() {
    window.location.href = '/';
}

/**
 * 跳转到登录页
 */
function goToLogin() {
    window.location.href = '/auth.html';
}

/**
 * 跳转到会话管理页面
 */
function goToDashboard() {
    window.location.href = '/dashboard.html';
}

// ==================== 退出登录 ====================

/**
 * 显示退出确认对话框
 */
function showLogoutConfirm() {
    const modal = document.getElementById('confirmModal');
    if (modal) {
        modal.classList.add('show');
    }
}

/**
 * 关闭退出确认对话框
 */
function closeLogoutConfirm() {
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
    closeLogoutConfirm();

    // 跳转到主页
    window.location.href = '/';
}

// ==================== 工具函数 ====================

/**
 * 格式化日期
 */
function formatDate(dateString) {
    if (!dateString) return '未知';

    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');

    return `${year}-${month}-${day}`;
}

/**
 * 格式化日期时间
 */
function formatDateTime(dateString) {
    if (!dateString) return '未知';

    const date = new Date(dateString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');

    return `${year}-${month}-${day} ${hours}:${minutes}`;
}

/**
 * 转义HTML特殊字符
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * 显示通知
 */
function showNotification(message, type = 'info') {
    // 简单实现，可以后续扩展
    console.log(`[${type.toUpperCase()}] ${message}`);

    // 或者使用简单的alert
    // alert(message);
}

// ==================== 编辑个人资料 ====================

/**
 * 显示编辑资料弹窗
 */
function showEditProfileModal() {
    const modal = document.getElementById('editProfileModal');
    if (!modal) return;

    // 获取当前显示的值
    const currentNickname = document.getElementById('nickname').textContent;
    const currentEmail = document.getElementById('email').textContent;

    // 填充表单（如果是"未设置"则显示为空）
    document.getElementById('editNickname').value = currentNickname === '未设置' ? '' : currentNickname;
    document.getElementById('editEmail').value = currentEmail === '未设置' ? '' : currentEmail;
    document.getElementById('editAvatarFile').value = ''; // 清空文件选择

    // 隐藏预览
    document.getElementById('avatarPreview').style.display = 'none';

    // 显示弹窗
    modal.classList.add('show');
}

/**
 * 关闭编辑资料弹窗
 */
function closeEditProfileModal() {
    const modal = document.getElementById('editProfileModal');
    if (modal) {
        modal.classList.remove('show');
    }
}

/**
 * 处理头像文件选择
 */
function handleAvatarFileSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    // 验证文件类型
    const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
        alert('请选择有效的图片文件（jpg、png、gif、webp）');
        event.target.value = '';
        return;
    }

    // 验证文件大小（5MB）
    const maxSize = 5 * 1024 * 1024;
    if (file.size > maxSize) {
        alert('图片大小不能超过5MB');
        event.target.value = '';
        return;
    }

    // 显示预览
    const reader = new FileReader();
    reader.onload = function(e) {
        const preview = document.getElementById('avatarPreview');
        const previewImg = document.getElementById('avatarPreviewImg');
        previewImg.src = e.target.result;
        preview.style.display = 'block';
    };
    reader.readAsDataURL(file);
}

/**
 * 保存个人资料
 */
async function saveProfile() {
    const token = localStorage.getItem('access_token');
    console.log('Token:', token ? token.substring(0, 20) + '...' : 'null');

    if (!token) {
        showNotification('请先登录', 'error');
        return;
    }

    const nickname = document.getElementById('editNickname').value.trim();
    const email = document.getElementById('editEmail').value.trim();
    const avatarFile = document.getElementById('editAvatarFile').files[0];

    // 验证至少填写一个字段
    if (!nickname && !email && !avatarFile) {
        alert('请至少填写一个字段');
        return;
    }

    try {
        // 使用统一的更新接口（支持FormData，可以同时上传文件）
        const formData = new FormData();
        if (nickname) formData.append('nickname', nickname);
        if (email) formData.append('email', email);
        if (avatarFile) formData.append('avatar', avatarFile);

        console.log('发送请求到:', `${API_BASE_URL}/api/profile/update-with-avatar`);
        console.log('FormData 包含:', { nickname, email, hasAvatar: !!avatarFile });

        const response = await fetch(`${API_BASE_URL}/api/profile/update-with-avatar`, {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`
            },
            body: formData
        });

        console.log('响应状态:', response.status);

        if (!response.ok) {
            const error = await response.json();
            console.error('错误详情:', error);
            throw new Error(error.detail || '保存失败');
        }

        const result = await response.json();
        console.log('保存成功:', result);

        showNotification('保存成功', 'success');

        // 关闭弹窗
        closeEditProfileModal();

        // 重新加载用户信息
        await checkLoginAndLoadData();

    } catch (error) {
        console.error('保存失败:', error);
        alert(`保存失败: ${error.message}`);
    }
}
