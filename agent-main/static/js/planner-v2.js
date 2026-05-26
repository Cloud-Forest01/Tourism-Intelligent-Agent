/**
 * 智能规划V2 - 地图展示逻辑
 * =====================================
 * 实现地图展示和AI对话显示：
 * - 绿色路线 (#10B981)
 * - 数字POI标记
 * - AI详细行程对话显示
 * - 地图标记与POI联动
 */

console.log('🚀 planner-v2.js 开始加载...');

// ==================== 全局变量 ====================
let mapV2 = null;
let currentItinerary = null; // 存储完整行程数据
let v2_markers = []; // 当前显示的标记 (v2前缀)
let v2_polylines = []; // 当前显示的所有路线（支持多天）

// 颜色配置（参照图2）
const COLORS = {
    route: '#10B981', // 绿色路线
    routeDim: '#D1D5DB', // 非当前天的路线（灰色）
    marker: '#10B981', // 绿色标记
    markerDim: '#9CA3AF', // 非当前天的标记（灰色）
    infoPanel: 'rgba(0, 0, 0, 0.8)', // 黑色半透明信息面板
    activeTab: '#10B981', // 激活的DAY标签
    inactiveTab: '#E5E7EB' // 未激活的DAY标签
};

// ==================== 初始化地图 ====================

/**
 * 初始化V2地图
 * @param {string} containerId - 地图容器ID
 */
function initializeMapV2(containerId = 'map-container') {
    if (typeof AMap === 'undefined') {
        console.error('❌ 高德地图API未加载');
        return null;
    }

    // 检查容器尺寸
    const container = document.getElementById(containerId);
    if (container) {
        const rect = container.getBoundingClientRect();
        console.log(`📐 地图容器尺寸: ${rect.width}x${rect.height}`);
        if (rect.width === 0 || rect.height === 0) {
            console.error('❌ 地图容器尺寸为0，地图无法显示');
        }
    }

    mapV2 = new AMap.Map(containerId, {
        zoom: 13,
        center: [116.397428, 39.90923],
        viewMode: '2D',
        mapStyle: 'amap://styles/normal',
        features: ['bg', 'road', 'building'], // 确保加载基础要素
        showLabel: true
    });

    // 添加地图加载事件监听
    mapV2.on('complete', () => {
        console.log('✅ 地图资源加载完成');
    });

    mapV2.on('click', () => {
        console.log('🖱️ 地图可点击');
    });

    // 添加工具栏
    AMap.plugin([
        'AMap.ToolBar',
        'AMap.Scale'
    ], function() {
        mapV2.addControl(new AMap.ToolBar({ position: 'RT' }));
        mapV2.addControl(new AMap.Scale());
    });

    // 强制刷新地图
    setTimeout(() => {
        if (mapV2) {
            mapV2.getSize();
            mapV2.setZoom(13);
            console.log('🔄 地图已强制刷新');
        }
    }, 500);

    console.log('✅ V2地图初始化成功');
    return mapV2;
}

// ==================== 渲染行程数据 ====================

/**
 * 渲染完整行程到地图
 * @param {Object} itineraryData - 行程数据（来自API响应）
 */
function renderItineraryV2(itineraryData) {
    currentItinerary = itineraryData;

    // 暴露到全局，供保存功能使用
    window.currentItinerary = itineraryData;

    // 显示AI对话内容
    displayAIConversation(itineraryData);

    // 在地图上显示所有天的POI
    renderAllDaysOnMap(itineraryData);

    // 同步填充V1的itinerary对象，更新右侧时间轴
    syncItineraryToV1(itineraryData);

    // 自动保存草稿到LocalStorage
    autoSaveToLocalStorage(itineraryData);
}

/**
 * 自动保存行程数据到LocalStorage
 * @param {Object} itineraryData - 行程数据
 */
function autoSaveToLocalStorage(itineraryData) {
    try {
        const draftData = {
            itinerary: itineraryData,
            timestamp: new Date().toISOString(),
            version: '1.0'
        };
        localStorage.setItem('trip_itinerary_draft', JSON.stringify(draftData));
        console.log('✅ 草稿已自动保存到LocalStorage');
    } catch (error) {
        console.warn('⚠️ 自动保存到LocalStorage失败:', error);
    }
}

/**
 * 同步行程数据到V1系统（更新右侧时间轴）
 * @param {Object} itineraryData - V2行程数据
 */
