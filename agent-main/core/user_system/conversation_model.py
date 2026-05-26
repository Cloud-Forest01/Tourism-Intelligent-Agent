"""
会话数据模型类
定义旅行计划会话的结构
"""
import secrets
from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


class TripPreferences(BaseModel):
    """旅行偏好设置（会话独立）"""
    destination: str
    start_date: str
    end_date: str
    days_count: int = 1
    budget: Optional[str] = None
    selected_preferences: List[str] = []  # ["classic", "free_attractions", "budget_food"]
    user_requirements: Optional[str] = None

    def to_display_string(self) -> str:
        """转换为展示字符串"""
        prefs = [
            "🎓 经典打卡" if "classic" in self.selected_preferences else "",
            "🍜 平价美食" if "budget_food" in self.selected_preferences else "",
            "🆓 免费景点" if "free_attractions" in self.selected_preferences else "",
            "📚 文化探索" if "culture" in self.selected_preferences else "",
            "🏔️ 自然风光" if "nature" in self.selected_preferences else "",
            "📸 拍照圣地" if "photo" in self.selected_preferences else "",
        ]
        prefs_str = "、".join([p for p in prefs if p])
        return f"{prefs_str}" if prefs_str else "无特定偏好"


class MessageMetadata(BaseModel):
    """消息元数据"""
    model_used: Optional[str] = None
    tools_used: List[str] = []
    generation_time: Optional[float] = None
    has_map: bool = False
    has_images: bool = False


class MessageModel(BaseModel):
    """单条消息"""
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    metadata: Optional[MessageMetadata] = None


class ResourceFile(BaseModel):
    """生成的资源文件"""
    file_path: str
    file_type: str  # "map", "excel", "html", "image"
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    description: Optional[str] = None


class ConversationMetadata(BaseModel):
    """会话元数据"""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    status: Literal["active", "archived", "deleted"] = "active"
    deleted_at: Optional[str] = None  # 删除时间（用于软删除过期计算）
    is_pinned: bool = False
    tags: List[str] = []


