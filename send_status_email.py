#!/usr/bin/env python3
"""
独立邮件发送脚本 - 无数据库依赖
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

def send_status_email():
    # 读取状态文件
    with open('/home/kunkka/projects/dailyreport/RESTART_STATUS.md', 'r', encoding='utf-8') as f:
        content = f.read()

    # 邮件配置（从环境变量或使用默认值）
    smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
    smtp_port = int(os.getenv('SMTP_PORT', '587'))
    sender = os.getenv('EMAIL_SENDER', 'kunkka@signalplus.com')
    password = os.getenv('EMAIL_PASSWORD', '')
    recipient = 'kunkka@signalplus.com'

    # 构建邮件
    msg = MIMEMultipart()
    msg['From'] = sender
    msg['To'] = recipient
    msg['Subject'] = f'APScheduler 重试装饰器修复状态报告 - {datetime.now().strftime("%Y-%m-%d")}'

    # 添加正文
    msg.attach(MIMEText(content, 'plain', 'utf-8'))

    try:
        # 连接 SMTP 服务器
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 连接到 {smtp_server}:{smtp_port}...")
        smtp = smtplib.SMTP(smtp_server, smtp_port)
        smtp.starttls()

        # 登录
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 登录邮箱 {sender}...")
        smtp.login(sender, password)

        # 发送邮件
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 发送邮件到 {recipient}...")
        smtp.send_message(msg)
        smtp.quit()

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ 邮件发送成功！")
        return True

    except Exception as e:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ❌ 邮件发送失败: {e}")
        return False

if __name__ == '__main__':
    send_status_email()