function syncItineraryToV1(itineraryData) {
    if (!window.plannerHelpers) {
        console.warn('V1 helpers not loaded');
        return;
    }

    // 获取V1的itinerary对象
    const v1Itinerary = window.plannerHelpers.itinerary || {};
    const v1TotalDays = window.plannerHelpers.totalDays || 3;

    // 清空旧数据
    for (let i = 1; i <= v1TotalDays; i++) {
        if (v1Itinerary[i]) {
            v1Itinerary[i].items = [];
        }
    }

    // 转换V2数据格式到V1格式
    if (itineraryData.days && Array.isArray(itineraryData.days)) {
        itineraryData.days.forEach(dayData => {
            const dayNum = dayData.day;
            if (!v1Itinerary[dayNum]) {
                v1Itinerary[dayNum] = { items: [] };
            }

            // 转换POI数据
            if (dayData.pois && Array.isArray(dayData.pois)) {
                dayData.pois.forEach(poi => {
                    v1Itinerary[dayNum].items.push({
                        startTime: poi.start_time || '--:--',
                        endTime: poi.end_time || '--:--',
                        name: poi.name || '未命名',
                        address: poi.address || poi.location || '',
                        notes: poi.description || '',
                        cost: poi.cost || 0,
                        lng: poi.lng,
                        lat: poi.lat
                    });
                });
            }
        });
    }

    // 更新V1的当前天数和总天数
    window.plannerHelpers.currentDay = 1;
    window.plannerHelpers.totalDays = itineraryData.total_days || itineraryData.days?.length || 3;

    // 调用V1的renderTimeline函数
    if (typeof window.plannerHelpers.renderTimeline === 'function') {
        window.plannerHelpers.renderTimeline();
    }

    console.log('✅ 已同步行程数据到V1系统');
}

/**
 * 显示AI对话内容（详细行程）
 * @param {Object} itineraryData - 行程数据
 */
