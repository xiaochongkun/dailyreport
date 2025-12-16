# Telegram Trade Alert 报告系统

一个自动化的 Telegram 消息采集和报告生成系统，用于监听 SignalPlus Trade Alert 群组的大宗交易信息，并生成每日报告。

## 📋 功能特性

✅ **实时消息监听** - 监听 Telegram 群组的新消息并保存到数据库
✅ **大宗交易警报** - 检测 #block 标签并触发实时警报
✅ **历史数据导出** - 导出最近 30 天的历史消息（JSON 格式）
✅ **定时日报生成** - 每日东八区 16:00 自动生成报告
✅ **数据持久化** - SQLite 数据库存储所有消息
✅ **结构化报告** - HTML 格式的邮件报告（包含市场指标和 Top 3 交易）

## 🏗️ 系统架构

```
dailyreport/
├── main.py                  # 主程序（整合所有组件）
├── config.py                # 配置管理
├── database.py              # 数据库模型和操作
├── message_listener.py      # 实时消息监听
├── history_export.py        # 历史数据导出
├── report_generator.py      # 日报生成
├── scheduler.py             # 定时任务调度
├── requirements.txt         # Python 依赖
├── .env.example            # 环境变量模板
├── telegram_client.py      # 基础客户端（阶段一）
├── TELEGRAM_SETUP.md       # 阶段一配置指南
└── README.md               # 本文档

生成的文件和目录：
├── data/                   # 数据目录
│   └── reports.db         # SQLite 数据库
├── history/               # 历史数据导出
│   └── history_YYYYMMDD_YYYYMMDD.json
├── reports/               # 生成的报告
│   └── daily_report_YYYYMMDD_HHMMSS.html
└── telegram_session.session  # Telegram 会话文件
```

## 🚀 快速开始

### 1. 安装依赖

```bash
cd /home/kunkka/projects/dailyreport

# 创建虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate

# 安装所有依赖
uv pip install -r requirements.txt
```

### 2. 配置系统

编辑 `config.py`，设置你的手机号（如果不是默认值）：

```python
PHONE_NUMBER = '+8613800138000'  # 替换为你的手机号
```

**注意：** API_ID、API_HASH 和 TARGET_CHAT_ID 已经预设好了，无需修改。

### 3. 首次认证

如果还没有 Telegram 会话文件，先运行基础客户端进行认证：

```bash
python telegram_client.py
```

按提示输入验证码和两步验证密码（如果有）。

### 4. 导出历史数据（可选）

建议首次运行前先导出历史数据，积累基础数据：

```bash
python main.py export
```

这将：
- 导出最近 30 天的消息到 `history/` 目录（JSON 格式）
- 提示是否同时保存到数据库（建议选择"是"）

### 5. 运行主程序

```bash
python main.py
```

系统将：
1. 初始化数据库
2. 连接到 Telegram
3. 开始监听新消息
4. 自动保存消息到数据库
5. 检测 #block 标签并触发警报
6. 每日东八区 16:00 自动生成报告

按 `Ctrl+C` 停止系统。

## 📊 使用命令

### 主程序运行

```bash
# 运行主程序（实时监听 + 定时报告）
python main.py
```

### 历史数据导出

```bash
# 导出最近 30 天的历史消息
python main.py export
```

### 测试报告生成

```bash
# 手动生成一次报告（用于测试）
python main.py report
```

### 独立测试工具

```bash
# 测试数据库初始化
python database.py

# 测试配置
python config.py

# 测试调度器
python scheduler.py

# 测试消息监听器
python message_listener.py
```

## 📈 报告内容

每日报告（东八区 16:00 - 16:00）包含以下 4 个部分：

### 1. 统计时间范围
- 报告所涵盖的日期和时间范围
- 时区信息

### 2. 当日关键市场指标
- BTC 现货价格
- ETH 现货价格

### 3. 大宗交易统计
- 总笔数
- BTC 笔数
- ETH 笔数

### 4. Top 3 影响力交易详情
按交易量排序，包含：
- 交易策略
- 交易量
- 交易所
- 合约详情
- 交易价格
- 执行 IV
- 希腊字母（Delta, Gamma, Vega, Theta, Rho）

## 🔧 配置说明

### 环境变量（可选）

可以创建 `.env` 文件覆盖 `config.py` 中的默认值：

```bash
# 复制模板
cp .env.example .env

# 编辑 .env
nano .env
```

主要配置项：

```bash
# Telegram API
API_ID=38073635
API_HASH=2c78d114834d147f1e46e0cbf9898ef6
PHONE_NUMBER=+86XXXXXXXXXXX
TARGET_CHAT_ID=-1001881744197

# 历史数据导出
HISTORY_DAYS=30

# 日报配置
REPORT_HOUR=16
REPORT_MINUTE=0
REPORT_WINDOW_HOURS=24

# 邮件配置（Phase III 实现）
EMAIL_ENABLED=false
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASSWORD=your_app_password
REPORT_RECIPIENTS=recipient@example.com
ALERT_RECIPIENTS=alert@example.com
```

## 🗄️ 数据库结构

