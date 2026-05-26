# 用户系统模块
# 注意：用户注册和登录功能已移除，等待重构
from .user_model import UserModel
from .conversation_model import ConversationModel, MessageModel, TripPreferences, MessageMetadata, ConversationMetadata, ResourceFile
from .conversation_repository import ConversationRepository
from .conversation_service import ConversationService

__all__ = [
    'UserModel',
    'ConversationModel',
    'MessageModel',
    'MessageMetadata',
    'ConversationMetadata',
    'ResourceFile',
    'TripPreferences',
    'ConversationRepository',
    'ConversationService',
]