function displayAIConversation(itineraryData) {
    const container = document.getElementById('ai-conversation');
    if (!container) {
        console.error('ai-conversation容器未找到');
        return;
    }

    // 生成时间字符串
    const now = new Date();
    const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}`;

    // 构建费用HTML（避免嵌套模板字符串）
    let costHtml = '';
    if (itineraryData.estimated_total_cost) {
        costHtml = `
            <p style="margin: 0.25rem 0; color: var(--text-primary); font-size: 0.9rem;">
                <i class="fas fa-wallet" style="margin-right: 0.5rem;"></i>
                预计总费用: ¥${itineraryData.estimated_total_cost}
            </p>
        `;
    }

    // 构建AI消息HTML
    let html = `
        <div class="ai-message">
            <div class="ai-message-header">
                <div class="ai-avatar"><i class="fas fa-robot"></i></div>
                <div class="ai-name">小YOU</div>
                <div class="ai-time">${timeStr}</div>
            </div>
            <div class="ai-message-content">
                <div class="trip-overview" style="margin-bottom: 1rem; padding: 1rem; background: #f0fdf4; border-radius: 8px;">
                    <h3 style="margin: 0 0 0.5rem 0; color: #10B981; display: flex; align-items: center; gap: 0.5rem;">
                        <i class="fas fa-map-marker-alt"></i>
                        ${itineraryData.destination || '未知目的地'}
                    </h3>
                    <p style="margin: 0.25rem 0; color: var(--text-primary); font-size: 0.9rem;">
                        <i class="fas fa-calendar" style="margin-right: 0.5rem;"></i>
                        ${itineraryData.start_date || ''} 至 ${itineraryData.end_date || ''}
                        （共${itineraryData.total_days || itineraryData.days?.length || 0}天）
                    </p>
                    ${costHtml}
                </div>
    `;

    // 遍历每一天
    if (itineraryData.days && Array.isArray(itineraryData.days)) {
        itineraryData.days.forEach((dayData, index) => {
            html += '<div class="day-section">';
            html += '<div class="day-title">';
            html += '<i class="fas fa-sun"></i>';
            html += '第' + (dayData.day || index + 1) + '天 - ' + (dayData.date || '');
            html += '</div>';

            // POI列表
            if (dayData.pois && Array.isArray(dayData.pois) && dayData.pois.length > 0) {
                html += '<ul class="poi-list">';
                dayData.pois.forEach((poi, poiIndex) => {
                    // 构建POI项HTML
                    let poiHtml = '<li class="poi-item" onclick="focusOnPOI(' + poi.lng + ', ' + poi.lat + ', ' + (poiIndex + 1) + ')">';
                    poiHtml += '<div class="poi-item-name">';
                    poiHtml += '<span class="poi-number">' + (poiIndex + 1) + '</span>';
                    poiHtml += poi.name || '未命名地点';
                    poiHtml += '</div>';

                    // 时间
                    if (poi.start_time && poi.end_time) {
                        poiHtml += '<div class="poi-item-time">';
                        poiHtml += '<i class="fas fa-clock"></i>';
                        poiHtml += poi.start_time + ' - ' + poi.end_time;
                        if (poi.duration) {
                            poiHtml += '(' + poi.duration + '分钟)';
                        }
                        poiHtml += '</div>';
                    }

                    // 描述
                    if (poi.description) {
                        poiHtml += '<div class="poi-item-desc">' + poi.description + '</div>';
                    }

                    // 地址
                    if (poi.address) {
                        poiHtml += '<div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 0.25rem;">';
                        poiHtml += '<i class="fas fa-map-marker-alt" style="margin-right: 0.25rem;"></i>';
                        poiHtml += poi.address;
                        poiHtml += '</div>';
                    }

                    // 费用
                    if (poi.cost || poi.ticket_price) {
                        poiHtml += '<div style="font-size: 0.85rem; color: #f59e0b; margin-top: 0.25rem;">';
                        poiHtml += '<i class="fas fa-ticket-alt" style="margin-right: 0.25rem;"></i>';
                        if (poi.ticket_price) {
                            poiHtml += '¥' + poi.ticket_price + ' ';
                        }
                        if (poi.notes) {
                            poiHtml += poi.notes;
                        }
                        poiHtml += '</div>';
                    }

                    poiHtml += '</li>';
                    html += poiHtml;
                });
                html += '</ul>';

                // 当天总结
                if (dayData.day_summary) {
                    html += '<div class="day-summary">';
                    html += '<i class="fas fa-clipboard-list" style="margin-right: 0.5rem;"></i>';
                    html += dayData.day_summary;
                    html += '</div>';
                }

                // 当天提示
                if (dayData.tips && Array.isArray(dayData.tips) && dayData.tips.length > 0) {
                    html += '<div class="tips-section">';
                    html += '<div class="tips-title">';
                    html += '<i class="fas fa-lightbulb" style="color: #f59e0b;"></i>';
                    html += '当日提示';
                    html += '</div>';
                    html += '<ul class="tips-list">';
                    dayData.tips.forEach(tip => {
                        html += '<li>' + tip + '</li>';
                    });
                    html += '</ul>';
                    html += '</div>';
                }
            }

            html += '</div>'; // end day-section
        });
    }

    // 总体建议
    if (itineraryData.recommendations && Array.isArray(itineraryData.recommendations) && itineraryData.recommendations.length > 0) {
        html += '<div style="margin-top: 1rem; padding: 1rem; background: #fffbeb; border-radius: 8px; border-left: 4px solid #f59e0b;">';
        html += '<h4 style="margin: 0 0 0.75rem 0; color: #f59e0b; display: flex; align-items: center; gap: 0.5rem;">';
        html += '<i class="fas fa-star"></i>旅行建议</h4>';
        html += '<ul style="margin: 0; padding-left: 1.25rem;">';
        itineraryData.recommendations.forEach(rec => {
            html += '<li style="margin-bottom: 0.5rem; color: var(--text-primary);">' + rec + '</li>';
        });
        html += '</ul>';
        html += '</div>';
    }

    html += `
            </div>
        </div>
    `;

    container.innerHTML = html;
    console.log('✅ AI对话内容已显示');
}

/**
 * 在地图上渲染所有天的POI和路线
 * @param {Object} itineraryData - 行程数据
 */
function renderAllDaysOnMap(itineraryData) {
    if (!mapV2 || !itineraryData.days) return;

    // 清除现有标记和路线
    clearMapV2();

    const allPOIs = [];

    // 收集所有POI
    itineraryData.days.forEach(dayData => {
        if (dayData.pois && Array.isArray(dayData.pois)) {
            dayData.pois.forEach(poi => {
                allPOIs.push(poi);
            });
        }
    });

    // 渲染所有POI标记
    if (allPOIs.length > 0) {
        allPOIs.forEach((poi, index) => {
            const marker = createNumberedMarkerV2(poi, index + 1);
            if (marker) {
                marker.on('click', () => {
                    // 聚焦到这个POI
                    mapV2.setCenter([poi.lng, poi.lat]);
                    mapV2.setZoom(15);
                });
                v2_markers.push(marker);
            }
        });

        // 调整视野以显示所有POI
        fitViewV2(allPOIs);
    }

    // 渲染每天的路线
    itineraryData.days.forEach(dayData => {
        renderRouteV2(dayData);
    });

    console.log(`✅ 已渲染${allPOIs.length}个POI到地图`);
}

/**
 * 聚焦到指定POI
 * @param {number} lng - 经度
 * @param {number} lat - 纬度
 * @param {number} poiNumber - POI编号
 */
function focusOnPOI(lng, lat, poiNumber) {
    if (!mapV2) return;

    // 设置地图中心和缩放
    mapV2.setCenter([lng, lat]);
    mapV2.setZoom(15);

    // 高亮对应的标记
    // TODO: 添加标记高亮效果

    console.log(`📍 聚焦到POI #${poiNumber}: [${lng}, ${lat}]`);
}

