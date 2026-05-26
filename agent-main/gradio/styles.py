"""
UI 样式模块
包含所有 Gradio 自定义 CSS 样式
"""


def get_custom_css():
    """
    获取自定义CSS样式

    Returns:
        str: CSS样式字符串
    """
    return """
#chatbot { min-height: 60vh; }
.user { text-align: right; }
.form-container { max-width: 900px; margin: 0 auto; }
.preference-checkbox { margin: 5px; }

/* ========== 地图容器样式 ========== */
#form_map_display, #chat_map_display, #map_popup_content {
    width: 100% !important;
    height: 500px !important;
    min-height: 500px !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    border: 2px solid #e8e8e8 !important;
}

#form_map_display iframe, #chat_map_display iframe, #map_popup_content iframe {
    width: 100% !important;
    height: 100% !important;
    border: none !important;
}

/* 地图弹窗样式 */
.map-popup-wrapper {
    width: 90vw !important;
    height: 80vh !important;
}

/* ========== 聊天窗口样式优化 ========== */
#chatbot {
    height: 500px !important;
    min-height: 500px !important;
    max-height: 500px !important;
    overflow-y: auto !important;
    border-radius: 12px !important;
    border: 2px solid #e8e8e8 !important;
    background: #ffffff !important;
}

/* 滚动条样式 */
#chatbot::-webkit-scrollbar {
    width: 8px !important;
}

#chatbot::-webkit-scrollbar-track {
    background: #f1f1f1 !important;
    border-radius: 4px !important;
}

#chatbot::-webkit-scrollbar-thumb {
    background: #888 !important;
    border-radius: 4px !important;
}

#chatbot::-webkit-scrollbar-thumb:hover {
    background: #555 !important;
}

/* 聊天消息样式 */
#chatbot .message {
    padding: 12px 16px !important;
    margin-bottom: 8px !important;
    border-radius: 12px !important;
    max-width: 85% !important;
    word-wrap: break-word !important;
}

#chatbot .user-message {
    background-color: #e3f2fd !important;
    margin-left: auto !important;
}

#chatbot .assistant-message {
    background-color: #f5f5f5 !important;
}

/* 地图预览卡片样式 */
#chatbot .map-preview {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    padding: 12px 16px !important;
    border-radius: 8px !important;
    margin-top: 8px !important;
    display: inline-block !important;
}

#chatbot .map-preview a {
    color: white !important;
    text-decoration: none !important;
    font-weight: bold !important;
    display: inline-block !important;
    padding: 8px 20px !important;
    background: rgba(255, 255, 255, 0.2) !important;
    border-radius: 8px !important;
    margin-top: 8px !important;
    transition: all 0.2s !important;
}

#chatbot .map-preview a:hover {
    background: rgba(255, 255, 255, 0.3) !important;
    transform: translateY(-2px) !important;
}

/* ========== 表单样式优化 ========== */
.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
}

/* 标签样式 */
.tabs {
    border-bottom: 2px solid #e8e8e8 !important;
}

.tab-item {
    font-weight: 600 !important;
    color: #666 !important;
}

.tab-item.selected {
    color: #667eea !important;
    border-bottom: 2px solid #667eea !important;
}

/* 按钮样式 */
.primary-button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    color: white !important;
    font-weight: 600 !important;
    transition: all 0.3s !important;
}

.primary-button:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4) !important;
}

/* ========== 响应式设计 ========== */
@media (max-width: 768px) {
    #chatbot {
        height: 400px !important;
        min-height: 400px !important;
    }

    #form_map_display, #chat_map_display {
        height: 350px !important;
        min-height: 350px !important;
    }
}

/* ========== 加载动画 ========== */
.loading-spinner {
    border: 3px solid #f3f3f3 !important;
    border-top: 3px solid #667eea !important;
    border-radius: 50% !important;
    width: 40px !important;
    height: 40px !important;
    animation: spin 1s linear infinite !important;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

/* ========== 卡片样式 ========== */
.info-card {
    background: white !important;
    border-radius: 12px !important;
    padding: 16px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1) !important;
    margin-bottom: 16px !important;
}

/* ========== 徽章样式 ========== */
.badge {
    display: inline-block !important;
    padding: 4px 12px !important;
    border-radius: 16px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
}

.badge-success {
    background: #d4edda !important;
    color: #155724 !important;
}

.badge-warning {
    background: #fff3cd !important;
    color: #856404 !important;
}

.badge-danger {
    background: #f8d7da !important;
    color: #721c24 !important;
}

/* ========== 分隔线 ========== */
hr {
    border: none !important;
    border-top: 1px solid #e8e8e8 !important;
    margin: 16px 0 !important;
}

/* ========== Markdown样式优化 ========== */
.markdown {
    line-height: 1.6 !important;
}

.markdown h1 {
    font-size: 24px !important;
    font-weight: 700 !important;
    margin-bottom: 16px !important;
    color: #333 !important;
}

.markdown h2 {
    font-size: 20px !important;
    font-weight: 600 !important;
    margin-bottom: 12px !important;
    color: #444 !important;
}

.markdown h3 {
    font-size: 18px !important;
    font-weight: 600 !important;
    margin-bottom: 10px !important;
    color: #555 !important;
}

.markdown ul {
    padding-left: 20px !important;
}

.markdown li {
    margin-bottom: 8px !important;
}

/* ========== 代码块样式 ========== */
pre {
    background: #f5f5f5 !important;
    border: 1px solid #e8e8e8 !important;
    border-radius: 8px !important;
    padding: 12px !important;
    overflow-x: auto !important;
}

code {
    font-family: 'Courier New', monospace !important;
    font-size: 14px !important;
}

/* ========== 图片样式 ========== */
img {
    max-width: 100% !important;
    height: auto !important;
    border-radius: 8px !important;
}
"""
