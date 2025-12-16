"""
Telegram Userbot Client - 基础配置脚本
使用 Telethon 连接 Telegram Core API，实现群组信息采集
"""

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
import asyncio
import config

# ============================================
# 使用 config.py 中的配置
# ============================================
API_ID = config.API_ID
API_HASH = config.API_HASH
PHONE_NUMBER = config.PHONE_NUMBER
SESSION_NAME = config.SESSION_NAME

# ============================================
# 客户端初始化
# ============================================
client = TelegramClient(SESSION_NAME, API_ID, API_HASH)


async def main():
    """
    主函数：处理用户认证并测试连接
    """
    print("=" * 50)
    print("Telegram Userbot 客户端启动中...")
    print("=" * 50)

    try:
        # 启动客户端并处理认证流程
        # 首次运行会提示输入验证码和两步验证密码（如果启用）
        await client.start(phone=PHONE_NUMBER)

        # 获取当前登录用户信息
        me = await client.get_me()
        print(f"\n✓ 登录成功！")
        print(f"  用户名: {me.username}")
        print(f"  姓名: {me.first_name} {me.last_name or ''}")
        print(f"  用户ID: {me.id}")
        print(f"  手机号: {me.phone}")

        # ============================================
        # 测试功能：列出前5个对话框
        # ============================================
        print("\n" + "=" * 50)
        print("获取对话框列表（前5个）...")
        print("=" * 50)

        dialogs = await client.get_dialogs(limit=5)

        for i, dialog in enumerate(dialogs, 1):
            entity = dialog.entity
            dialog_type = "未知"

            # 判断对话框类型
            if hasattr(entity, 'broadcast'):
                dialog_type = "频道" if entity.broadcast else "群组"
            elif hasattr(entity, 'bot'):
                dialog_type = "机器人" if entity.bot else "用户"
            else:
                dialog_type = "用户"

            print(f"\n[{i}] {dialog.name}")
            print(f"    类型: {dialog_type}")
            print(f"    ID: {entity.id}")
            print(f"    Username: @{entity.username if hasattr(entity, 'username') and entity.username else '无'}")

            # 显示额外信息
            if hasattr(entity, 'participants_count'):
                print(f"    成员数: {entity.participants_count}")
            if hasattr(entity, 'about'):
                about = entity.about[:50] + "..." if len(entity.about) > 50 else entity.about
                print(f"    简介: {about}")

        print("\n" + "=" * 50)
        print("✓ 测试完成！客户端工作正常")
        print("=" * 50)

    except SessionPasswordNeededError:
        print("\n⚠ 检测到两步验证，请输入密码：")
        password = input("密码: ")
        await client.start(phone=PHONE_NUMBER, password=password)
        print("✓ 两步验证通过！")

    except Exception as e:
        print(f"\n✗ 错误: {type(e).__name__}")
        print(f"  详情: {str(e)}")
        raise

    finally:
        # 断开连接
        await client.disconnect()
        print("\n客户端已断开连接")


if __name__ == '__main__':
    # 运行主函数
    asyncio.run(main())
