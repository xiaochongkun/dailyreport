"""
发送项目文档到订阅邮箱
"""
import config
from email_sender import send_html_email
from datetime import datetime
import markdown2

# 读取Markdown文档
with open('PROJECT_DOCUMENTATION.md', 'r', encoding='utf-8') as f:
    md_content = f.read()

# 转换为HTML
html_content = markdown2.markdown(
    md_content,
    extras=['tables', 'fenced-code-blocks', 'header-ids', 'toc']
)

# 添加CSS样式
styled_html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", Arial, sans-serif;
            line-height: 1.6;
            max-width: 1000px;
            margin: 40px auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .container {{
            background: white;
            padding: 40px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #34495e;
            margin-top: 40px;
            border-bottom: 2px solid #ecf0f1;
            padding-bottom: 8px;
        }}
        h3 {{
            color: #7f8c8d;
            margin-top: 30px;
        }}
        code {{
            background: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
        }}
        pre {{
            background: #282c34;
            color: #abb2bf;
            padding: 15px;
            border-radius: 6px;
            overflow-x: auto;
        }}
        pre code {{
            background: none;
            color: inherit;
            padding: 0;
        }}
        table {{
            border-collapse: collapse;
            width: 100%;
            margin: 20px 0;
        }}
        th, td {{
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }}
        th {{
            background: #3498db;
            color: white;
            font-weight: bold;
        }}
        tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        blockquote {{
            border-left: 4px solid #3498db;
            padding-left: 20px;
            margin-left: 0;
            color: #555;
        }}
        .footer {{
            margin-top: 60px;
            padding-top: 20px;
            border-top: 2px solid #ecf0f1;
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        {html_content}
        <div class="footer">
            <p><strong>文档生成时间:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p><strong>项目路径:</strong> /home/kunkka/projects/dailyreport</p>
            <p><strong>维护者:</strong> kunkka@signalplus.com</p>
        </div>
    </div>
</body>
</html>
"""

# 邮件标题
subject = "📚 Telegram Trade Alert 报告系统 - 完整项目文档"

# 发送邮件
print(f"正在发送项目文档到: {', '.join(config.EMAIL_RECIPIENTS)}")
success = send_html_email(subject, styled_html)

if success:
    print(f"✅ 文档已成功发送到订阅邮箱！")
    print(f"   收件人: {', '.join(config.EMAIL_RECIPIENTS)}")
    print(f"   主题: {subject}")
else:
    print(f"❌ 文档发送失败，请检查邮件配置")
