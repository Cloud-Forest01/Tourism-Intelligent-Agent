"""
UI 模块
包含所有前端UI组件和事件处理逻辑

注意：用户认证UI已移除，等待重构
"""
from .components import *
# from .auth_ui import create_login_box, get_login_components  # 已删除：等待重构
from .main_ui import create_main_box, create_footer
from .styles import get_custom_css
from .event_handlers import (
    # AuthEventHandler,  # 已删除：等待重构
    ConversationEventHandler,
    update_preferences
)

__all__ = [
    # Components
    'create_date_inputs',
    'create_destination_input',
    'create_preference_checkboxes',
    'create_budget_input',
    'create_requirements_input',
    'create_submit_button',
    'create_result_display',
    'create_chat_tab',
    'create_conversation_sidebar',
    'create_header',
    'create_current_trip_info',
    'create_auth_message',
    'create_global_states',

    # Auth UI (已移除)
    # 'create_login_box',
    # 'get_login_components',

    # Main UI
    'create_main_box',
    'create_footer',

    # Styles
    'get_custom_css',

    # Event Handlers
    # 'AuthEventHandler',  # 已删除
    'ConversationEventHandler',
    'update_preferences'
]
