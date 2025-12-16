"""
测试数据导出脚本 V2
使用 StringSession 避免 SQLite 数据库损坏问题
实时保存数据，每500条写入一次文件
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from telethon import TelegramClient
from telethon.sessions import StringSession
import pytz
import config


async def export_test_messages(days=30):
    """
    导出测试用的原始消息数据（使用 StringSession）

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

    # 读取现有的 session（如果存在）
    session_str = None
    session_file = f"{config.SESSION_NAME}.session"
    if os.path.exists(session_file):
        print("✓ 检测到现有 session，尝试加载...")
        # 使用临时客户端读取 session 字符串
        temp_client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)
        await temp_client.connect()
        if await temp_client.is_user_authorized():
            session_str = StringSession.save(temp_client.session)
            print("✓ Session 加载成功")
        await temp_client.disconnect()

    # 使用 StringSession 创建客户端
    if session_str:
        client = TelegramClient(StringSession(session_str), config.API_ID, config.API_HASH)
    else:
        # 如果没有 session，需要先认证
        print("✗ 未找到有效的 session，请先运行 auto_auth.py 完成认证")
        return 0

    try:
        # 启动客户端
        await client.start()
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

        # 临时文件路径
        filename = f"messages_last_{days}_days.json"
        filepath = os.path.join(test_dir, filename)
        temp_filepath = filepath + ".tmp"

        # 遍历消息
        print("正在拉取消息...")
        async for message in client.iter_messages(
            entity,
            offset_date=end_date.replace(tzinfo=None),
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

                # 每 500 条消息保存一次（实时备份）
                if message_count % 500 == 0:
                    print(f"  已拉取 {message_count} 条消息... (实时保存中)")
                    # 临时保存
                    with open(temp_filepath, 'w', encoding='utf-8') as f:
                        json.dump(messages_data, f, ensure_ascii=False, indent=2)
                elif message_count % 100 == 0:
                    print(f"  已拉取 {message_count} 条消息...")

        print(f"\n✓ 共拉取 {message_count} 条有效消息（已过滤空消息）")

        # 最终保存
        if messages_data:
            # 按时间正序排序（从旧到新）
            messages_data.sort(key=lambda x: x['date'])

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(messages_data, f, ensure_ascii=False, indent=2)

            # 删除临时文件
            if os.path.exists(temp_filepath):
                os.remove(temp_filepath)

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

        # 如果有临时文件，尝试恢复
        if os.path.exists(temp_filepath):
            print(f"\n✓ 检测到临时备份文件，尝试恢复...")
            try:
                os.rename(temp_filepath, filepath)
                print(f"✓ 已恢复部分数据到: {filepath}")
                with open(filepath, 'r', encoding='utf-8') as f:
                    recovered_data = json.load(f)
                print(f"  恢复的消息数: {len(recovered_data)}")
            except Exception as recover_error:
                print(f"✗ 恢复失败: {recover_error}")
        raise

    finally:
        # 断开连接（StringSession 不会有数据库问题）
        try:
            await client.disconnect()
            print("\n✓ 客户端已断开连接")
        except:
            pass


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
        print("✗ 导出过程出现错误")
        print("=" * 60)
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
