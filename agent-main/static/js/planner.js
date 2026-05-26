/**
 * 行程规划辅助工具 - 非地图功能模块
 * =====================================
 * 说明：
 * - 原planner.js已移除所有地图相关功能
 * - 地图功能统一由planner-v2.js实现
 * - 本文件仅保留表单处理、预算计算、UI交互等辅助功能
 *
 * 修改日期: 2025-02-04
 * 版本: v2.0 (移除地图功能)
 */

// ==================== 全局变量 ====================
let currentDay = 1;
let totalDays = 3;
let selectedInterests = [];
let itinerary = {}; // 按天存储的行程数据

// ==================== 页面加载 ====================
document.addEventListener('DOMContentLoaded', function() {
    // 注意：地图初始化已移至 planner-v2.js
    initializeEventListeners();
    loadURLParams();
    initializeInterests();
    initializeItinerary();
    updateBudgetDisplay();
});

// ==================== URL参数加载 ====================
function loadURLParams() {
    const urlParams = new URLSearchParams(window.location.search);
    const destination = urlParams.get('destination');

    if (destination) {
        document.getElementById('destination').value = destination;
        // 注意：搜索功能已移至 planner-v2.js
    }
}

// ==================== 事件监听器初始化 ====================
function initializeEventListeners() {
    // 旅行天数变化
    const tripDaysInput = document.getElementById('trip-days');
    if (tripDaysInput) {
        tripDaysInput.addEventListener('change', function() {
            totalDays = parseInt(this.value);
            initializeItinerary();
        });
    }

    // 预算变化
    const budgetInput = document.getElementById('budget');
    if (budgetInput) {
        budgetInput.addEventListener('change', updateBudgetDisplay);
    }

    // 日期变化
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');

    if (startDateInput) {
        startDateInput.addEventListener('change', calculateDays);
    }
    if (endDateInput) {
        endDateInput.addEventListener('change', calculateDays);
    }
}

// ==================== 兴趣偏好初始化 ====================
function initializeInterests() {
    const interestsContainer = document.getElementById('interests-tags');
    if (!interestsContainer) return;

    const checkboxes = interestsContainer.querySelectorAll('input[type="checkbox"]');

    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', updateSelectedInterests);
    });

    // 限制最多选择3个
    updateSelectedInterests();
}

function updateSelectedInterests() {
    const interestsContainer = document.getElementById('interests-tags');
    if (!interestsContainer) return;

    const checkboxes = interestsContainer.querySelectorAll('input[type="checkbox"]:checked');
    selectedInterests = Array.from(checkboxes).map(cb => cb.value);

    // 限制选择数量
    if (selectedInterests.length > 3) {
        const lastChecked = checkboxes[checkboxes.length - 1];
        lastChecked.checked = false;
        selectedInterests.pop();
        showNotification('最多只能选择3个偏好', 'warning');
    }

    // 更新计数显示
    const countElement = document.getElementById('preference-count-planner');
    if (countElement) {
        countElement.textContent = `已选择${selectedInterests.length}个偏好`;
    }
}

// ==================== 行程初始化 ====================
function initializeItinerary() {
    itinerary = {};

    for (let day = 1; day <= totalDays; day++) {
        itinerary[day] = {
            date: '',
            items: []
        };
    }

    renderTimeline();
}

