"""
会话数据同步工具 (JSON → SQLite)
===============================
用于定期手动运行，将JSON文件数据同步到数据库作为备份

特性：
- 只读JSON，不删除JSON文件（JSON仍是主要存储）
- 支持增量同步：已存在的会话会更新数据
- 同步消息记录到messages表
- 同步资源文件记录到resources表
- 安全模式：出错不影响JSON文件

使用方法：
    python backup_conversations_to_db.py

建议：
    - 每天运行一次进行备份
    - 可以设置cron任务或计划任务自动运行
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

# 设置UTF-8输出（Windows兼容）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from core.database.repository import DatabaseRepository
from core.database.models import User, Conversation, Message, Resource
from sqlalchemy.orm import Session


def print_banner():
    """打印横幅"""
    print("\n" + "="*60)
    print("📦 会话数据备份工具 (JSON → SQLite)")
    print("="*60)
    print(f"⏰ 开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")


def print_summary(stats: dict):
    """打印统计摘要"""
    print("\n" + "="*60)
    print("✅ 同步完成!")
    print("="*60)
    print(f"📊 统计信息:")
    print(f"  • 处理用户数: {stats['users_processed']}")
    print(f"  • 新增会话: {stats['conversations_created']}")
    print(f"  • 更新会话: {stats['conversations_updated']}")
    print(f"  • 同步消息: {stats['messages_synced']}")
    print(f"  • 同步资源: {stats['resources_synced']}")
    print(f"  • 错误数量: {stats['errors']}")
    print("="*60)
    print(f"⏰ 结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("💡 提示: JSON文件未修改，数据库仅作为备份")
    print("="*60 + "\n")


def sync_messages_to_db(session: Session, conversation_id: str, messages_data: list) -> int:
    """
    同步消息到数据库

    Args:
        session: 数据库会话
        conversation_id: 会话ID
        messages_data: 消息列表数据

    Returns:
        int: 同步的消息数量
    """
    synced_count = 0

    for msg_data in messages_data:
        try:
            # 检查消息是否已存在（根据timestamp和role判断）
            timestamp_str = msg_data.get("timestamp")
            role = msg_data.get("role")

            if not timestamp_str or not role:
                continue

            # 转换timestamp字符串为datetime对象
            try:
                if isinstance(timestamp_str, str):
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                else:
                    timestamp = timestamp_str
            except:
                # 如果转换失败，使用当前时间
                timestamp = datetime.now()

            existing = session.query(Message).filter(
                Message.conversation_id == conversation_id,
                Message.role == role,
                Message.timestamp == timestamp
            ).first()

            if existing:
                # 消息已存在，跳过
                continue

            # 创建新消息记录
            message = Message(
                conversation_id=conversation_id,
                role=role,
                content=msg_data.get("content", ""),
                timestamp=timestamp,
                meta_data=msg_data.get("metadata")
            )

            session.add(message)
            synced_count += 1

        except Exception as e:
            print(f"    ⚠️  同步消息失败: {e}")
            continue

    return synced_count


def sync_resources_to_db(session: Session, conversation_id: str, resources_data: dict) -> int:
    """
    同步资源到数据库

    Args:
        session: 数据库会话
        conversation_id: 会话ID
        resources_data: 资源字典数据

    Returns:
        int: 同步的资源数量
    """
    synced_count = 0

    for resource_type in ["map_files", "generated_files", "images"]:
        files = resources_data.get(resource_type, [])

        for file_data in files:
            try:
                # 统一处理（文件可能是字典或字符串）
                if isinstance(file_data, dict):
                    file_path = file_data.get("file_path", "")
                    file_type = file_data.get("file_type", "unknown")
                    description = file_data.get("description", "")
                else:
                    file_path = str(file_data)
                    file_type = resource_type.replace("_files", "")
                    description = ""

                if not file_path:
                    continue

                # 检查资源是否已存在
                existing = session.query(Resource).filter(
                    Resource.conversation_id == conversation_id,
                    Resource.file_path == file_path
                ).first()

                if existing:
                    # 资源已存在，跳过
                    continue

                # 创建新资源记录
                resource = Resource(
                    conversation_id=conversation_id,
                    resource_type=resource_type,
                    file_path=file_path,
                    file_type=file_type,
                    description=description
                )

                session.add(resource)
                synced_count += 1

            except Exception as e:
                print(f"    ⚠️  同步资源失败: {e}")
                continue

    return synced_count


def backup_conversations_to_db():
    """主函数：将会话数据从JSON备份到数据库"""
    print_banner()

    db = DatabaseRepository()
    session = db.get_session()

    user_data_dir = Path("user_data")

    # 统计信息
    stats = {
        "users_processed": 0,
        "conversations_created": 0,
        "conversations_updated": 0,
        "messages_synced": 0,
        "resources_synced": 0,
        "errors": 0
    }

    try:
        if not user_data_dir.exists():
            print(f"❌ 用户数据目录不存在: {user_data_dir}")
            return

        # 遍历所有用户目录
        for user_dir in user_data_dir.iterdir():
            if not user_dir.is_dir():
                continue

            if user_dir.name.startswith('.'):
                continue

            print(f"\n👤 处理用户: {user_dir.name}")

            # 读取用户的会话索引文件
            conv_index_file = user_dir / "conversations.json"
            if not conv_index_file.exists():
                print(f"  ⚠️  会话索引文件不存在，跳过")
                continue

            try:
                with open(conv_index_file, 'r', encoding='utf-8') as f:
                    conv_index = json.load(f)

                user_id = user_dir.name

                # 确保用户存在于数据库
                user = session.query(User).filter(User.user_id == user_id).first()

                if not user:
                    print(f"  ⚠️  用户不存在于数据库，跳过")
                    stats['errors'] += 1
                    continue

                stats['users_processed'] += 1

                # 遍历会话列表
                conversations = conv_index.get("conversations", [])

                for conv_item in conversations:
                    if isinstance(conv_item, dict):
                        conv_id = conv_item.get("conversation_id")
                    else:
                        conv_id = conv_item
                        conv_item = {"conversation_id": conv_id}

                    if not conv_id:
                        continue

                    # 检查数据库中是否已存在该会话
                    existing = session.query(Conversation).filter(
                        Conversation.conversation_id == conv_id
                    ).first()

                    # 读取会话详细文件
                    conv_file = user_dir / "conversations" / f"{conv_id}.json"

                    # 尝试从归档目录读取
                    if not conv_file.exists():
                        archive_file = user_dir / "conversations" / "archived" / f"{conv_id}.json"
                        if archive_file.exists():
                            conv_file = archive_file

                    if not conv_file.exists():
                        print(f"    ⚠️  会话文件不存在: {conv_id[:20]}...")
                        stats['errors'] += 1
                        continue

                    with open(conv_file, 'r', encoding='utf-8') as cf:
                        conv_data = json.load(cf)

                    # 提取数据
                    trip_prefs = conv_data.get("trip_preferences", {})
                    resources = conv_data.get("resources", {})
                    messages = conv_data.get("messages", [])
                    metadata = conv_data.get("metadata", {})

                    # 准备会话数据
                    conversation_data = {
                        "conversation_id": conv_id,
                        "user_id": user_id,
                        "title": trip_prefs.get("title", conv_data.get("title", "未命名会话")),
                        "destination": trip_prefs.get("destination", ""),
                        "status": metadata.get("status", conv_data.get("status", "active")),
                        "created_at": datetime.fromisoformat(
                            metadata.get("created_at", conv_data.get("created_at", datetime.now(timezone.utc).isoformat()))
                        ),
                        "updated_at": datetime.fromisoformat(
                            metadata.get("updated_at", conv_data.get("updated_at", datetime.now(timezone.utc).isoformat()))
                        ),
                        "message_count": len(messages),
                        "has_map": len(resources.get("map_files", [])) > 0,
                        "has_files": len(resources.get("generated_files", [])) > 0,
                        "tags": trip_prefs.get("tags", []),
                        "trip_preferences": trip_prefs
                    }

                    if existing:
                        # 更新已存在的会话
                        for key, value in conversation_data.items():
                            setattr(existing, key, value)

                        stats['conversations_updated'] += 1
                        print(f"    🔄 更新会话: {conv_id[:20]}...")
                    else:
                        # 创建新会话
                        conversation = Conversation(**conversation_data)
                        session.add(conversation)
                        stats['conversations_created'] += 1
                        print(f"    ➕ 新增会话: {conv_id[:20]}...")

                    # 同步消息
                    msg_count = sync_messages_to_db(session, conv_id, messages)
                    stats['messages_synced'] += msg_count

                    # 同步资源
                    res_count = sync_resources_to_db(session, conv_id, resources)
                    stats['resources_synced'] += res_count

                    # 立即刷新以确保写入
                    session.flush()

                # 提交当前用户的所有更改
                session.commit()
                print(f"  ✅ 用户 {user_id} 同步完成")

            except Exception as e:
                stats['errors'] += 1
                print(f"  ❌ 处理用户 {user_dir.name} 时出错: {e}")
                session.rollback()

    except Exception as e:
        print(f"\n❌ 同步过程出错: {e}")
        session.rollback()
        stats['errors'] += 1

    finally:
        session.close()

    # 打印统计摘要
    print_summary(stats)


if __name__ == "__main__":
    backup_conversations_to_db()
