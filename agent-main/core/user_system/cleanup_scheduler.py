"""
定时清理任务模块
负责定期清理过期的已删除会话
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
from pathlib import Path

from core.user_system.conversation_repository import ConversationRepository

logger = logging.getLogger(__name__)


class CleanupScheduler:
    """
    定时清理调度器

    职责：
    - 定期检查已删除的会话
    - 自动删除超过7天的deleted会话
    - 记录清理日志
    """

    # 已删除会话的保留天数
    DELETED_RETENTION_DAYS = 7

    def __init__(self, conversation_repository: ConversationRepository = None):
        """
        初始化调度器

        Args:
            conversation_repository: 会话仓储实例
        """
        self.conv_repo = conversation_repository or ConversationRepository()

    def cleanup_expired_deleted_conversations(self, user_id: str) -> Dict[str, Any]:
        """
        清理过期的已删除会话（超过7天）

        Args:
            user_id: 用户ID

        Returns:
            Dict: {
                "success": bool,
                "cleaned_count": int,
                "message": str
            }
        """
        try:
            # 获取所有会话
            conversations = self.conv_repo.list_conversations(user_id, status="all")

            # 计算过期时间点（7天前）
            expiration_time = datetime.now() - timedelta(days=self.DELETED_RETENTION_DAYS)

            cleaned_count = 0
            expired_conversations = []

            for conv in conversations:
                # 只处理已删除状态的会话
                if conv.get("status") != "deleted":
                    continue

                # 获取删除时间
                deleted_at = conv.get("deleted_at")
                if not deleted_at:
                    continue

                try:
                    # 解析删除时间
                    deleted_datetime = datetime.fromisoformat(deleted_at.replace('Z', '+00:00'))

                    # 检查是否过期
                    if deleted_datetime < expiration_time:
                        logger.info(f"🗑️ 发现过期会话: {conv.get('conversation_id')}, 删除时间: {deleted_at}")
                        expired_conversations.append(conv)

                except Exception as e:
                    logger.warning(f"⚠️ 解析删除时间失败: {deleted_at}, 错误: {e}")
                    continue

            # 永久删除过期的会话
            for conv in expired_conversations:
                conv_id = conv.get("conversation_id")
                result = self.conv_repo.delete_conversation(user_id, conv_id, permanently=True)

                if result.get("success"):
                    cleaned_count += 1
                    logger.info(f"✅ 永久删除过期会话: {conv_id}")
                else:
                    logger.warning(f"⚠️ 删除会话失败: {conv_id}, 原因: {result.get('message')}")

            if cleaned_count > 0:
                logger.info(f"🎉 清理完成: 用户 {user_id}, 删除了 {cleaned_count} 个过期会话")
            else:
                logger.debug(f"ℹ️ 无需清理: 用户 {user_id} 没有过期的已删除会话")

            return {
                "success": True,
                "cleaned_count": cleaned_count,
                "message": f"清理完成，删除了 {cleaned_count} 个过期会话"
            }

        except Exception as e:
            logger.error(f"❌ 清理过期会话失败: {e}")
            return {
                "success": False,
                "cleaned_count": 0,
                "message": f"清理失败: {str(e)}"
            }

    def cleanup_all_users(self, data_dir: str = "user_data") -> Dict[str, Any]:
        """
        清理所有用户的过期会话

        Args:
            data_dir: 用户数据目录

        Returns:
            Dict: {
                "success": bool,
                "total_cleaned": int,
                "user_count": int,
                "message": str
            }
        """
        try:
            user_data_path = Path(data_dir)
            if not user_data_path.exists():
                return {
                    "success": True,
                    "total_cleaned": 0,
                    "user_count": 0,
                    "message": "用户数据目录不存在"
                }

            # 获取所有用户目录
            user_dirs = [d for d in user_data_path.iterdir() if d.is_dir() and not d.name.startswith('.')]

            total_cleaned = 0
            user_count = 0

            for user_dir in user_dirs:
                user_id = user_dir.name
                result = self.cleanup_expired_deleted_conversations(user_id)

                if result.get("success"):
                    total_cleaned += result.get("cleaned_count", 0)
                    user_count += 1

            logger.info(f"🎉 全局清理完成: 处理了 {user_count} 个用户，删除了 {total_cleaned} 个过期会话")

            return {
                "success": True,
                "total_cleaned": total_cleaned,
                "user_count": user_count,
                "message": f"全局清理完成，删除了 {total_cleaned} 个过期会话"
            }

        except Exception as e:
            logger.error(f"❌ 全局清理失败: {e}")
            return {
                "success": False,
                "total_cleaned": 0,
                "user_count": 0,
                "message": f"全局清理失败: {str(e)}"
            }

    def get_expiration_info(self, deleted_at: str) -> Dict[str, Any]:
        """
        获取会话的过期信息

        Args:
            deleted_at: 删除时间（ISO格式字符串）

        Returns:
            Dict: {
                "deleted_at": str,
                "expiration_date": str,
                "days_remaining": int,
                "is_expired": bool,
                "will_be_deleted_on": str
            }
        """
        try:
            deleted_datetime = datetime.fromisoformat(deleted_at.replace('Z', '+00:00'))
            expiration_date = deleted_datetime + timedelta(days=self.DELETED_RETENTION_DAYS)
            now = datetime.now()

            # 计算剩余天数
            days_remaining = (expiration_date - now).days
            is_expired = days_remaining < 0

            return {
                "deleted_at": deleted_at,
                "expiration_date": expiration_date.isoformat(),
                "days_remaining": max(0, days_remaining),
                "is_expired": is_expired,
                "will_be_deleted_on": expiration_date.strftime("%Y-%m-%d %H:%M")
            }

        except Exception as e:
            logger.warning(f"⚠️ 计算过期信息失败: {e}")
            return {
                "deleted_at": deleted_at,
                "expiration_date": None,
                "days_remaining": 0,
                "is_expired": False,
                "will_be_deleted_on": "未知"
            }


# 全局单例
_cleanup_scheduler = None


def get_cleanup_scheduler() -> CleanupScheduler:
    """获取清理调度器单例"""
    global _cleanup_scheduler
    if _cleanup_scheduler is None:
        _cleanup_scheduler = CleanupScheduler()
    return _cleanup_scheduler