// ==================== 时间轴渲染 ====================
function renderTimeline() {
    const timelineContainer = document.getElementById('itinerary-timeline');
    if (!timelineContainer) return;

    const dayData = itinerary[currentDay];

    if (!dayData || dayData.items.length === 0) {
        timelineContainer.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-map-marked-alt"></i>
                <p>点击地图添加景点</p>
                <p>或使用AI智能生成行程</p>
            </div>
        `;
        return;
    }

    let html = '';

    dayData.items.forEach((item, index) => {
        html += `
            <div class="timeline-item">
                <div class="timeline-marker">
                    <span class="marker-number">${index + 1}</span>
                </div>
                <div class="timeline-content">
                    <div class="timeline-header">
                        <span class="timeline-time">${item.startTime || '--:--'} - ${item.endTime || '--:--'}</span>
                        <div class="timeline-actions">
                            <button class="btn-icon" onclick="editTimelineItem(${index})" title="编辑">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn-icon btn-danger" onclick="deleteTimelineItem(${index})" title="删除">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                    <h4 class="timeline-title">${item.name || '未命名'}</h4>
                    ${item.address ? `<p class="timeline-address"><i class="fas fa-map-marker-alt"></i> ${item.address}</p>` : ''}
                    ${item.notes ? `<p class="timeline-notes">${item.notes}</p>` : ''}
                    ${item.cost ? `<p class="timeline-cost"><i class="fas fa-yen-sign"></i> ${item.cost}</p>` : ''}
                </div>
            </div>
        `;
    });

    timelineContainer.innerHTML = html;

    // 更新天数标签
    const dayLabel = document.getElementById('current-day-label');
    if (dayLabel) {
        dayLabel.textContent = `第 ${currentDay} 天`;
    }
}

// ==================== 天数切换 ====================
function changeDay(delta) {
    const newDay = currentDay + delta;

    if (newDay >= 1 && newDay <= totalDays) {
        currentDay = newDay;
        renderTimeline();
    }
}

// ==================== 手动添加项目 ====================
function addManualItem() {
    const modal = document.getElementById('add-place-modal');
    if (modal) {
        modal.style.display = 'block';
    }
}

// ==================== 删除时间轴项目 ====================
function deleteTimelineItem(index) {
    if (!confirm('确定要删除这个行程项吗？')) {
        return;
    }

    const dayData = itinerary[currentDay];
    if (dayData && dayData.items) {
        dayData.items.splice(index, 1);
        renderTimeline();
        showNotification('已删除行程项', 'success');
    }
}

// ==================== 编辑时间轴项目 ====================
function editTimelineItem(index) {
    const dayData = itinerary[currentDay];
    if (!dayData || !dayData.items[index]) {
        return;
    }

    const item = dayData.items[index];

    // 填充模态框
    document.getElementById('modal-place-name').value = item.name || '';
    document.getElementById('modal-start-time').value = item.startTime || '09:00';
    document.getElementById('modal-end-time').value = item.endTime || '10:00';
    document.getElementById('modal-cost').value = item.cost || '';
    document.getElementById('modal-notes').value = item.notes || '';

    // 保存当前编辑的索引
    document.getElementById('add-place-modal').dataset.editIndex = index;

    // 显示模态框
    const modal = document.getElementById('add-place-modal');
    if (modal) {
        modal.style.display = 'block';
    }
}

// ==================== 关闭模态框 ====================
function closeModal() {
    const modal = document.getElementById('add-place-modal');
    if (modal) {
        modal.style.display = 'none';
        // 清除编辑索引
        delete modal.dataset.editIndex;
    }
}

// ==================== 预算计算 ====================
function updateBudgetDisplay() {
    const budgetInput = document.getElementById('budget');
    const totalBudgetElement = document.getElementById('total-budget');
    const allocatedBudgetElement = document.getElementById('allocated-budget');
    const remainingBudgetElement = document.getElementById('remaining-budget');

    if (!budgetInput) return;

    const totalBudget = parseFloat(budgetInput.value) || 0;

    // 计算已分配预算
    let allocatedBudget = 0;

    for (let day = 1; day <= totalDays; day++) {
        if (itinerary[day] && itinerary[day].items) {
            itinerary[day].items.forEach(item => {
                const cost = parseFloat(item.cost) || 0;
                allocatedBudget += cost;
            });
        }
    }

    const remainingBudget = totalBudget - allocatedBudget;

    // 更新显示
    if (totalBudgetElement) {
        totalBudgetElement.textContent = `¥${totalBudget.toFixed(0)}`;
    }
    if (allocatedBudgetElement) {
        allocatedBudgetElement.textContent = `¥${allocatedBudget.toFixed(0)}`;
    }
    if (remainingBudgetElement) {
        remainingBudgetElement.textContent = `¥${remainingBudget.toFixed(0)}`;

        // 根据剩余预算改变颜色
        if (remainingBudget < 0) {
            remainingBudgetElement.style.color = '#EF4444';
        } else if (remainingBudget < totalBudget * 0.2) {
            remainingBudgetElement.style.color = '#F59E0B';
        } else {
            remainingBudgetElement.style.color = '#10B981';
        }
    }
}

// ==================== 计算天数 ====================
function calculateDays() {
    const startDateInput = document.getElementById('start-date');
    const endDateInput = document.getElementById('end-date');
    const tripDaysInput = document.getElementById('trip-days');

    if (!startDateInput || !endDateInput || !tripDaysInput) return;

    const startDate = new Date(startDateInput.value);
    const endDate = new Date(endDateInput.value);

    if (startDate && endDate && endDate >= startDate) {
        const days = Math.ceil((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1;
        tripDaysInput.value = days;
        totalDays = days;
        initializeItinerary();
    }
}

// ==================== 通知功能 ====================
function showNotification(message, type = 'info') {
    const container = createNotificationContainer();

    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <i class="fas fa-${getNotificationIcon(type)}"></i>
        <span>${message}</span>
    `;

    container.appendChild(notification);

    // 3秒后自动移除
    setTimeout(() => {
        notification.classList.add('notification-hide');
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

function createNotificationContainer() {
    let container = document.getElementById('notification-container');

    if (!container) {
        container = document.createElement('div');
        container.id = 'notification-container';
        container.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            z-index: 10000;
        `;
        document.body.appendChild(container);
    }

    return container;
}

function getNotificationIcon(type) {
    const icons = {
        success: 'check-circle',
        error: 'exclamation-circle',
        warning: 'exclamation-triangle',
        info: 'info-circle'
    };
    return icons[type] || 'info-circle';
}

// ==================== 关闭AI规划面板 ====================
function closeAIPlanPanel() {
    const panel = document.getElementById('ai-plan-panel');
    if (panel) {
        panel.style.display = 'none';
    }
}

// ==================== 获取表单数据（供V2调用）====================
/**
 * 获取表单数据供AI规划使用
 * 此函数由 planner-v2.js 调用
 */
function getFormData() {
    return {
        destination: document.getElementById('destination')?.value || '',
        start_date: document.getElementById('start-date')?.value || '',
        end_date: document.getElementById('end-date')?.value || '',
        days_count: parseInt(document.getElementById('trip-days')?.value) || 3,
        travelers: parseInt(document.getElementById('travelers')?.value) || 1,
        budget: document.getElementById('budget')?.value || '',
        preferences: selectedInterests,
        deep_thinking: document.getElementById('deep-thinking-planner')?.checked || false
    };
}

// ==================== 导出到全局供 planner-v2.js 使用 ====================
window.plannerHelpers = {
    getFormData,
    updateBudgetDisplay,
    renderTimeline,
    itinerary,
    currentDay,
    totalDays,
    selectedInterests
};

// 暴露showNotification到全局（供planner-v2.js调用）
window.showNotification = showNotification;

// ==================== 确认添加行程项 ====================
function confirmAddPlace() {
    const modal = document.getElementById('add-place-modal');
    if (!modal) return;

    // 获取表单数据
    const name = document.getElementById('modal-place-name')?.value || '';
    const startTime = document.getElementById('modal-start-time')?.value || '09:00';
    const endTime = document.getElementById('modal-end-time')?.value || '10:00';
    const cost = document.getElementById('modal-cost')?.value || '0';
    const notes = document.getElementById('modal-notes')?.value || '';

    if (!name) {
        showNotification('请输入地点名称', 'warning');
        return;
    }

    // 检查是否是编辑模式
    const editIndex = modal.dataset.editIndex;

    if (editIndex !== undefined) {
        // 编辑模式：更新现有项目
        const dayData = itinerary[currentDay];
        if (dayData && dayData.items[editIndex]) {
            dayData.items[editIndex] = {
                ...dayData.items[editIndex],
                name,
                startTime,
                endTime,
                cost,
                notes
            };
            showNotification('行程项已更新', 'success');
        }
        delete modal.dataset.editIndex;
    } else {
        // 新增模式：添加新项目
        const dayData = itinerary[currentDay];
        if (dayData) {
            dayData.items.push({
                name,
                startTime,
                endTime,
                cost,
                notes,
                address: ''
            });
            showNotification('行程项已添加', 'success');
        }
    }

    // 更新显示
    renderTimeline();
    updateBudgetDisplay();

    // 清空表单
    document.getElementById('modal-place-name').value = '';
    document.getElementById('modal-cost').value = '';
    document.getElementById('modal-notes').value = '';

    // 关闭模态框
    closeModal();
}

// ==================== 保存行程（占位函数）====================
function saveItinerary() {
    // 检查是否有可保存的行程数据
    const itineraryData = window.plannerV2?.render ? window.currentItinerary : null;

    if (!itineraryData) {
        showNotification('请先生成行程', 'warning');
        return;
    }

    try {
        // 1. 自动保存到LocalStorage（草稿）
        const itineraryJSON = JSON.stringify(itineraryData, null, 2);
        localStorage.setItem('trip_itinerary_draft', itineraryJSON);
        console.log('✅ 草稿已自动保存到LocalStorage');

        // 2. 提供文件下载选项
        const dataStr = JSON.stringify(itineraryData, null, 2);
        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);

        // 创建下载链接
        const link = document.createElement('a');
        link.href = url;
        link.download = `${itineraryData.destination}_行程_${itineraryData.start_date}.json`;
        document.body.appendChild(link);
        link.click();

        // 清理
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        showNotification('行程已保存（文件已下载，草稿已自动保存）', 'success');
        console.log('✅ 行程保存成功');

    } catch (error) {
        console.error('保存失败:', error);
        showNotification('保存失败: ' + error.message, 'error');
    }
}
