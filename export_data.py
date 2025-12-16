#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据导出脚本
从 reports.db 导出指定时间范围的历史数据，生成多种格式供 AI 模型消费
"""

import os
import json
import csv
import zipfile
from datetime import datetime, timedelta
import pytz
from database import get_session, Message
from report_generator import parse_block_trade_message, normalize_block_trades, build_daily_report_data
from email_sender import send_html_email, create_smtp_connection
import config
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# 时区
TZ = pytz.timezone(config.REPORT_TIMEZONE)

# 导出时间范围（东八区）
START_TIME = TZ.localize(datetime(2025, 12, 11, 16, 0, 0))
END_TIME = TZ.localize(datetime(2025, 12, 12, 16, 0, 0))

# 输出目录
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'data_export')
os.makedirs(OUTPUT_DIR, exist_ok=True)

def export_raw_messages(messages):
    """
    导出原始消息为 JSONL 格式
    """
    output_path = os.path.join(OUTPUT_DIR, 'raw_messages.jsonl')

    with open(output_path, 'w', encoding='utf-8') as f:
        for msg in messages:
            record = {
                'msg_id': msg.message_id,
                'date': msg.date.isoformat(),
                'channel': config.TARGET_CHAT_ID,
                'raw_text': msg.text
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    print(f"✓ 已生成: {output_path} ({len(messages)} 条消息)")
    return output_path

def export_normalized_trades(messages):
    """
    导出归一化交易数据为 JSONL 和 CSV 格式
    """
    # 筛选大宗交易消息（normalize_block_trades 需要 Message 对象）
    block_trades = [msg for msg in messages if msg.is_block_trade]

    # 归一化处理（不过滤，保留所有类型）
    normalized = normalize_block_trades(block_trades, filter_non_options=False)

    # 导出 JSONL
    jsonl_path = os.path.join(OUTPUT_DIR, 'normalized_trades.jsonl')
    with open(jsonl_path, 'w', encoding='utf-8') as f:
        for trade in normalized:
            f.write(json.dumps(trade, ensure_ascii=False) + '\n')

    print(f"✓ 已生成: {jsonl_path} ({len(normalized)} 笔交易)")

    # 导出 CSV
    csv_path = os.path.join(OUTPUT_DIR, 'normalized_trades.csv')
    if normalized:
        fieldnames = list(normalized[0].keys())
        with open(csv_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(normalized)

        print(f"✓ 已生成: {csv_path} ({len(normalized)} 笔交易)")

    return jsonl_path, csv_path, len(normalized)

def export_daily_snapshot(messages):
    """
    导出日报聚合快照为 JSON 格式
    """
    # 筛选大宗交易消息
    block_trades = [msg for msg in messages if msg.is_block_trade]

    # 使用 build_daily_report_data 生成聚合数据
    report_data = build_daily_report_data(
        messages=messages,
        block_trades=block_trades,
        start_date=START_TIME,
        end_date=END_TIME
    )

    # 保存为 JSON
    json_path = os.path.join(OUTPUT_DIR, 'daily_snapshot.json')
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)

    print(f"✓ 已生成: {json_path}")
    return json_path

def create_zip_package():
    """
    打包所有导出文件为 zip
    """
    zip_path = os.path.join(OUTPUT_DIR, 'telegram_trades_dataset.zip')

    files_to_zip = [
        'raw_messages.jsonl',
        'normalized_trades.jsonl',
        'normalized_trades.csv',
        'daily_snapshot.json'
    ]

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filename in files_to_zip:
            file_path = os.path.join(OUTPUT_DIR, filename)
            if os.path.exists(file_path):
                zipf.write(file_path, arcname=filename)

    print(f"✓ 已打包: {zip_path}")
    return zip_path

def send_email_with_attachment(subject: str, html_body: str, attachment_path: str, recipients: list = None) -> bool:
    """
    发送带附件的HTML邮件

    Args:
        subject: 邮件标题
        html_body: HTML正文
        attachment_path: 附件文件路径
        recipients: 收件人列表

    Returns:
        True: 发送成功
        False: 发送失败
    """
    import time
    import re

    if recipients is None:
        recipients = config.EMAIL_RECIPIENTS

    for attempt in range(2):
        try:
            # 创建混合类型邮件（支持附件）
            msg = MIMEMultipart('mixed')
            msg['From'] = config.EMAIL_SENDER
            msg['To'] = ', '.join(recipients)
            msg['Subject'] = subject

            # 添加HTML正文和纯文本备用
            msg_alternative = MIMEMultipart('alternative')
            text_body = re.sub(r'<[^>]+>', '', html_body)
            text_body = re.sub(r'\s+', ' ', text_body).strip()
            msg_alternative.attach(MIMEText(text_body, 'plain', 'utf-8'))
            msg_alternative.attach(MIMEText(html_body, 'html', 'utf-8'))
            msg.attach(msg_alternative)

            # 添加附件
            with open(attachment_path, 'rb') as f:
                part = MIMEBase('application', 'zip')
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename="{os.path.basename(attachment_path)}"')
            msg.attach(part)

            # 发送邮件
            smtp = create_smtp_connection()
            if smtp is None:
                raise Exception("SMTP connection failed")
            smtp.send_message(msg)
            smtp.quit()

            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] sent with attachment subject='{subject[:50]}'")
            return True
        except Exception as e:
            print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [EMAIL] failed attempt={attempt+1} error={e}")
            if attempt == 0:
                time.sleep(2)
    return False

def generate_email_body(message_count, trade_count):
    """
    生成邮件正文（HTML格式）
    """
    html = f"""
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; }}
            .section {{ margin: 20px 0; }}
            .field {{ margin: 5px 0; padding-left: 20px; }}
            code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        </style>
    </head>
    <body>
        <h2>📊 Telegram Trades Dataset Export</h2>

        <div class="section">
            <h3>数据范围</h3>
            <div class="field">
                <strong>时间范围:</strong> 2025-12-11 16:00 → 2025-12-12 16:00 (Asia/Shanghai)
            </div>
            <div class="field">
                <strong>原始消息数:</strong> {message_count} 条
            </div>
            <div class="field">
                <strong>归一化交易数:</strong> {trade_count} 笔
            </div>
        </div>

        <div class="section">
            <h3>文件说明</h3>

            <h4>1. raw_messages.jsonl</h4>
            <div class="field">
                Telegram 原始消息，每行一条 JSON 记录<br>
                字段: <code>msg_id</code>, <code>date</code>, <code>channel</code>, <code>raw_text</code>
            </div>

            <h4>2. normalized_trades.jsonl</h4>
            <div class="field">
                归一化交易数据，每行一笔交易的 JSON 记录<br>
                字段: <code>asset</code>, <code>exchange</code>, <code>instrument_type</code>,
                <code>strategy</code>, <code>contract</code>, <code>side</code>, <code>volume</code>,
                <code>amount_usd</code>, <code>iv</code>, <code>greeks</code>, <code>spot_price</code>,
                <code>msg_id</code>, <code>date</code>, <code>raw_text</code>
            </div>

            <h4>3. normalized_trades.csv</h4>
            <div class="field">
                与 JSONL 相同数据的 CSV 格式，方便 Excel/Pandas 读取
            </div>

            <h4>4. daily_snapshot.json</h4>
            <div class="field">
                日报聚合数据，包含:<br>
                - 基本统计 (total_messages, total_block_trades, spot_prices)<br>
                - 交易量统计 (btc_volume, eth_volume)<br>
                - TopN 排名 (btc_top_by_volume, eth_top_by_volume)<br>
                - 时间范围 (start_time, end_time)
            </div>
        </div>

        <div class="section">
            <h3>数据格式约定</h3>
            <ul>
                <li>所有文件使用 UTF-8 编码</li>
                <li>保留所有字段，包括 "Unknown" 和 null 值（表示缺失）</li>
                <li>日期时间使用 ISO 8601 格式</li>
                <li>JSONL 格式：每行一个完整的 JSON 对象</li>
            </ul>
        </div>

        <p>
            <strong>数据来源:</strong> reports.db (SQLite)<br>
            <strong>解析方法:</strong> parse_block_trade_message() + normalize_block_trades()<br>
            <strong>生成时间:</strong> {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')}
        </p>
    </body>
    </html>
    """
    return html

def main():
    """
    主函数：执行数据导出流程
    """
    print("=" * 60)
    print("数据导出任务开始")
    print("=" * 60)
    print(f"时间范围: {START_TIME.strftime('%Y-%m-%d %H:%M')} → {END_TIME.strftime('%Y-%m-%d %H:%M')}")
    print()

    # 1. 从数据库读取消息
    print("【步骤 1】从数据库读取消息...")
    session = get_session()
    try:
        messages = session.query(Message).filter(
            Message.date >= START_TIME,
            Message.date < END_TIME
        ).order_by(Message.date).all()

        print(f"✓ 读取到 {len(messages)} 条消息")
        print()
    finally:
        session.close()

    if not messages:
        print("❌ 指定时间范围内没有数据，退出")
        return

    # 2. 导出原始消息
    print("【步骤 2】导出原始消息...")
    export_raw_messages(messages)
    print()

    # 3. 导出归一化交易
    print("【步骤 3】导出归一化交易数据...")
    jsonl_path, csv_path, trade_count = export_normalized_trades(messages)
    print()

    # 4. 导出日报快照
    print("【步骤 4】导出日报聚合快照...")
    export_daily_snapshot(messages)
    print()

    # 5. 打包 zip
    print("【步骤 5】打包所有文件...")
    zip_path = create_zip_package()
    print()

    # 6. 发送邮件
    print("【步骤 6】发送邮件...")
    subject = "【DATA EXPORT】【2025-12-12】Telegram Trades Dataset"
    body_html = generate_email_body(len(messages), trade_count)

    success = send_email_with_attachment(
        subject=subject,
        html_body=body_html,
        attachment_path=zip_path,
        recipients=config.EMAIL_RECIPIENTS
    )

    if success:
        print(f"✓ 邮件已发送")
        print(f"  Subject: {subject}")
        print(f"  Recipients: {', '.join(config.EMAIL_RECIPIENTS)}")
        print(f"  Attachment: {os.path.basename(zip_path)}")
    else:
        print(f"✗ 邮件发送失败")
    print()

    # 7. 输出总结
    print("=" * 60)
    print("数据导出任务完成")
    print("=" * 60)
    print(f"生成文件:")
    print(f"  - raw_messages.jsonl ({len(messages)} 条消息)")
    print(f"  - normalized_trades.jsonl ({trade_count} 笔交易)")
    print(f"  - normalized_trades.csv ({trade_count} 笔交易)")
    print(f"  - daily_snapshot.json (1 个快照)")
    print(f"  - telegram_trades_dataset.zip (打包文件)")
    print()
    print(f"邮件发送:")
    print(f"  Subject: {subject}")
    print(f"  Recipients: {', '.join(config.EMAIL_RECIPIENTS)}")

if __name__ == '__main__':
    main()