/**
 * 显示指定天数（保留此函数以兼容旧代码）
 * @param {number} day - 天数（1-based）
 */
function showDayV2(day) {
    if (!currentItinerary || !currentItinerary.days) return;

    v2_currentDay = day;
    const dayData = currentItinerary.days.find(d => d.day === day);

    if (!dayData) {
        console.warn(`第${day}天数据不存在`);
        return;
    }

    // 清除现有标记和路线
    clearMapV2();

    // 渲染POI标记
    renderPOIsV2(dayData.pois);

    // 渲染路线
    renderRouteV2(dayData);

    // 更新信息面板
    if (dayData.pois && dayData.pois.length > 0) {
        showInfoPanelV2(dayData.pois[0], 0, day);
    }

    // 调整视野
    fitViewV2(dayData.pois);
}

// ==================== 渲染POI标记 ====================

/**
 * 渲染POI标记（带数字标签）
 * @param {Array} pois - POI列表
 */
function renderPOIsV2(pois) {
    if (!mapV2 || !pois || pois.length === 0) return;

    pois.forEach((poi, index) => {
        const marker = createNumberedMarkerV2(poi, index + 1);
        if (marker) {
            marker.on('click', () => {
                showInfoPanelV2(poi, index, v2_currentDay);
            });
            v2_markers.push(marker);
        }
    });
}

/**
 * 创建带数字的标记
 * @param {Object} poi - POI数据
 * @param {number} number - 显示的数字
 * @returns {AMap.Marker} 标记实例
 */
function createNumberedMarkerV2(poi, number) {
    if (!poi.lng || !poi.lat) return null;

    // 创建自定义内容（数字标记）
    const content = `
        <div class="custom-marker marker-${number}"
             style="
                width: 36px;
                height: 36px;
                background: ${COLORS.marker};
                border: 3px solid white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-weight: bold;
                font-size: 16px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.3);
                cursor: pointer;
                transition: all 0.2s ease;
             ">
            ${number}
        </div>
    `;

    const marker = new AMap.Marker({
        position: [poi.lng, poi.lat],
        content: content,
        offset: new AMap.Pixel(-18, -18),
        title: poi.name,
        extData: { poi: poi, number: number }
    });

    mapV2.add(marker);
    return marker;
}

// ==================== 渲染路线 ====================

/**
 * 渲染路线（绿色）
 * @param {Object} dayData - 当天数据
 */
function renderRouteV2(dayData) {
    if (!mapV2 || !dayData.pois || dayData.pois.length < 2) return;

    // 收集路径坐标
    let path = [];

    // 如果有route_segments，使用详细路径
    if (dayData.route_segments && dayData.route_segments.length > 0) {
        dayData.route_segments.forEach(seg => {
            if (seg.path_coords && seg.path_coords.length > 0) {
                path = path.concat(seg.path_coords);
            }
        });
    }

    // 如果没有详细路径，使用POI之间的直线
    if (path.length === 0) {
        path = dayData.pois.map(poi => [poi.lng, poi.lat]);
    }

    // 根据天数选择颜色（第一天绿色，后续天蓝色/橙色等）
    const dayColors = ['#10B981', '#3B82F6', '#F59E0B', '#EF4444', '#8B5CF6'];
    const colorIndex = (dayData.day - 1) % dayColors.length;

    // 创建路线并添加到数组
    const polyline = new AMap.Polyline({
        path: path,
        strokeColor: dayColors[colorIndex],
        strokeWeight: 5,
        strokeOpacity: 0.8,
        lineJoin: 'round',
        lineCap: 'round'
    });

    mapV2.add(polyline);
    v2_polylines.push(polyline);

    console.log(`✅ 已渲染第${dayData.day}天路线，颜色: ${dayColors[colorIndex]}`);
}

