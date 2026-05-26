"""
会话服务类
面向 UI 的服务层
"""
import logging
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime

from .conversation_repository import ConversationRepository
from .conversation_model import ConversationModel

logger = logging.getLogger(__name__)


class ConversationService:
    """
    会话服务层（面向 UI）

    职责：
    - 为 Gradio 提供会话列表
    - 提供会话操作接口
    - 格式化会话数据用于展示
    - 错误处理和用户提示

    注意：ConversationManager已移除，直接使用ConversationRepository
    """

    def __init__(self, conversation_repository: Optional[ConversationRepository] = None):
        """
        初始化服务

        Args:
            conversation_repository: 会话仓储实例
        """
        self.conv_repo = conversation_repository or ConversationRepository()

    def get_conversation_list_ui(
        self,
        user_id: str,
        status: Literal["active", "archived", "all"] = "active"
    ) -> Dict[str, Any]:
        """
        获取UI用的会话列表

        Args:
            user_id: 用户ID
            status: 会话状态

        Returns:
            Dict: {
                "conversations": List[Dict],
                "quota_info": Dict,
                "display_info": str
            }
        """
        try:
            # 如果status是all，获取所有状态的会话
            if status == "all":
                active_convs = self.conv_repo.list_conversations(user_id, status="active")
                archived_convs = self.conv_repo.list_conversations(user_id, status="archived")
                deleted_convs = self.conv_repo.list_conversations(user_id, status="deleted")  # ✅ 添加已删除会话
                conversations = active_convs + archived_convs + deleted_convs
            else:
                conversations = self.conv_repo.list_conversations(user_id, status=status)

            # 格式化会话数据
            formatted_conversations = []
            for conv in conversations:
                formatted_conversations.append({
                    "id": conv.get("conversation_id"),
                    "title": conv.get("title"),
                    "destination": conv.get("destination"),
                    "date": self._format_date(conv.get("updated_at")),
                    "created_at": conv.get("created_at"),  # ✅ 添加创建时间
                    "updated_at": conv.get("updated_at"),  # 添加完整时间戳
                    "deleted_at": conv.get("deleted_at"),  # ✅ 添加删除时间
                    "message_count": conv.get("message_count", 0),
                    "has_map": conv.get("has_map", False),
                    "has_files": conv.get("has_files", False),
                    "is_pinned": conv.get("is_pinned", False),
                    "status": conv.get("status", "active")  # 添加状态字段
                })

            # 获取配额信息
            quota_info = self.conv_repo.get_quota_info(user_id)

            # 生成显示信息
            display_info = f"💾 **{quota_info['current']}/{quota_info['max']}** 个活跃计划"
            if quota_info['archived'] > 0:
                display_info += f" | 📦 {quota_info['archived']} 个已归档"

            return {
                "conversations": formatted_conversations,
                "quota_info": quota_info,
                "display_info": display_info,
                "choices": [conv["id"] for conv in formatted_conversations],  # 用于 Gradio Radio
                "labels": [f"{conv['title']} ({conv['date']})" for conv in formatted_conversations]  # 显示标签
            }

        except Exception as e:
            logger.error(f"❌ 获取会话列表失败: {e}")
            return {
                "conversations": [],
                "quota_info": {"current": 0, "max": 10, "archived": 0, "can_create": True},
                "display_info": "💾 **0/10** 个活跃计划",
                "choices": [],
                "labels": []
            }

    def get_conversation_detail_ui(self, user_id: str, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        获取UI用的会话详情

        Args:
            user_id: 用户ID
            conversation_id: 会话ID

        Returns:
            Optional[Dict]: 会话详情
        """
        try:
            conversation = self.conv_repo.get_conversation(user_id, conversation_id)

            if not conversation:
                return None

            # 格式化偏好设置
            trip_prefs = conversation.trip_preferences
            prefs_display = f"""
### 📍 当前计划：{conversation.title}

**目的地**：{trip_prefs.destination}
**日期**：{trip_prefs.start_date} 至 {trip_prefs.end_date}（{trip_prefs.days_count}天）
{f"**预算**：{trip_prefs.budget}元" if trip_prefs.budget else ""}
**偏好**：{trip_prefs.to_display_string()}
            """.strip()

            # 获取对话历史
            messages = conversation.get_messages()
            chat_history = [
                [msg.content, ""] if msg.role == "user" else ["", msg.content]
                for msg in messages
            ]

            return {
                "conversation_id": conversation.conversation_id,
                "title": conversation.title,
                "prefs_display": prefs_display,
                "trip_preferences": trip_prefs.dict(),
                "chat_history": chat_history,
                "message_count": len(messages),
                "resources": conversation.resources,
                "status": conversation.metadata.status,
                "tags": conversation.metadata.tags
            }

        except Exception as e:
            logger.error(f"❌ 获取会话详情失败: {e}")
            return None

    def create_from_form(
        self,
        user_id: str,
        start_date: str,
        end_date: str,
        destination: str,
        preferences: List[str],
        budget: Optional[str] = None,
        travelers: int = 1,
        user_requirements: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        从表单创建会话

        Args:
            user_id: 用户ID
            start_date: 开始日期
            end_date: 结束日期
            destination: 目的地
            preferences: 偏好列表
            budget: 预算
            travelers: 旅行人数
            user_requirements: 用户要求

        Returns:
            Dict: {
                "success": bool,
                "message": str,
                "conversation_id": Optional[str]
            }
        """
        try:
            # 计算天数
            from datetime import datetime
            try:
                start = datetime.strptime(start_date, "%Y-%m-%d")
                end = datetime.strptime(end_date, "%Y-%m-%d")
                days_count = (end - start).days + 1
            except:
                days_count = 1

            # 生成标题（包含人数信息）
            # ✅ 智能标题生成：如果有目的地信息，生成智能标题；否则使用"新对话"，等待首条消息自动命名
            if destination and destination.strip() and destination != "未指定":
                title = f"{destination} {travelers}人{days_count}日{'穷游' if budget else '之旅'}"
            else:
                title = "新对话"  # 聊天模式使用默认标题，等待首条消息自动命名

            # 构建偏好字典
            trip_preferences = {
                "destination": destination,
                "start_date": start_date,
                "end_date": end_date,
                "days_count": days_count,
                "budget": budget,
                "travelers": travelers,
                "selected_preferences": preferences,
                "user_requirements": user_requirements
            }

            # 创建会话
            result = self.conv_repo.create_conversation(user_id, title, trip_preferences)

            if result.get("success"):
                logger.info(f"✅ 从表单创建会话成功: {result.get('conversation_id')}")
            else:
                logger.warning(f"⚠️ 创建会话失败: {result.get('message')}")

            return result

        except Exception as e:
            logger.error(f"❌ 从表单创建会话失败: {e}")
            return {
                "success": False,
                "message": f"创建失败: {str(e)}",
                "conversation_id": None
            }

    def switch_to_conversation(
        self,
        user_id: str,
        conversation_id: str
    ) -> Dict[str, Any]:
        """
        切换到会话

        Args:
            user_id: 用户ID
            conversation_id: 会话ID

        Returns:
            Dict: {
                "success": bool,
                "message": str,
                "conversation_detail": Optional[Dict]
            }
        """
        try:
            # 切换会话
            result = self.conv_repo.switch_conversation(user_id, conversation_id)

            if not result.get("success"):
                return {
                    "success": False,
                    "message": result.get("message"),
                    "conversation_detail": None
                }

            # 获取会话详情
            conversation = result.get("conversation")
            detail = self.get_conversation_detail_ui(user_id, conversation.conversation_id)

            return {
                "success": True,
                "message": f"已切换到：{conversation.title}",
                "conversation_detail": detail
            }

        except Exception as e:
            logger.error(f"❌ 切换会话失败: {e}")
            return {
                "success": False,
                "message": f"切换失败: {str(e)}",
                "conversation_detail": None
            }

    def rename_conversation_ui(
        self,
        user_id: str,
        conversation_id: str,
        new_title: str
    ) -> Dict[str, Any]:
        """
        重命名会话（UI接口）

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            new_title: 新标题

        Returns:
            Dict: {"success": bool, "message": str, "new_title": str}
        """
        result = self.conv_repo.rename_conversation(user_id, conversation_id, new_title)

        return {
            "success": result.get("success", False),
            "message": result.get("message", ""),
            "new_title": new_title if result.get("success") else ""
        }

    def delete_conversation(
        self,
        conversation_id: str,
        user_id: str,
        permanently: bool = False
    ) -> Dict[str, Any]:
        """
        删除会话（对外接口）

        Args:
            conversation_id: 会话ID
            user_id: 用户ID
            permanently: 是否永久删除

        Returns:
            Dict: {"success": bool, "message": str}
        """
        # 调用内部方法（参数顺序不同）
        return self.delete_with_confirmation(user_id, conversation_id, permanently)

    def delete_with_confirmation(
        self,
        user_id: str,
        conversation_id: str,
        permanently: bool = False
    ) -> Dict[str, Any]:
        """
        删除会话（带确认）

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            permanently: 是否永久删除

        Returns:
            Dict: {"success": bool, "message": str}
        """
        result = self.conv_repo.delete_conversation(user_id, conversation_id, permanently)

        action = "永久删除" if permanently else "删除"
        if result.get("success"):
            return {
                "success": True,
                "message": f"✅ 会话已{action}"
            }
        else:
            return {
                "success": False,
                "message": f"❌ {result.get('message', '删除失败')}"
            }

    def archive_conversation_ui(
        self,
        user_id: str,
        conversation_id: str
    ) -> Dict[str, Any]:
        """
        归档会话（UI接口）

        Args:
            user_id: 用户ID
            conversation_id: 会话ID

        Returns:
            Dict: {"success": bool, "message": str}
        """
        result = self.conv_repo.archive_conversation(user_id, conversation_id)

        return {
            "success": result.get("success", False),
            "message": result.get("message", "")
        }

    def restore_conversation_ui(
        self,
        user_id: str,
        conversation_id: str
    ) -> Dict[str, Any]:
        """
        恢复会话（UI接口）

        Args:
            user_id: 用户ID
            conversation_id: 会话ID

        Returns:
            Dict: {"success": bool, "message": str}
        """
        result = self.conv_repo.restore_conversation(user_id, conversation_id)

        return {
            "success": result.get("success", False),
            "message": result.get("message", "")
        }

    def search_conversations_ui(
        self,
        user_id: str,
        keyword: str
    ) -> List[Dict[str, Any]]:
        """
        搜索会话（UI接口）

        Args:
            user_id: 用户ID
            keyword: 搜索关键词

        Returns:
            List[Dict]: 匹配的会话列表
        """
        conversations = self.conv_repo.search_conversations(user_id, keyword)

        # 格式化结果
        formatted = []
        for conv in conversations:
            formatted.append({
                "id": conv.get("conversation_id"),
                "title": conv.get("title"),
                "destination": conv.get("destination"),
                "date": self._format_date(conv.get("updated_at")),
                "status": conv.get("status")
            })

        return formatted

    def _format_date(self, date_str: Optional[str]) -> str:
        """格式化日期字符串"""
        if not date_str:
            return ""

        try:
            dt = datetime.fromisoformat(date_str)
            # 相对时间
            now = datetime.now()
            delta = now - dt

            if delta.days < 1:
                hours = delta.seconds // 3600
                if hours < 1:
                    return "刚刚"
                return f"{hours}小时前"
            elif delta.days < 7:
                return f"{delta.days}天前"
            elif delta.days < 30:
                weeks = delta.days // 7
                return f"{weeks}周前"
            else:
                return dt.strftime("%Y-%m-%d")
        except:
            return date_str

    def get_chat_history_for_llm(
        self,
        user_id: str,
        conversation_id: str,
        max_messages: int = 20
    ) -> List[Dict[str, str]]:
        """
        获取用于LLM的对话历史

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            max_messages: 最大消息数

        Returns:
            List[Dict]: [{"role": "user", "content": "..."}, ...]
        """
        return self.conv_repo.get_conversation_context(user_id, conversation_id, max_messages)

    def add_message_to_conversation(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        **metadata
    ) -> bool:
        """
        添加消息到会话

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            role: 角色
            content: 内容
            **metadata: 元数据

        Returns:
            bool: 是否成功
        """
        result = self.conv_repo.add_message(user_id, conversation_id, role, content, **metadata)

        # ✅ 首条消息自动命名：如果是该会话的第一条用户消息，自动更新会话标题
        if result and role == "user":
            conversation = self.conv_repo.get_conversation_by_id_only(conversation_id)
            if conversation and len(conversation.messages) == 1:  # 第一条消息
                # 生成标题：截取消息前20个字符
                title = self._generate_title_from_message(content)

                # 尝试从消息中提取目的地（简单关键词匹配）
                destination = self._extract_destination_from_message(content)

                # 如果提取到了目的地且当前是"未指定"，则更新
                if destination and conversation.trip_preferences.destination == "未指定":
                    conversation.trip_preferences.destination = destination
                    logger.info(f"✅ 自动更新目的地 {conversation_id}: {destination}")

                # 直接更新会话标题并保存
                conversation.title = title
                conversation.metadata.updated_at = datetime.now().isoformat()
                self.conv_repo.save_conversation(conversation)
                logger.info(f"✅ 自动命名会话 {conversation_id}: {title}")

        return result

    def _generate_title_from_message(self, message: str, max_length: int = 20) -> str:
        """
        根据消息内容生成会话标题

        Args:
            message: 消息内容
            max_length: 标题最大长度

        Returns:
            str: 生成的标题
        """
        import re

        # 去除多余的空白字符
        title = message.strip()

        # 移除换行符，只保留空格
        title = re.sub(r'\s+', ' ', title)

        # 截取前N个字符
        if len(title) > max_length:
            title = title[:max_length] + "..."

        # 如果标题为空，使用默认标题
        if not title:
            title = "新对话"

        return title

    def _extract_destination_from_message(self, message: str) -> Optional[str]:
        """
        从消息中提取目的地（简单关键词匹配）

        Args:
            message: 用户消息内容

        Returns:
            Optional[str]: 提取的目的地，如果无法识别则返回None
        """
        # 常见的中国城市和地区列表
        common_destinations = [
            "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "西安", "南京",
            "武汉", "厦门", "青岛", "大连", "苏州", "桂林", "丽江", "拉萨", "三亚",
            "哈尔滨", "长春", "沈阳", "济南", "郑州", "长沙", "南昌", "福州", "昆明",
            "贵州", "南宁", "海口", "兰州", "西宁", "银川", "呼和浩特", "太原",
            "新疆", "西藏", "青海", "甘肃", "四川", "云南", "贵州", "海南", "台湾",
            "香港", "澳门", "内蒙古", "黑龙江", "吉林", "辽宁", "河北", "河南", "湖北",
            "湖南", "江西", "安徽", "江苏", "浙江", "福建", "广东", "广西", "海南",
            "四川", "贵州", "云南", "陕西", "甘肃", "青海", "宁夏", "新疆"
        ]

        # 在消息中查找目的地
        for dest in common_destinations:
            if dest in message:
                return dest

        # 如果没有找到，返回None（保持"未指定"）
        return None

    def get_conversation_messages(
        self,
        conversation_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> Optional[List[Dict[str, Any]]]:
        """
        获取会话的消息列表（支持分页）

        Args:
            conversation_id: 会话ID
            limit: 返回消息数量限制（默认100条）
            offset: 跳过的消息数量（用于分页）

        Returns:
            Optional[List[Dict]]: 消息列表或None
        """
        try:
            conversation = self.conv_repo.get_conversation_by_id_only(conversation_id)

            if not conversation:
                return None

            # 获取所有消息
            all_messages = conversation.messages

            # 应用分页
            messages = all_messages[offset:offset + limit]

            # 转换为字典格式
            messages_data = [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "metadata": msg.metadata.dict() if msg.metadata else None
                }
                for msg in messages
            ]

            logger.info(f"✅ 获取会话 {conversation_id} 的消息: {len(messages_data)} 条 (offset={offset}, limit={limit})")
            return messages_data

        except Exception as e:
            logger.error(f"❌ 获取会话消息失败: {e}")
            return None

    def get_conversation_by_id(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        根据会话ID获取会话详情（不限定用户）
        注意：仅用于内部查询，不检查用户权限

        Args:
            conversation_id: 会话ID

        Returns:
            Optional[Dict]: 会话详情或None
        """
        try:
            conversation = self.conv_repo.get_conversation_by_id_only(conversation_id)

            if not conversation:
                return None

            return {
                "conversation_id": conversation.conversation_id,
                "title": conversation.title,
                "user_id": conversation.user_id,
                "destination": conversation.trip_preferences.destination,
                "start_date": conversation.trip_preferences.start_date,
                "end_date": conversation.trip_preferences.end_date,
                "budget": conversation.trip_preferences.budget,
                "preferences": conversation.trip_preferences.selected_preferences,
                "message_count": len(conversation.messages),
                "created_at": conversation.metadata.created_at,
                "updated_at": conversation.metadata.updated_at,
                "status": conversation.metadata.status
            }
        except Exception as e:
            logger.error(f"❌ 获取会话失败: {e}")
            return None

    def add_resource_to_conversation(
        self,
        user_id: str,
        conversation_id: str,
        resource_type: str,
        file_path: str,
        file_type: str,
        description: Optional[str] = None
    ) -> bool:
        """
        添加资源到会话

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            resource_type: 资源类型
            file_path: 文件路径
            file_type: 文件类型
            description: 描述

        Returns:
            bool: 是否成功
        """
        return self.conv_repo.add_resource(
            user_id, conversation_id, resource_type, file_path, file_type, description
        )