### messages 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键，自增 |
| message_id | INTEGER | Telegram 消息 ID（唯一） |
| date | DATETIME | 消息时间戳 |
| text | TEXT | 消息内容 |
| is_block_trade | BOOLEAN | 是否为大宗交易 |
| created_at | DATETIME | 记录创建时间 |

### 数据库操作示例

```python
from database import get_session, get_messages_by_date_range
from datetime import datetime, timedelta

session = get_session()

# 查询最近 24 小时的消息
end_date = datetime.now()
start_date = end_date - timedelta(hours=24)
messages = get_messages_by_date_range(session, start_date, end_date)

print(f"找到 {len(messages)} 条消息")

session.close()
```

## 🚨 实时警报机制

当检测到包含 `#block` 标签的消息时：

1. 自动保存到数据库（`is_block_trade=True`）
2. 提取交易详情（策略、交易量、交易所等）
3. 触发 `send_alert_email()` 函数（当前为占位符）
4. 记录警报统计

**注意：** 邮件发送功能将在 Phase III 实现。

## ⏰ 定时任务

系统使用 APScheduler 管理定时任务：

- **触发时间：** 每日东八区 16:00
- **任务内容：** 生成过去 24 小时的报告
- **时间范围：** 昨天 16:00 - 今天 16:00

### 查看下次执行时间

运行主程序后会显示：

```
✓ 定时任务已设置
  任务: 每日报告生成
  触发时间: 每日 16:00 (Asia/Shanghai)
  每日报告生成: 下次执行时间 2025-12-12 16:00:00 CST
```

## 📝 日志和输出

### 实时监听日志

```
==================================================
[新消息] ID: 12345
时间: 2025-12-11 14:30:45
大宗交易: 是
内容预览: #block BTC Call Option...
==================================================
✓ 消息已保存: ID=12345, Block=True

🚨 触发大宗交易警报！
  [占位符] 发送警报邮件
  消息ID: 12345

统计: 总消息 42 | 大宗交易 5 | 警报 5
```

### 报告生成日志

```
==================================================
开始生成每日报告...
==================================================
时间范围: 2025-12-10 16:00:00 到 2025-12-11 16:00:00
时区: Asia/Shanghai

✓ 获取到 156 条消息
✓ 提取现货价格: BTC=$45123.45, ETH=$2345.67
✓ 获取到 12 条大宗交易
✓ 统计: 总笔数=12, BTC=8, ETH=4
✓ 提取 Top 3 交易

✓ 报告已保存到: /home/kunkka/projects/dailyreport/reports/daily_report_20251211_160001.html
```

## 🔐 安全提示

- ✅ `.gitignore` 已配置，防止提交敏感文件
- ✅ Session 文件包含登录凭证，请勿分享
- ✅ API_ID 和 API_HASH 已预设，请勿修改
- ⚠️ 如果修改配置，请确保不提交到 Git

## 🛠️ 故障排查

### 问题：无法连接到 Telegram

**解决方案：**
1. 检查网络连接
2. 确认 Session 文件存在
3. 重新运行 `python telegram_client.py` 认证

### 问题：数据库错误

**解决方案：**
```bash
# 删除数据库重新初始化
rm -rf data/reports.db
python database.py
```

### 问题：定时任务未触发

**解决方案：**
1. 检查系统时间和时区
2. 确认主程序持续运行
3. 查看日志中的"下次执行时间"

### 问题：消息未保存

**解决方案：**
1. 检查是否监听了正确的群组 ID
2. 确认数据库已正确初始化
3. 查看错误日志

## 📦 部署到服务器（推荐使用 pm2）

### 1. 安装 pm2

```bash
npm install -g pm2
```

### 2. 启动服务

```bash
cd /home/kunkka/projects/dailyreport
source .venv/bin/activate

# 启动主程序
pm2 start python --name telegram-report -- main.py

# 保存 pm2 配置
pm2 save

# 设置开机自启
pm2 startup
```

### 3. 管理服务

```bash
# 查看状态
pm2 ls

# 查看日志
pm2 logs telegram-report

# 重启服务
pm2 restart telegram-report

# 停止服务
pm2 stop telegram-report
```

## 📚 下一步开发（Phase III）

### 1. 消息解析增强
- 实现 `parse_block_trade_message()` 函数
- 提取交易策略、交易量、希腊字母等详细信息
- 支持多种消息格式

### 2. 邮件发送功能
- 实现 `send_alert_email()` 函数
- 实现 `send_daily_report_email()` 函数
- 配置 SMTP 服务器
- 设计 HTML 邮件模板

### 3. 数据分析
- 交易趋势分析
- 交易量统计图表
- 市场情绪指标

### 4. Web 界面
- 查看历史报告
- 实时监控面板
- 数据可视化

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可

MIT License

## 📞 支持

如有问题，请查看：
- [Telethon 文档](https://docs.telethon.dev/)
- [APScheduler 文档](https://apscheduler.readthedocs.io/)
- [SQLAlchemy 文档](https://docs.sqlalchemy.org/)

---

**最后更新：** 2025-12-11
**版本：** 2.0.0 (Phase II 完成)