// ==================== 清除地图元素 ====================

/**
 * 清除地图上的标记和路线
 */
function clearMapV2() {
    if (v2_markers.length > 0) {
        mapV2.remove(v2_markers);
        v2_markers = [];
    }

    if (v2_polylines.length > 0) {
        mapV2.remove(v2_polylines);
        v2_polylines = [];
    }
}

// ==================== 调整视野 ====================

/**
 * 调整地图视野以显示所有POI
 * @param {Array} pois - POI列表
 */
function fitViewV2(pois) {
    if (!mapV2 || !pois || pois.length === 0) return;

    const bounds = new AMap.Bounds();
    let hasValidPoint = false;

    pois.forEach(poi => {
        if (poi.lng && poi.lat) {
            bounds.extend([poi.lng, poi.lat]);
            hasValidPoint = true;
        }
    });

    if (hasValidPoint) {
        mapV2.setFitView(null, false, [50, 50, 50, 150]); // 为底部信息面板留出空间
    }
}

// ==================== DAY切换组件 ====================

// ==================== 底部信息面板样式 ====================
// 注意：info面板样式保留，但天数切换功能已移除

// ==================== 底部信息面板 ====================

/**
 * 显示底部信息面板
 * @param {Object} poi - POI数据
 * @param {number} index - POI索引
 * @param {number} day - 天数
 */
function showInfoPanelV2(poi, index, day) {
    let panel = document.getElementById('info-panel-v2');

    if (!panel) {
        panel = document.createElement('div');
        panel.id = 'info-panel-v2';
        panel.className = 'info-panel-v2';
        document.getElementById('map-container').appendChild(panel);
    }

    // 计算总POI数
    const totalPOIs = currentItinerary.days?.[day - 1]?.pois?.length || 0;

    // 生成进度点HTML
    let dotsHtml = '<div class="progress-dots">';
    for (let i = 0; i < totalPOIs; i++) {
        dotsHtml += `<div class="progress-dot ${i === index ? 'active' : ''}"></div>`;
    }
    dotsHtml += '</div>';

    // 图片URL（使用SVG占位符）
    const placeholderSvg = `data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120' viewBox='0 0 120 120'%3E%3Crect fill='%23333' width='120' height='120'/%3E%3Ctext fill='%23FFF' font-family='Arial' font-size='14' x='50%25' y='50%25' text-anchor='middle' dy='.3em'%3EPOI%3C/text%3E%3C/svg%3E`;
    const imageUrl = poi.image_url || placeholderSvg;

    panel.innerHTML = `
        <img class="info-panel-image" src="${imageUrl}" alt="${poi.name}" onerror="this.src='${placeholderSvg}'">
        <div class="info-panel-content">
            <div class="info-panel-time">${poi.start_time} - ${poi.end_time}</div>
            <div class="info-panel-name">${poi.name}</div>
            <div class="info-panel-desc">${poi.description || ''}</div>
            <div class="info-panel-actions">
                <button class="info-panel-btn" onclick="navigateToPOIV2(${index})" title="导航">
                    <i class="fas fa-location-arrow"></i>
                </button>
                <button class="info-panel-btn" onclick="toggleFavoritePOIV2(${index})" title="收藏">
                    <i class="fas fa-star"></i>
                </button>
                <button class="info-panel-btn" onclick="sharePOIV2(${index})" title="分享">
                    <i class="fas fa-share-alt"></i>
                </button>
            </div>
        </div>
        ${dotsHtml}
    `;
}

/**
 * 隐藏信息面板
 */
function hideInfoPanelV2() {
    const panel = document.getElementById('info-panel-v2');
    if (panel) {
        panel.classList.add('hidden');
    }
}

// ==================== POI操作函数 ====================

/**
 * 导航到POI
 * @param {number} index - POI索引
 */
