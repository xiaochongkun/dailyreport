"""
自动化 Telegram 认证脚本
使用提供的验证码完成认证
"""

import asyncio
import sys
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
import config

async def auto_authenticate(verification_code: str = None):
    """
    使用提供的验证码自动完成认证
    """
    print("=" * 60)
    print("开始自动认证...")
    print("=" * 60)

    client = TelegramClient(config.SESSION_NAME, config.API_ID, config.API_HASH)

    try:
        await client.connect()

        if not await client.is_user_authorized():
            print(f"手机号: {config.PHONE_NUMBER}")

            # 发送验证码请求
            await client.send_code_request(config.PHONE_NUMBER)
            print("✓ 验证码请求已发送")
            print("\n请查看 Telegram 获取验证码")

            # 如果没有提供验证码，从命令行参数或输入获取
            if not verification_code:
                if len(sys.argv) > 1:
                    verification_code = sys.argv[1]
                    print(f"使用命令行参数提供的验证码: {verification_code}")
                else:
                    print("\n使用方法: python auto_auth.py <验证码>")
                    print("或者运行后输入验证码")
                    verification_code = input("请输入验证码: ").strip()

            # 使用验证码登录
            print(f"使用验证码: {verification_code}")
            try:
                await client.sign_in(config.PHONE_NUMBER, verification_code)
                print("✓ 验证码验证成功！")
            except SessionPasswordNeededError:
                print("\n⚠ 检测到两步验证")
                print("需要输入两步验证密码")
                return False
            except PhoneCodeInvalidError:
                print("\n✗ 验证码无效或已过期")
                print("请重新获取验证码")
                return False

        # 验证是否成功登录
        if await client.is_user_authorized():
            me = await client.get_me()
            print("\n" + "=" * 60)
            print("✓ 认证成功！")
            print("=" * 60)
            print(f"用户名: {me.username or 'N/A'}")
            print(f"姓名: {me.first_name} {me.last_name or ''}")
            print(f"用户ID: {me.id}")
            print(f"手机号: {me.phone}")
            print("=" * 60)
            return True
        else:
            print("\n✗ 认证失败")
            return False

    except Exception as e:
        print(f"\n✗ 错误: {type(e).__name__}")
        print(f"详情: {str(e)}")
        return False
    finally:
        await client.disconnect()

async def main():
    # 检查是否有命令行参数
    verification_code = sys.argv[1] if len(sys.argv) > 1 else None

    success = await auto_authenticate(verification_code)
    if success:
        print("\n✓ Session 文件已生成: telegram_session.session")
        print("✓ 现在可以启动 telegram-report 服务了！")
        print("\n运行命令:")
        print("  pm2 restart telegram-report")
    else:
        print("\n需要手动完成认证")
        print("\n使用方法:")
        print("  python .venv/bin/python auto_auth.py <验证码>")

if __name__ == '__main__':
    asyncio.run(main())