class ConversationModel(BaseModel):
    """
    会话数据模型

    职责：
    - 定义会话数据结构
    - 消息管理
    - 资源引用管理
    - 序列化/反序列化
    """

    # ========== 基本信息 ==========
    conversation_id: str
    user_id: str
    title: str  # 会话标题，如 "西安3日穷游"

    # ========== 本次旅行的偏好设置 ==========
    trip_preferences: TripPreferences

    # ========== 对话历史 ==========
    messages: List[MessageModel] = []

    # ========== 生成的资源 ==========
    resources: Dict[str, List[ResourceFile]] = Field(
        default_factory=lambda: {
            "map_files": [],
            "generated_files": [],
            "images": []
        }
    )

    # ========== 元数据 ==========
    metadata: ConversationMetadata = Field(default_factory=ConversationMetadata)

    def add_message(self, role: str, content: str, **metadata_kwargs) -> MessageModel:
        """添加消息到对话历史"""
        message = MessageModel(
            role=role,
            content=content,
            metadata=MessageMetadata(**metadata_kwargs) if metadata_kwargs else None
        )
        self.messages.append(message)
        self.metadata.updated_at = datetime.now().isoformat()
        return message

    def get_messages(self, limit: Optional[int] = None) -> List[MessageModel]:
        """获取消息历史"""
        if limit:
            return self.messages[-limit:]
        return self.messages

    def get_conversation_context(self, max_messages: int = 20) -> List[Dict[str, str]]:
        """
        获取用于LLM的对话上下文

        Returns:
            List[Dict]: [{"role": "user", "content": "..."}, ...]
        """
        recent_messages = self.get_messages(limit=max_messages)
        return [
            {"role": msg.role, "content": msg.content}
            for msg in recent_messages
        ]

    def update_title(self, new_title: str):
        """更新会话标题"""
        self.title = new_title
        self.metadata.updated_at = datetime.now().isoformat()

    def add_resource(self, resource_type: str, file_path: str, file_type: str, description: Optional[str] = None):
        """
        添加生成的资源

        Args:
            resource_type: 资源类型 ("map_files", "generated_files", "images")
            file_path: 文件路径
            file_type: 文件类型 ("map", "excel", "html", "image")
            description: 描述
        """
        resource = ResourceFile(
            file_path=file_path,
            file_type=file_type,
            description=description
        )
        if resource_type not in self.resources:
            self.resources[resource_type] = []
        self.resources[resource_type].append(resource)
        self.metadata.updated_at = datetime.now().isoformat()

    def archive(self):
        """归档会话"""
        self.metadata.status = "archived"
        self.metadata.updated_at = datetime.now().isoformat()

    def delete(self):
        """删除会话（软删除）"""
        self.metadata.status = "deleted"
        self.metadata.deleted_at = datetime.now().isoformat()  # 记录删除时间
        self.metadata.updated_at = datetime.now().isoformat()

    def restore(self):
        """恢复已归档或已删除的会话"""
        self.metadata.status = "active"
        self.metadata.deleted_at = None  # 清除删除时间
        self.metadata.updated_at = datetime.now().isoformat()

    def add_tag(self, tag: str):
        """添加标签"""
        if tag not in self.metadata.tags:
            self.metadata.tags.append(tag)

    def toggle_pin(self):
        """切换置顶状态"""
        self.metadata.is_pinned = not self.metadata.is_pinned
        self.metadata.updated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "title": self.title,
            "trip_preferences": self.trip_preferences.dict(),
            "messages": [msg.dict() for msg in self.messages],
            "resources": {
                k: [r.dict() for r in v]
                for k, v in self.resources.items()
            },
            "metadata": self.metadata.dict()
        }

    def to_summary_dict(self) -> Dict[str, Any]:
        """
        转换为摘要字典（用于列表展示）

        只包含基本信息，不包含完整消息历史和资源
        """
        return {
            "conversation_id": self.conversation_id,
            "title": self.title,
            "destination": self.trip_preferences.destination,
            "created_at": self.metadata.created_at,
            "updated_at": self.metadata.updated_at,
            "status": self.metadata.status,
            "deleted_at": self.metadata.deleted_at,  # 添加删除时间
            "message_count": len(self.messages),
            "has_map": len(self.resources.get("map_files", [])) > 0,
            "has_files": len(self.resources.get("generated_files", [])) > 0,
            "is_pinned": self.metadata.is_pinned,
            "tags": self.metadata.tags
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationModel':
        """从字典创建实例"""
        # 解析消息列表
        messages = [
            MessageModel(**msg) for msg in data.get("messages", [])
        ]

        # 解析资源
        resources = data.get("resources", {})
        parsed_resources = {}
        for key, resource_list in resources.items():
            parsed_resources[key] = [
                ResourceFile(**r) for r in resource_list
            ]

        return cls(
            conversation_id=data.get("conversation_id"),
            user_id=data.get("user_id"),
            title=data.get("title"),
            trip_preferences=TripPreferences(**data.get("trip_preferences", {})),
            messages=messages,
            resources=parsed_resources,
            metadata=ConversationMetadata(**data.get("metadata", {}))
        )

    @classmethod
    def create_new(cls, user_id: str, title: str, trip_preferences: Dict[str, Any]) -> 'ConversationModel':
        """
        创建新会话

        Args:
            user_id: 用户ID
            title: 会话标题
            trip_preferences: 旅行偏好字典

        Returns:
            ConversationModel: 新会话实例
        """
        conversation_id = f"conv_{secrets.token_hex(8)}"

        return cls(
            conversation_id=conversation_id,
            user_id=user_id,
            title=title,
            trip_preferences=TripPreferences(**trip_preferences)
        )

    def __repr__(self):
        return f"<ConversationModel(id={self.conversation_id}, title={self.title}, user={self.user_id})>"