function navigateToPOIV2(index) {
    const dayData = currentItinerary.days?.[v2_currentDay - 1];
    if (dayData && dayData.pois && dayData.pois[index]) {
        const poi = dayData.pois[index];
        // 使用高德地图导航
        window.open(`https://uri.amap.com/navigation?to=${poi.lng},${poi.lat},${encodeURIComponent(poi.name)}&mode=car&src=Vtrip`, '_blank');
    }
}

/**
 * 收藏POI
 * @param {number} index - POI索引
 */
function toggleFavoritePOIV2(index) {
    // TODO: 实现收藏功能
    showNotificationV2('收藏功能开发中', 'info');
}

/**
 * 分享POI
 * @param {number} index - POI索引
 */
function sharePOIV2(index) {
    const dayData = currentItinerary.days?.[v2_currentDay - 1];
    if (dayData && dayData.pois && dayData.pois[index]) {
        const poi = dayData.pois[index];
        const text = `📍 ${poi.name}\n🕐 ${poi.start_time} - ${poi.end_time}\n${poi.description || ''}`;

        if (navigator.share) {
            navigator.share({
                title: poi.name,
                text: text
            });
        } else {
            // 复制到剪贴板
            navigator.clipboard.writeText(text).then(() => {
                showNotificationV2('已复制到剪贴板', 'success');
            });
        }
    }
}

// ==================== API调用函数 ====================

/**
 * 调用V2行程规划API（带实时进度反馈）
 * @param {Object} requestData - 请求参数
 */
async function callPlanV2API(requestData) {
    try {
        const startTime = Date.now();
        console.log('📡 发起AI请求...');

        const response = await fetch('/api/trip/plan-v2', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(requestData)
        });

        const result = await response.json();
        const elapsedTime = ((Date.now() - startTime) / 1000).toFixed(1);
        console.log(`✅ AI响应完成，耗时: ${elapsedTime}秒`);

        if (result.success && result.itinerary) {
            return result.itinerary;
        } else {
            throw new Error(result.message || '规划失败');
        }
    } catch (error) {
        console.error('V2 API调用失败:', error);
        throw error;
    }
}

// ==================== AI行程生成主函数 ====================

/**
 * AI智能生成行程（主入口函数）
 * 由 planner.html 中的"AI智能生成行程"按钮调用
 */
async function generateAITripV2() {
    try {
        // 1. 获取表单数据
        const formData = window.plannerHelpers?.getFormData();
        if (!formData) {
            showNotificationV2('请先填写行程信息', 'warning');
            return;
        }

        // 2. 验证必填字段
        if (!formData.destination) {
            showNotificationV2('请输入目的地', 'warning');
            return;
        }

        if (!formData.start_date || !formData.end_date) {
            showNotificationV2('请选择开始和结束日期', 'warning');
            return;
        }

        // 3. 显示进度模态框
        showProgressModal();

        // 4. 启动慢速进度动画（到99%）
        startSlowProgressAnimation();

        // 5. 调用API
        const itineraryData = await callPlanV2API(formData);

        // 6. API返回后，完成进度（99% -> 100%）
        completeProgress();

        // 7. 更新最终状态
        updateProgressText('行程规划完成！');
        activateProgressStep(4);

        // 8. 延迟关闭进度模态框
        await new Promise(resolve => setTimeout(resolve, 1000));
        hideProgressModal();

        // 9. 渲染行程到地图
        if (itineraryData) {
            renderItineraryV2(itineraryData);
            showNotificationV2('行程生成成功！', 'success');
        }

    } catch (error) {
        updateProgressText('规划失败，请重试');
        hideProgressModal();
        console.error('AI行程生成失败:', error);
        showNotificationV2('行程生成失败: ' + error.message, 'error');
    }
}

/**
 * 启动慢速进度动画
 */
function startSlowProgressAnimation() {
    // 进度时间表（匹配实际AI处理时间：约100秒）
    const progressSchedule = [
        { percent: 10, delay: 500, step: 1, text: '正在分析目的地信息' },
        { percent: 20, delay: 3000, step: 2, text: '正在搜索景点和路线' },
        { percent: 35, delay: 8000, step: 2, text: 'AI正在思考最佳方案...' },
        { percent: 50, delay: 15000, step: 3, text: '正在优化路线安排' },
        { percent: 65, delay: 25000, step: 3, text: '正在计算预算分配' },
        { percent: 80, delay: 40000, step: 4, text: '正在生成详细行程' },
        { percent: 90, delay: 60000, step: 4, text: 'AI正在完善细节...' },
        { percent: 95, delay: 75000, step: 4, text: '正在添加地理编码...' },
        { percent: 99, delay: 90000, step: 4, text: 'AI正在最后优化，请稍候...' }
    ];

    progressSchedule.forEach(({ percent, delay, step, text }) => {
        setTimeout(() => {
            updateProgressText(text);
            activateProgressStep(step);
            updateProgressBar(percent, true); // 使用慢速模式
            updateProgressPercentage(percent);
        }, delay);
    });
}

