"""
事件处理器模块
包含所有 Gradio 事件的处理函数
"""
import os
import re
import time
import logging
from datetime import datetime, timedelta

import gradio as gr

# 导入业务逻辑
from core.user_system import ConversationService

logger = logging.getLogger(__name__)


# ========== 会话管理事件处理器 ==========

class ConversationEventHandler:
    """会话管理事件处理器"""

    def __init__(self):
        self.conversation_service = None

    def get_conversation_service(self):
        """延迟加载会话服务"""
        if self.conversation_service is None:
            self.conversation_service = ConversationService()
        return self.conversation_service

    def load_conversation_list(self, user_id):
        """加载用户的会话列表"""
        try:
            conv_service = self.get_conversation_service()
            result = conv_service.get_conversation_list_ui(user_id)

            return (
                gr.update(choices=result["choices"], labels=result["labels"]),
                result["display_info"]
            )
        except Exception as e:
            logger.error(f"加载会话列表失败: {e}")
            return (
                gr.update(choices=[], labels=[]),
                "💾 **0/10** 个活跃计划"
            )

    def handle_switch_conversation(self, user_id, conversation_id):
        """切换会话"""
        try:
            conv_service = self.get_conversation_service()
            result = conv_service.switch_to_conversation(user_id, conversation_id)

            if result["success"]:
                detail = result["conversation_detail"]
                return (
                    conversation_id,  # 返回 conversation_id 用于更新全局状态
                    detail["prefs_display"] if detail else "### 📍 当前计划：新旅行",
                    detail["chat_history"] if detail else [],
                    detail["trip_preferences"] if detail else {},
                    result["message"]
                )
            else:
                return (
                    None,  # 切换失败时返回 None
                    f"### ❌ {result['message']}",
                    [],
                    {},
                    result["message"]
                )
        except Exception as e:
            logger.error(f"切换会话失败: {e}")
            return (
                None,  # 异常时返回 None
                f"### ❌ 切换失败: {str(e)}",
                [],
                {},
                f"切换失败: {str(e)}"
            )

    def handle_rename_conversation(self, user_id, conversation_id, new_title):
        """重命名会话"""
        try:
            conv_service = self.get_conversation_service()
            result = conv_service.rename_conversation_ui(user_id, conversation_id, new_title)

            if result["success"]:
                # 重新加载会话列表
                list_result = conv_service.get_conversation_list_ui(user_id)
                return (
                    gr.update(choices=list_result["choices"], labels=list_result["labels"]),
                    f"✅ {result['message']}"
                )
            else:
                return (
                    gr.update(),
                    f"❌ {result['message']}"
                )
        except Exception as e:
            logger.error(f"重命名会话失败: {e}")
            return (
                gr.update(),
                f"❌ 重命名失败: {str(e)}"
            )

    def handle_delete_conversation(self, user_id, conversation_id):
        """删除会话（带确认和验证）"""
        try:
            # 验证输入
            if not conversation_id:
                return (
                    gr.update(),
                    "💾 **0/10** 个活跃计划",
                    "⚠️ 请先选择要删除的会话"
                )

            conv_service = self.get_conversation_service()

            # 获取会话详情用于确认消息
            conv_detail = conv_service.get_conversation_by_id(conversation_id)
            conv_title = conv_detail["title"] if conv_detail else "未知会话"

            # 执行删除（软删除）
            result = conv_service.delete_with_confirmation(user_id, conversation_id, permanently=False)

            # 重新加载会话列表
            list_result = conv_service.get_conversation_list_ui(user_id)

            if result["success"]:
                # 成功消息，显示删除的会话名称
                success_msg = f"✅ 已删除会话：**{conv_title}**\n\n💡 提示：如需恢复，请从归档中找回（功能开发中）"
            else:
                success_msg = f"❌ {result.get('message', '删除失败')}"

            return (
                gr.update(choices=list_result["choices"], labels=list_result["labels"]),
                list_result["display_info"],
                success_msg
            )
        except Exception as e:
            logger.error(f"删除会话失败: {e}", exc_info=True)
            return (
                gr.update(),
                "💾 配额信息加载失败",
                f"❌ 删除失败: {str(e)}"
            )

    def create_new_plan(self):
        """创建新计划（重置状态）"""
        return [None, "### 📍 当前计划：新建旅行", {}]


# ========== 表单偏好选择处理器 ==========

def update_preferences(classic, food, niche, culture, nature, photo, nightlife, adventure, shopping, social):
    """更新偏好选择列表"""
    selected = []
    if classic: selected.append("classic")
    if food: selected.append("budget_food")
    if niche: selected.append("free_attractions")
    if culture: selected.append("culture")
    if nature: selected.append("nature")
    if photo: selected.append("photo")
    if nightlife: selected.append("nightlife")
    if adventure: selected.append("adventure")
    if shopping: selected.append("shopping")
    if social: selected.append("social")

    # 更新显示标签
    if len(selected) == 0:
        label = "请至少选择1个偏好"
    elif len(selected) > 3:
        label = f"已选择{len(selected)}个，最多只能选择3个"
    else:
        label = f"✅ 已选择{len(selected)}个偏好"

    return selected, gr.update(value=label)
