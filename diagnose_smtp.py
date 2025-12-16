"""
SMTP 连接诊断工具
帮助排查 Gmail/Workspace SMTP 连接问题
"""

import smtplib
import socket
from email.mime.text import MIMEText
import config

def test_smtp_connection():
    """测试 SMTP 连接的各个步骤"""

    print("=" * 60)
    print("SMTP 连接诊断工具")
    print("=" * 60)

    # 1. 检查配置
    print("\n[1/6] 检查配置...")
    print(f"  SMTP 服务器: {config.SMTP_SERVER}")
    print(f"  SMTP 端口: {config.SMTP_PORT}")
    print(f"  使用 TLS: {config.SMTP_USE_TLS}")
    print(f"  发件人: {config.EMAIL_SENDER}")
    print(f"  密码长度: {len(config.EMAIL_PASSWORD)} 字符")

    if not config.EMAIL_PASSWORD:
        print("  ✗ 错误: EMAIL_PASSWORD 为空")
        return False

    # 检查邮箱类型
    if '@gmail.com' in config.EMAIL_SENDER:
        print("  ℹ 检测到标准 Gmail 账号")
    else:
        domain = config.EMAIL_SENDER.split('@')[1]
        print(f"  ℹ 检测到自定义域名: {domain}")
        print(f"  ⚠ 这可能是 Google Workspace 企业邮箱")
        print(f"  ⚠ 可能需要管理员配置 SMTP 访问权限")

    # 2. 测试 DNS 解析
    print("\n[2/6] 测试 DNS 解析...")
    try:
        ip = socket.gethostbyname(config.SMTP_SERVER)
        print(f"  ✓ DNS 解析成功: {config.SMTP_SERVER} -> {ip}")
    except Exception as e:
        print(f"  ✗ DNS 解析失败: {e}")
        return False

    # 3. 测试端口连接
    print("\n[3/6] 测试端口连接...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(10)
        result = sock.connect_ex((config.SMTP_SERVER, config.SMTP_PORT))
        sock.close()
        if result == 0:
            print(f"  ✓ 端口 {config.SMTP_PORT} 可访问")
        else:
            print(f"  ✗ 端口 {config.SMTP_PORT} 无法连接")
            print(f"  提示: 检查防火墙或网络设置")
            return False
    except Exception as e:
        print(f"  ✗ 端口测试失败: {e}")
        return False

    # 4. 创建 SMTP 连接
    print("\n[4/6] 创建 SMTP 连接...")
    try:
        smtp = smtplib.SMTP(config.SMTP_SERVER, config.SMTP_PORT, timeout=10)
        print(f"  ✓ SMTP 连接已建立")
    except Exception as e:
        print(f"  ✗ SMTP 连接失败: {e}")
        return False

    # 5. 启动 TLS
    if config.SMTP_USE_TLS:
        print("\n[5/6] 启动 TLS 加密...")
        try:
            smtp.starttls()
            print(f"  ✓ TLS 加密已启动")
        except Exception as e:
            print(f"  ✗ TLS 启动失败: {e}")
            smtp.quit()
            return False
    else:
        print("\n[5/6] 跳过 TLS（未启用）")

    # 6. 测试登录
    print("\n[6/6] 测试 SMTP 登录...")
    try:
        smtp.login(config.EMAIL_SENDER, config.EMAIL_PASSWORD)
        print(f"  ✓ SMTP 登录成功！")
        smtp.quit()

        print("\n" + "=" * 60)
        print("✓ 诊断完成：所有测试通过")
        print("=" * 60)
        print("\n邮件系统应该可以正常工作。")
        return True

    except smtplib.SMTPAuthenticationError as e:
        print(f"  ✗ SMTP 认证失败: {e}")
        smtp.quit()

        print("\n" + "=" * 60)
        print("✗ 诊断结果：认证失败")
        print("=" * 60)

        # 提供详细的故障排除建议
        print("\n可能的原因和解决方案：")
        print()

        if '@gmail.com' not in config.EMAIL_SENDER:
            print("【Google Workspace 企业邮箱问题】")
            print()
            print("1. 管理员权限问题：")
            print("   - 登录 Google Workspace 管理后台")
            print("   - 导航到：安全性 → API 控制")
            print("   - 启用「不够安全的应用的访问权限」")
            print()
            print("2. SMTP 中继配置：")
            print("   - 管理后台：应用 → Gmail → 路由")
            print("   - 配置 SMTP 中继服务")
            print("   - 文档：https://support.google.com/a/answer/176600")
            print()
            print("3. 联系管理员：")
            print("   - 如果你不是域名管理员")
            print("   - 请联系 IT 部门配置 SMTP 访问权限")
            print()
        else:
            print("【Gmail 账号问题】")
            print()
            print("1. 检查应用专用密码：")
            print("   - 访问：https://myaccount.google.com/apppasswords")
            print("   - 确认密码未被撤销")
            print("   - 尝试重新生成")
            print()
            print("2. 检查两步验证：")
            print("   - 访问：https://myaccount.google.com/security")
            print("   - 确认已开启两步验证")
            print()
            print("3. 检查密码格式：")
            print("   - 应用专用密码应该是 16 位字符")
            print("   - 不包含空格")
            print()

        print("4. 临时测试方案：")
        print("   - 使用标准 @gmail.com 账号测试")
        print("   - 先验证代码是否正常工作")
        print()

        return False

    except Exception as e:
        print(f"  ✗ 登录失败: {e}")
        smtp.quit()
        return False


if __name__ == '__main__':
    test_smtp_connection()
