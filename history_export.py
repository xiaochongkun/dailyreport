"""
历史数据导出功能
从 Telegram 群组导出最近 30 天的消息并保存为 JSON 文件
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.tl.types import Message as TelegramMessage
import config


async def export_history_data(client):
    """
    导出历史数据（最近 N 天）

    Args:
        client: Telegram 客户端实例

    Returns:
        导出的消息数量
    """
    print("=" * 60)
    print("开始导出历史数据...")
    print("=" * 60)

    # 创建导出目录
    os.makedirs(config.HISTORY_EXPORT_DIR, exist_ok=True)

    # 计算时间范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=config.HISTORY_DAYS)

    print(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标群组: {config.TARGET_CHAT_NAME} (ID: {config.TARGET_CHAT_ID})")
    print(f"导出目录: {config.HISTORY_EXPORT_DIR}")
    print()

    # 存储所有消息
    all_messages = []
    message_count = 0
    block_trade_count = 0

    try:
        # 获取群组实体
        entity = await client.get_entity(config.TARGET_CHAT_ID)
        print(f"✓ 成功连接到群组: {entity.title}")
        print()

        # 遍历消息
        print("正在获取消息...")
        async for message in client.iter_messages(
            entity,
            offset_date=end_date,
            reverse=False,
            limit=None
        ):
            # 检查消息时间是否在范围内
            if message.date < start_date:
                break

            # 提取消息数据
            message_data = {
                'message_id': message.id,
                'date': message.date.isoformat(),
                'text': message.text or '',
                'is_block_trade': config.BLOCK_TRADE_TAG in (message.text or ''),
                'sender_id': message.sender_id,
                'views': message.views,
                'forwards': message.forwards,
                'replies': message.replies.replies if message.replies else 0
            }

            all_messages.append(message_data)
            message_count += 1

            if message_data['is_block_trade']:
                block_trade_count += 1

            # 每 100 条消息打印一次进度
            if message_count % 100 == 0:
                print(f"  已获取 {message_count} 条消息...")

        print(f"\n✓ 共获取 {message_count} 条消息")
        print(f"  其中大宗交易: {block_trade_count} 条")

    except Exception as e:
        print(f"\n✗ 获取消息失败: {e}")
        raise

    # 保存为 JSON 文件
    if all_messages:
        # 生成文件名（包含时间范围）
        filename = f"history_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.json"
        filepath = os.path.join(config.HISTORY_EXPORT_DIR, filename)

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({
                    'export_date': datetime.now().isoformat(),
                    'start_date': start_date.isoformat(),
                    'end_date': end_date.isoformat(),
                    'chat_id': config.TARGET_CHAT_ID,
                    'chat_name': config.TARGET_CHAT_NAME,
                    'total_messages': message_count,
                    'block_trades': block_trade_count,
                    'messages': all_messages
                }, f, ensure_ascii=False, indent=2)

            print(f"\n✓ 历史数据已保存到: {filepath}")
            print(f"  文件大小: {os.path.getsize(filepath) / 1024:.2f} KB")

        except Exception as e:
            print(f"\n✗ 保存文件失败: {e}")
            raise

    else:
        print("\n⚠ 没有找到符合条件的消息")

    print("\n" + "=" * 60)
    print("历史数据导出完成！")
    print("=" * 60)

    return message_count


async def export_and_save_to_db(client, session):
    """
    导出历史数据并保存到数据库

    Args:
        client: Telegram 客户端实例
        session: 数据库会话

    Returns:
        (导出的消息数量, 保存到数据库的消息数量)
    """
    from database import save_message

    print("=" * 60)
    print("导出历史数据并保存到数据库...")
    print("=" * 60)

    # 计算时间范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=config.HISTORY_DAYS)

    print(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S')} 到 {end_date.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"目标群组: {config.TARGET_CHAT_NAME} (ID: {config.TARGET_CHAT_ID})")
    print()

    message_count = 0
    saved_count = 0
    skipped_count = 0
    block_trade_count = 0

    try:
        # 获取群组实体
        entity = await client.get_entity(config.TARGET_CHAT_ID)
        print(f"✓ 成功连接到群组: {entity.title}")
        print()

        # 遍历消息
        print("正在获取并保存消息...")
        async for message in client.iter_messages(
            entity,
            offset_date=end_date,
            reverse=False,
            limit=None
        ):
            # 检查消息时间是否在范围内
            if message.date < start_date:
                break

            message_count += 1

            # 检查是否为大宗交易
            is_block = config.BLOCK_TRADE_TAG in (message.text or '')
            if is_block:
                block_trade_count += 1

            # 保存到数据库
            result = save_message(
                session=session,
                message_id=message.id,
                date=message.date,
                text=message.text or '',
                is_block_trade=is_block
            )

            if result:
                saved_count += 1
            else:
                skipped_count += 1

            # 每 50 条消息打印一次进度
            if message_count % 50 == 0:
                print(f"  已处理 {message_count} 条消息 (保存: {saved_count}, 跳过: {skipped_count})...")

        print(f"\n✓ 处理完成:")
        print(f"  总消息数: {message_count}")
        print(f"  保存到数据库: {saved_count}")
        print(f"  跳过（已存在）: {skipped_count}")
        print(f"  大宗交易: {block_trade_count}")

    except Exception as e:
        print(f"\n✗ 处理失败: {e}")
        raise

    print("\n" + "=" * 60)
    print("历史数据导入完成！")
    print("=" * 60)

    return message_count, saved_count


async def main():
    """主函数：导出历史数据"""
    # 验证配置
    if not config.validate_config():
        print("\n✗ 配置验证失败，请检查 config.py")
        return

    # 创建客户端
    client = TelegramClient(
        config.SESSION_NAME,
        config.API_ID,
        config.API_HASH
    )

    try:
        # 启动客户端
        await client.start(phone=config.PHONE_NUMBER)
        print("✓ Telegram 客户端已连接\n")

        # 导出历史数据到 JSON 文件
        message_count = await export_history_data(client)

        # 可选：同时保存到数据库
        print("\n是否同时保存到数据库？")
        print("1. 是")
        print("2. 否（仅导出 JSON 文件）")
        choice = input("请选择 (1/2): ").strip()

        if choice == '1':
            from database import init_database, get_session

            # 初始化数据库
            init_database()
            session = get_session()

            try:
                # 导出并保存到数据库
                total, saved = await export_and_save_to_db(client, session)
                print(f"\n✓ 共保存 {saved} 条新消息到数据库")
            finally:
                session.close()

    finally:
        await client.disconnect()
        print("\n客户端已断开连接")


if __name__ == '__main__':
    asyncio.run(main())
