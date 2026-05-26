"""
会话仓储类
负责会话数据的持久化操作
"""
import json
import os
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from pathlib import Path
import logging

from .conversation_model import ConversationModel

logger = logging.getLogger(__name__)


class ConversationRepository:
    """
    会话数据仓储

    职责：
    - 读写会话数据文件
    - 会话的 CRUD 操作
    - 会话查询和筛选
    """

    def __init__(self, data_dir: str = "user_data"):
        """
        初始化仓储

        Args:
            data_dir: 数据目录路径
        """
        self.data_dir = Path(data_dir)

    def _get_user_dir(self, user_id: str) -> Path:
        """获取用户数据目录"""
        user_dir = self.data_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_conversations_dir(self, user_id: str) -> Path:
        """获取用户会话目录"""
        user_dir = self._get_user_dir(user_id)
        conv_dir = user_dir / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)

        # 创建归档目录
        archive_dir = conv_dir / "archived"
        archive_dir.mkdir(parents=True, exist_ok=True)

        return conv_dir

    def _get_conversations_index_file(self, user_id: str) -> Path:
        """获取会话索引文件路径"""
        user_dir = self._get_user_dir(user_id)
        return user_dir / "conversations.json"

    def _get_conversation_file(self, user_id: str, conversation_id: str, archived: bool = False) -> Path:
        """获取单个会话文件路径"""
        conv_dir = self._get_conversations_dir(user_id)
        if archived:
            return conv_dir / "archived" / f"{conversation_id}.json"
        return conv_dir / f"{conversation_id}.json"

    def _load_index(self, user_id: str) -> Dict[str, Any]:
        """加载会话索引"""
        index_file = self._get_conversations_index_file(user_id)
        if not index_file.exists():
            # 创建初始索引
            initial_data = {
                "conversations": [],
                "meta": {
                    "total_count": 0,
                    "active_count": 0,
                    "archived_count": 0
                }
            }
            self._save_index(user_id, initial_data)
            return initial_data

        try:
            with open(index_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"❌ 会话索引JSON解析失败: {e}")
            return {"conversations": [], "meta": {"total_count": 0, "active_count": 0, "archived_count": 0}}

    def _save_index(self, user_id: str, index_data: Dict[str, Any]):
        """保存会话索引"""
        index_file = self._get_conversations_index_file(user_id)
        with open(index_file, 'w', encoding='utf-8') as f:
            json.dump(index_data, f, ensure_ascii=False, indent=2)

    def create_conversation(
        self,
        user_id: str,
        title: str,
        trip_preferences: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        创建新会话

        Args:
            user_id: 用户ID
            title: 会话标题
            trip_preferences: 旅行偏好字典

        Returns:
            Dict: {
                "success": bool,
                "message": str,
                "conversation_id": Optional[str]
            }
        """
        try:
            # 检查配额
            active_count = self.get_conversation_count(user_id, status="active")
            if active_count >= 10:
                return {
                    "success": False,
                    "message": "已达到最大会话数量限制（10个），请先归档或删除旧会话",
                    "conversation_id": None
                }

            # 创建新会话
            conversation = ConversationModel.create_new(user_id, title, trip_preferences)

            # 保存会话
            if self.save_conversation(conversation):
                return {
                    "success": True,
                    "message": "会话创建成功",
                    "conversation_id": conversation.conversation_id
                }
            else:
                return {
                    "success": False,
                    "message": "保存会话失败",
                    "conversation_id": None
                }

        except Exception as e:
            logger.error(f"❌ 创建会话失败: {e}")
            return {
                "success": False,
                "message": f"创建失败: {str(e)}",
                "conversation_id": None
            }

    def save_conversation(self, conversation: ConversationModel) -> bool:
        """
        保存或更新会话

        Args:
            conversation: 会话模型实例

        Returns:
            bool: 是否成功
        """
        try:
            user_id = conversation.user_id
            conversation_id = conversation.conversation_id

            # 保存会话详情
            is_archived = conversation.metadata.status == "archived"
            conv_file = self._get_conversation_file(user_id, conversation_id, archived=is_archived)

            with open(conv_file, 'w', encoding='utf-8') as f:
                json.dump(conversation.to_dict(), f, ensure_ascii=False, indent=2)

            # 更新索引
            self._update_conversation_index(conversation)

            logger.info(f"✅ 保存会话: {conversation_id}")
            return True

        except Exception as e:
            logger.error(f"❌ 保存会话失败: {e}")
            return False

    def _update_conversation_index(self, conversation: ConversationModel):
        """更新会话索引"""
        user_id = conversation.user_id
        index_data = self._load_index(user_id)

        conversations_list = index_data.get("conversations", [])

        # 查找会话是否在索引中
        conv_index = None
        for i, conv in enumerate(conversations_list):
            if conv.get("conversation_id") == conversation.conversation_id:
                conv_index = i
                break

        # 更新或添加索引
        summary = conversation.to_summary_dict()
        if conv_index is not None:
            conversations_list[conv_index] = summary
        else:
            conversations_list.append(summary)

        # 更新元数据
        index_data["conversations"] = conversations_list
        index_data["meta"]["total_count"] = len(conversations_list)
        index_data["meta"]["active_count"] = len([c for c in conversations_list if c.get("status") == "active"])
        index_data["meta"]["archived_count"] = len([c for c in conversations_list if c.get("status") == "archived"])

        self._save_index(user_id, index_data)

    def get_conversation(self, user_id: str, conversation_id: str) -> Optional[ConversationModel]:
        """
        获取会话（别名方法，与 load_conversation 相同）

        Args:
            user_id: 用户ID
            conversation_id: 会话ID

        Returns:
            Optional[ConversationModel]: 会话对象或None
        """
        return self.load_conversation(user_id, conversation_id)

    def load_conversation(self, user_id: str, conversation_id: str) -> Optional[ConversationModel]:
        """加载单个会话"""
        # 先尝试从活跃目录加载
        conv_file = self._get_conversation_file(user_id, conversation_id, archived=False)

        if not conv_file.exists():
            # 尝试从归档目录加载
            conv_file = self._get_conversation_file(user_id, conversation_id, archived=True)

        if not conv_file.exists():
            logger.warning(f"⚠️ 会话文件不存在: {conversation_id}")
            return None

        try:
            with open(conv_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return ConversationModel.from_dict(data)
        except Exception as e:
            logger.error(f"❌ 加载会话失败: {e}")
            return None

    def list_conversations(
        self,
        user_id: str,
        status: Optional[Literal["active", "archived", "deleted"]] = "active",
        sort_by: str = "updated_at",
        order: Literal["asc", "desc"] = "desc"
    ) -> List[Dict[str, Any]]:
        """
        列出用户的会话

        Args:
            user_id: 用户ID
            status: 会话状态过滤 (active/archived/deleted)
            sort_by: 排序字段 (updated_at/created_at/title)
            order: 排序方向 (asc/desc)

        Returns:
            List[Dict]: 会话摘要列表
        """
        index_data = self._load_index(user_id)
        conversations = index_data.get("conversations", [])

        # 状态过滤
        if status:
            conversations = [c for c in conversations if c.get("status") == status]

        # 排序
        reverse = (order == "desc")
        conversations.sort(key=lambda x: x.get(sort_by, ""), reverse=reverse)

        return conversations

    def delete_conversation(self, user_id: str, conversation_id: str, permanently: bool = False) -> Dict[str, Any]:
        """
        删除会话

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            permanently: 是否永久删除

        Returns:
            Dict: {"success": bool, "message": str}
        """
        try:
            if permanently:
                # 永久删除：移除文件和索引
                conv_file = self._get_conversation_file(user_id, conversation_id, archived=False)
                archive_file = self._get_conversation_file(user_id, conversation_id, archived=True)

                # 删除文件
                if conv_file.exists():
                    conv_file.unlink()
                if archive_file.exists():
                    archive_file.unlink()

                # 从索引中移除
                index_data = self._load_index(user_id)
                conversations = index_data.get("conversations", [])
                conversations = [c for c in conversations if c.get("conversation_id") != conversation_id]
                index_data["conversations"] = conversations
                index_data["meta"]["total_count"] = len(conversations)
                self._save_index(user_id, index_data)

                logger.info(f"✅ 永久删除会话: {conversation_id}")
                return {"success": True, "message": "会话已永久删除"}
            else:
                # 软删除：标记为deleted
                conversation = self.load_conversation(user_id, conversation_id)
                if conversation:
                    conversation.delete()
                    self.save_conversation(conversation)
                    logger.info(f"✅ 标记删除会话: {conversation_id}")
                    return {"success": True, "message": "会话已删除"}
                else:
                    return {"success": False, "message": "会话不存在"}

        except Exception as e:
            logger.error(f"❌ 删除会话失败: {e}")
            return {"success": False, "message": f"删除失败: {str(e)}"}

    def archive_conversation(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        """
        归档会话

        Args:
            user_id: 用户ID
            conversation_id: 会话ID

        Returns:
            Dict: {"success": bool, "message": str}
        """
        try:
            conversation = self.load_conversation(user_id, conversation_id)
            if not conversation:
                return {"success": False, "message": "会话不存在"}

            # 标记为归档
            conversation.archive()
            self.save_conversation(conversation)

            # 移动文件到归档目录
            active_file = self._get_conversation_file(user_id, conversation_id, archived=False)
            archive_file = self._get_conversation_file(user_id, conversation_id, archived=True)

            if active_file.exists():
                import shutil
                shutil.move(str(active_file), str(archive_file))
                logger.info(f"✅ 归档会话: {conversation_id}")
                return {"success": True, "message": "会话已归档"}

            return {"success": True, "message": "会话已归档"}

        except Exception as e:
            logger.error(f"❌ 归档会话失败: {e}")
            return {"success": False, "message": f"归档失败: {str(e)}"}

    def restore_conversation(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        """
        恢复已归档或已删除的会话

        Args:
            user_id: 用户ID
            conversation_id: 会话ID

        Returns:
            Dict: {"success": bool, "message": str}
        """
        try:
            conversation = self.load_conversation(user_id, conversation_id)
            if not conversation:
                return {"success": False, "message": "会话不存在"}

            # 恢复状态
            conversation.restore()
            self.save_conversation(conversation)

            # 如果是从归档目录恢复，移动文件回活跃目录
            archive_file = self._get_conversation_file(user_id, conversation_id, archived=True)
            active_file = self._get_conversation_file(user_id, conversation_id, archived=False)

            if archive_file.exists():
                import shutil
                shutil.move(str(archive_file), str(active_file))
                logger.info(f"✅ 恢复会话: {conversation_id}")
                return {"success": True, "message": "会话已恢复"}

            return {"success": True, "message": "会话已恢复"}

        except Exception as e:
            logger.error(f"❌ 恢复会话失败: {e}")
            return {"success": False, "message": f"恢复失败: {str(e)}"}

    def get_quota_info(self, user_id: str) -> Dict[str, Any]:
        """
        获取用户会话配额信息

        Args:
            user_id: 用户ID

        Returns:
            Dict: {
                "current": int,      # 当前活跃会话数
                "max": int,          # 最大会话数
                "archived": int,     # 归档会话数
                "deleted": int,      # 已删除会话数
                "can_create": bool   # 是否可以创建新会话
            }
        """
        index_data = self._load_index(user_id)
        conversations = index_data.get("conversations", [])

        active_count = len([c for c in conversations if c.get("status") == "active"])
        archived_count = len([c for c in conversations if c.get("status") == "archived"])
        deleted_count = len([c for c in conversations if c.get("status") == "deleted"])  # ✅ 添加已删除统计

        return {
            "current": active_count,
            "max": 10,  # 最大会话数限制
            "archived": archived_count,
            "deleted": deleted_count,  # ✅ 返回已删除数量
            "can_create": active_count < 10
        }

    def get_conversation_count(self, user_id: str, status: Optional[str] = "active") -> int:
        """
        获取用户会话数量

        Args:
            user_id: 用户ID
            status: 会话状态过滤

        Returns:
            int: 会话数量
        """
        index_data = self._load_index(user_id)
        conversations = index_data.get("conversations", [])

        if status:
            conversations = [c for c in conversations if c.get("status") == status]

        return len(conversations)

    def find_by_destination(self, user_id: str, destination: str) -> List[Dict[str, Any]]:
        """按目的地搜索会话"""
        index_data = self._load_index(user_id)
        conversations = index_data.get("conversations", [])

        return [
            c for c in conversations
            if destination.lower() in c.get("destination", "").lower()
        ]

    def search_conversations(self, user_id: str, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索会话（标题、目的地、标签）

        Args:
            user_id: 用户ID
            keyword: 搜索关键词

        Returns:
            List[Dict]: 匹配的会话列表
        """
        index_data = self._load_index(user_id)
        conversations = index_data.get("conversations", [])

        keyword_lower = keyword.lower()
        results = []

        for conv in conversations:
            # 搜索标题
            if keyword_lower in conv.get("title", "").lower():
                results.append(conv)
                continue

            # 搜索目的地
            if keyword_lower in conv.get("destination", "").lower():
                results.append(conv)
                continue

            # 搜索标签
            tags = conv.get("tags", [])
            if any(keyword_lower in tag.lower() for tag in tags):
                results.append(conv)
                continue

        return results

    def get_conversation_by_id_only(self, conversation_id: str) -> Optional[ConversationModel]:
        """
        仅根据 conversation_id 查找会话（不限定用户）
        注意：此方法会搜索所有用户的会话，性能较低，仅用于特定场景

        Args:
            conversation_id: 会话ID

        Returns:
            Optional[ConversationModel]: 会话对象或None
        """
        # 获取所有用户目录
        if not self.data_dir.exists():
            return None

        for user_dir in self.data_dir.iterdir():
            if not user_dir.is_dir():
                continue

            # 尝试从活跃目录加载
            conv_dir = user_dir / "conversations"
            if conv_dir.exists():
                conv_file = conv_dir / f"{conversation_id}.json"
                if conv_file.exists():
                    try:
                        with open(conv_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        return ConversationModel.from_dict(data)
                    except Exception as e:
                        logger.error(f"❌ 加载会话失败: {e}")

                # 尝试从归档目录加载
                archive_file = conv_dir / "archived" / f"{conversation_id}.json"
                if archive_file.exists():
                    try:
                        with open(archive_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        return ConversationModel.from_dict(data)
                    except Exception as e:
                        logger.error(f"❌ 加载会话失败: {e}")

        return None

    def cleanup_old_conversations(self, user_id: str, max_age_days: int = 90) -> int:
        """
        清理旧会话（自动归档）

        Args:
            user_id: 用户ID
            max_age_days: 最大天数，超过此天数的活跃会话将被归档

        Returns:
            int: 归档的会话数量
        """
        from datetime import timedelta

        cutoff_date = datetime.now() - timedelta(days=max_age_days)
        cutoff_iso = cutoff_date.isoformat()

        conversations = self.list_conversations(user_id, status="active")
        archived_count = 0

        for conv in conversations:
            updated_at = conv.get("updated_at", "")
            if updated_at < cutoff_iso:
                if self.archive_conversation(user_id, conv.get("conversation_id")):
                    archived_count += 1

        if archived_count > 0:
            logger.info(f"✅ 自动归档了 {archived_count} 个旧会话")

        return archived_count

    def switch_conversation(self, user_id: str, conversation_id: str) -> Dict[str, Any]:
        """
        切换到指定会话

        Args:
            user_id: 用户ID
            conversation_id: 会话ID

        Returns:
            Dict: {
                "success": bool,
                "message": str,
                "conversation": Optional[ConversationModel]
            }
        """
        conversation = self.load_conversation(user_id, conversation_id)

        if conversation:
            return {
                "success": True,
                "message": "会话切换成功",
                "conversation": conversation
            }
        else:
            return {
                "success": False,
                "message": "会话不存在",
                "conversation": None
            }

    def rename_conversation(self, user_id: str, conversation_id: str, new_title: str) -> Dict[str, Any]:
        """
        重命名会话

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            new_title: 新标题

        Returns:
            Dict: {"success": bool, "message": str}
        """
        try:
            conversation = self.load_conversation(user_id, conversation_id)
            if not conversation:
                return {"success": False, "message": "会话不存在"}

            conversation.update_title(new_title)
            self.save_conversation(conversation)

            return {"success": True, "message": "重命名成功"}
        except Exception as e:
            logger.error(f"❌ 重命名会话失败: {e}")
            return {"success": False, "message": f"重命名失败: {str(e)}"}

    def get_conversation_context(self, user_id: str, conversation_id: str, max_messages: int = 20) -> List[Dict[str, str]]:
        """
        获取会话的对话上下文（用于LLM）

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            max_messages: 最大消息数

        Returns:
            List[Dict]: [{"role": "user", "content": "..."}, ...]
        """
        conversation = self.load_conversation(user_id, conversation_id)
        if conversation:
            return conversation.get_conversation_context(max_messages)
        return []

    def add_message(
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
            role: 角色 (user/assistant/system)
            content: 消息内容
            **metadata: 元数据

        Returns:
            bool: 是否成功
        """
        try:
            conversation = self.load_conversation(user_id, conversation_id)
            if not conversation:
                logger.warning(f"❌ 会话不存在: {conversation_id}")
                return False

            # 🔒 归档会话安全检查：禁止向已归档或已删除的会话添加消息
            if conversation.metadata.status in ["archived", "deleted"]:
                logger.warning(f"🔒 拒绝向{conversation.metadata.status}状态的会话添加消息: {conversation_id}")
                return False

            # 获取当前消息数量（用于自动命名判断）
            message_count_before = len(conversation.messages)

            conversation.add_message(role, content, **metadata)

            # ✅ 首条用户消息自动命名：如果是该会话的第一条用户消息，自动更新会话标题
            if role == "user" and message_count_before == 0:
                # 生成标题：截取消息前20个字符
                title = self._generate_title_from_message(content)

                # 尝试从消息中提取目的地
                destination = self._extract_destination_from_message(content)

                # 如果提取到了目的地且当前是"未指定"，则更新
                if destination and conversation.trip_preferences.destination == "未指定":
                    conversation.trip_preferences.destination = destination
                    logger.info(f"✅ 自动更新目的地 {conversation_id}: {destination}")

                # 更新会话标题
                conversation.title = title
                logger.info(f"✅ 自动命名会话 {conversation_id}: {title}")

            self.save_conversation(conversation)
            logger.info(f"✅ 已添加消息到会话 {conversation_id}")
            return True
        except Exception as e:
            logger.error(f"❌ 添加消息失败: {e}")
            return False

    def add_resource(
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
        try:
            conversation = self.load_conversation(user_id, conversation_id)
            if not conversation:
                return False

            conversation.add_resource(resource_type, file_path, file_type, description)
            self.save_conversation(conversation)
            return True
        except Exception as e:
            logger.error(f"❌ 添加资源失败: {e}")
            return False

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
