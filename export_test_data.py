"""
测试数据导出脚本
从 Telegram 群组拉取最近30天的原始消息，保存为 JSON 格式
用于日报模板和预警模板的测试开发
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from telethon import TelegramClient
import pytz
import config


async def export_test_messages(days=30):
    """
    导出测试用的原始消息数据

    Args:
        days: 导出最近多少天的消息，默认30天

    Returns:
        导出的消息数量
    """
    print("=" * 60)
    print("开始导出测试数据...")
    print("=" * 60)

    # 确保测试目录存在
    test_dir = os.path.join(os.path.dirname(__file__), 'tests', 'raw_messages')
    os.makedirs(test_dir, exist_ok=True)

    # 设置时区为东八区
    tz = pytz.timezone('Asia/Shanghai')

    # 计算时间范围（使用东八区时间）
    end_date = datetime.now(tz)
    start_date = end_date - timedelta(days=days)

    print(f"时间范围: {start_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"        到 {end_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"目标群组: {config.TARGET_CHAT_NAME} (ID: {config.TARGET_CHAT_ID})")
    print(f"保存路径: {test_dir}/messages_last_{days}_days.json")
    print()

    # 初始化 Telegram 客户端
    client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)

    try:
        # 启动客户端
        await client.start(phone=config.PHONE_NUMBER)
        me = await client.get_me()
        print(f"✓ 已登录: {me.first_name} (@{me.username or 'N/A'})")
        print()

        # 获取群组实体
        entity = await client.get_entity(config.TARGET_CHAT_ID)
        print(f"✓ 成功连接到群组: {entity.title}")
        print()

        # 存储消息的列表
        messages_data = []
        message_count = 0

        # 遍历消息
        print("正在拉取消息...")
        async for message in client.iter_messages(
            entity,
            offset_date=end_date.replace(tzinfo=None),  # Telethon 需要 naive datetime
            reverse=False,
            limit=None
        ):
            # 转换消息时间为东八区时间
            msg_date = message.date.replace(tzinfo=pytz.UTC).astimezone(tz)

            # 检查消息时间是否在范围内
            if msg_date < start_date:
                break

            # 只保存有文本内容的消息
            if message.text and message.text.strip():
                message_data = {
                    'message_id': message.id,
                    'date': msg_date.strftime('%Y-%m-%d %H:%M:%S'),
                    'text': message.text.strip()
                }
                messages_data.append(message_data)
                message_count += 1

                # 每 100 条消息打印一次进度
                if message_count % 100 == 0:
                    print(f"  已拉取 {message_count} 条消息...")

        print(f"\n✓ 共拉取 {message_count} 条有效消息（已过滤空消息）")

        # 保存为 JSON 文件
        if messages_data:
            filename = f"messages_last_{days}_days.json"
            filepath = os.path.join(test_dir, filename)

            # 按时间正序排序（从旧到新）
            messages_data.sort(key=lambda x: x['date'])

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(messages_data, f, ensure_ascii=False, indent=2)

            print(f"\n✓ 数据已保存到: {filepath}")
            print(f"  文件大小: {os.path.getsize(filepath) / 1024:.2f} KB")

            # 显示统计信息
            print("\n" + "=" * 60)
            print("数据统计")
            print("=" * 60)
            print(f"总消息数: {len(messages_data)}")
            print(f"时间跨度: {messages_data[0]['date']} 到 {messages_data[-1]['date']}")

            # 统计包含 #block 标签的消息
            block_count = sum(1 for msg in messages_data if '#block' in msg['text'].lower())
            print(f"包含 #block 标签: {block_count} 条")

            # 显示示例消息
            print("\n" + "=" * 60)
            print("示例消息（前3条）")
            print("=" * 60)
            for i, msg in enumerate(messages_data[:3], 1):
                print(f"\n[{i}] ID: {msg['message_id']} | 时间: {msg['date']}")
                preview = msg['text'][:100] + "..." if len(msg['text']) > 100 else msg['text']
                print(f"    内容: {preview}")
        else:
            print("\n⚠ 未找到符合条件的消息")

        return message_count

    except Exception as e:
        print(f"\n✗ 导出失败: {type(e).__name__}")
        print(f"  详情: {str(e)}")
        raise

    finally:
        # 断开连接
        await client.disconnect()
        print("\n✓ 客户端已断开连接")


async def main():
    """
    主函数：处理命令行参数并执行导出
    """
    import sys

    # 检查命令行参数
    days = 30  # 默认30天
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
            if days <= 0:
                print("⚠ 天数必须为正整数，使用默认值 30 天")
                days = 30
        except ValueError:
            print("⚠ 无效的天数参数，使用默认值 30 天")

    # 执行导出
    try:
        await export_test_messages(days)
        print("\n" + "=" * 60)
        print("✓ 测试数据导出完成！")
        print("=" * 60)
        print("\n接下来可以：")
        print("  1. 查看导出的 JSON 文件")
        print("  2. 开始设计日报模板")
        print("  3. 开始设计预警模板")
    except Exception as e:
        print("\n" + "=" * 60)
        print("✗ 导出失败")
        print("=" * 60)
        raise


if __name__ == '__main__':
    asyncio.run(main())