console.log('✅ generateAITripV2 函数已定义');

/**
 * 显示进度模态框
 */
function showProgressModal() {
    const modal = document.getElementById('ai-progress-modal');
    if (modal) {
        modal.classList.add('show');
        // 重置进度
        updateProgressText('正在分析目的地信息');
        updateProgressBar(0);
        updateProgressPercentage(0);
        resetProgressSteps();
        activateProgressStep(1);
    }
}

/**
 * 隐藏进度模态框
 */
function hideProgressModal() {
    const modal = document.getElementById('ai-progress-modal');
    if (modal) {
        modal.classList.remove('show');
    }
}

/**
 * 更新进度文字
 */
function updateProgressText(text) {
    const textElement = document.getElementById('ai-progress-text');
    if (textElement) {
        textElement.textContent = text;
    }
}

/**
 * 更新进度百分比显示
 */
function updateProgressPercentage(percent) {
    const percentageElement = document.getElementById('progress-percentage');
    if (percentageElement) {
        percentageElement.textContent = Math.round(percent) + '%';
    }
}

/**
 * 更新进度条（带慢速效果）
 * @param {number} percent - 目标进度（0-100）
 * @param {boolean} isSlow - 是否慢速模式
 */
function updateProgressBar(percent, isSlow = false) {
    const fill = document.getElementById('progress-fill');
    if (fill) {
        // 如果是慢速模式，逐步增加
        if (isSlow) {
            const currentWidth = parseFloat(fill.style.width) || 0;
            const targetWidth = Math.min(percent, 99); // 最多到99%

            // 如果需要增加，分步增加
            if (currentWidth < targetWidth) {
                const increment = 0.5; // 每次增加0.5%
                const newWidth = Math.min(currentWidth + increment, targetWidth);
                fill.style.width = newWidth + '%';

                // 如果还没到99%，继续增加
                if (newWidth < targetWidth) {
                    setTimeout(() => updateProgressBar(targetWidth, true), 50);
                }
            }
        } else {
            // 正常速度直接设置
            fill.style.width = Math.min(percent, 99) + '%';

            // 如果到达99%，添加等待效果
            if (percent >= 99) {
                fill.classList.add('waiting');
            } else {
                fill.classList.remove('waiting');
            }
        }
    }
}

/**
 * 重置所有进度步骤
 */
function resetProgressSteps() {
    const steps = document.querySelectorAll('.progress-step');
    if (steps.length === 0) return;

    steps.forEach(step => {
        step.classList.remove('pending', 'active', 'completed');
        const icon = step.querySelector('i');
        if (icon) {
            icon.className = 'far fa-circle';
        }
    });
}

/**
 * 激活指定的进度步骤
 * @param {number} stepNumber - 步骤编号 (1-4)
 */
function activateProgressStep(stepNumber) {
    const steps = document.querySelectorAll('.progress-step');
    if (steps.length === 0) return;

    steps.forEach((step, index) => {
        const stepNum = index + 1;
        const icon = step.querySelector('i');

        if (stepNum < stepNumber) {
            // 已完成的步骤
            step.classList.remove('pending', 'active');
            step.classList.add('completed');
            if (icon) {
                icon.className = 'fas fa-check-circle';
            }
        } else if (stepNum === stepNumber) {
            // 当前激活的步骤
            step.classList.remove('pending', 'completed');
            step.classList.add('active');
            if (icon) {
                icon.className = 'fas fa-spinner fa-spin';
            }
        } else {
            // 待处理的步骤
            step.classList.remove('active', 'completed');
            step.classList.add('pending');
            if (icon) {
                icon.className = 'far fa-circle';
            }
        }
    });
}

/**
 * 完成进度（从99%到100%）
 */
function completeProgress() {
    const fill = document.getElementById('progress-fill');
    const percentageElement = document.getElementById('progress-percentage');

    // 移除等待效果
    if (fill) {
        fill.classList.remove('waiting');
    }

    // 动画到100%
    let currentPercent = 99;
    const completeInterval = setInterval(() => {
        currentPercent += 0.5;
        if (currentPercent >= 100) {
            currentPercent = 100;
            clearInterval(completeInterval);
        }

        updateProgressBar(currentPercent, false);
        updateProgressPercentage(currentPercent);
    }, 20); // 每20ms增加0.5%
}

// ==================== 导出 ====================

// 将函数暴露到全局作用域
window.plannerV2 = {
    initialize: initializeMapV2,
    render: renderItineraryV2,
    showDay: showDayV2,
    hidePanel: hideInfoPanelV2,
    callAPI: callPlanV2API
};

// 将generateAITripV2暴露到全局（供HTML按钮调用）
window.generateAITripV2 = generateAITripV2;
console.log('✅ generateAITripV2 已暴露到 window.generateAITripV2');

/**
 * 从JSON文件加载行程
 */
function loadItineraryFromFile(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        try {
            const itineraryData = JSON.parse(e.target.result);

            // 验证数据格式
            if (!itineraryData.destination || !itineraryData.days) {
                throw new Error('无效的行程文件格式');
            }

            // 渲染行程
            renderItineraryV2(itineraryData);

            // 填充表单
            if (window.plannerHelpers && window.plannerHelpers.fillFormData) {
                window.plannerHelpers.fillFormData(itineraryData);
            }

            showNotificationV2('行程加载成功', 'success');
            console.log('✅ 行程已从文件加载:', itineraryData);

        } catch (error) {
            console.error('加载失败:', error);
            showNotificationV2('加载失败: ' + error.message, 'error');
        }
    };
    reader.readAsText(file);
}

/**
 * 自动恢复LocalStorage中的草稿
 */
function autoRestoreDraft() {
    try {
        const draftDataStr = localStorage.getItem('trip_itinerary_draft');
        if (!draftDataStr) return;

        const draftData = JSON.parse(draftDataStr);

        // 检查草稿是否过期（7天）
        const draftTime = new Date(draftData.timestamp);
        const now = new Date();
        const daysDiff = (now - draftTime) / (1000 * 60 * 60 * 24);

        if (daysDiff > 7) {
            console.log('草稿已过期，已清除');
            localStorage.removeItem('trip_itinerary_draft');
            return;
        }

        // 提示用户恢复草稿
        if (draftData.itinerary && draftData.itinerary.destination) {
            const message = `发现未完成的行程草稿（${draftData.itinerary.destination}，保存于${Math.floor(daysDiff)}天前）\n\n是否恢复此草稿？`;

            if (confirm(message)) {
                renderItineraryV2(draftData.itinerary);
                showNotificationV2('草稿已恢复', 'success');
                console.log('✅ 草稿已恢复');
            } else {
                // 清除草稿
                localStorage.removeItem('trip_itinerary_draft');
                console.log('草稿已清除');
            }
        }

    } catch (error) {
        console.warn('恢复草稿失败:', error);
        localStorage.removeItem('trip_itinerary_draft');
    }
}

/**
 * 清除草稿
 */
function clearDraft() {
    localStorage.removeItem('trip_itinerary_draft');
    showNotificationV2('草稿已清除', 'success');
    console.log('✅ 草稿已清除');
}

// 暴露加载和清除草稿函数到全局
window.loadItineraryFromFile = loadItineraryFromFile;
window.clearDraft = clearDraft;
window.autoRestoreDraft = autoRestoreDraft;

/**
 * 显示通知（跨模块调用）
 * 注意：这个函数只作为桥梁，实际实现在 planner.js 中
 */
function showNotificationV2(message, type = 'info') {
    // 直接调用全局的 showNotification (来自 planner.js)
    if (typeof window.showNotification === 'function') {
        window.showNotification(message, type);
    } else {
        // 备用实现
        console.log(`[${type.toUpperCase()}] ${message}`);
    }
}

console.log('✅ 智能规划V2模块加载完成');

// ==================== 页面加载时初始化地图 ====================
document.addEventListener('DOMContentLoaded', function() {
    // 延迟初始化，确保DOM完全加载
    setTimeout(function() {
        if (typeof initializeMapV2 === 'function') {
            initializeMapV2();
            console.log('✅ 地图自动初始化完成');
        }

        // 尝试恢复草稿
        if (typeof autoRestoreDraft === 'function') {
            autoRestoreDraft();
        }
    }, 100);
});
