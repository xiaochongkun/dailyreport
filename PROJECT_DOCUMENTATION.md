# 📊 Telegram Trade Alert 报告系统 - 完整项目文档

**项目版本**: v3.5.0
**文档生成时间**: 2025-12-17
**负责人**: kunkka@signalplus.com

---

## 📑 目录

1. [产品定义](#产品定义)
2. [核心功能模块](#核心功能模块)
3. [数据字段定义](#数据字段定义)
4. [系统架构](#系统架构)
5. [配置参数详解](#配置参数详解)
6. [数据库结构](#数据库结构)
7. [邮件模板系统](#邮件模板系统)
8. [警报触发机制](#警报触发机制)
9. [修改指南](#修改指南)
10. [常用操作命令](#常用操作命令)

---

## 📋 产品定义

### 产品概述

**Telegram Trade Alert 报告系统**是一个自动化的加密货币大宗期权交易监控平台，主要功能包括：

1. **实时监听** - 监听 Telegram "SignalPlus Trade Alert" 群组的交易消息
2. **智能解析** - 自动解析大宗交易信息（多腿策略支持）
3. **即时预警** - 超过阈值的OPTIONS交易触发实时邮件预警
4. **每日报告** - 每日东八区16:00自动生成HTML格式日报
5. **数据持久化** - SQLite数据库存储所有历史消息

### 产品定位

- **目标用户**: 加密货币期权交易员、风控团队、市场研究员
- **核心价值**: 实时监控大宗期权交易，捕捉市场重要信号
- **差异化**: 支持多腿策略解析，OPTIONS/FUTURES/PERPETUAL自动识别

### 关键指标 (KPI)

| 指标 | 定义 | 当前阈值 |
|------|------|---------|
| BTC OPTIONS 预警阈值 | 单笔交易数量 | > 200张 |
| ETH OPTIONS 预警阈值 | 单笔交易数量 | > 5000张 |
| 监控交易所 | Deribit | 固定 |
| 日报生成时间 | 东八区每日16:00 | 固定 |
| 数据统计窗口 | 过去24小时 | 16:00-16:00 |

---

## 🔧 核心功能模块

### 1. 实时消息监听 (`message_listener.py`)

**功能描述**:
- 通过 Telethon 库监听 Telegram 群组
- 检测 `#block` 标签识别大宗交易
- 自动保存所有消息到数据库
- 触发预警邮件（OPTIONS ONLY）

**关键类/函数**:
```python
class MessageListener:
    - handle_new_message()  # 处理新消息
    - trigger_alert()       # 触发警报

async def send_alert_email(message_data):
    # 检查阈值并发送单笔预警邮件
```

**触发条件** (OPTIONS ONLY):
1. 消息包含 `#block` 标签
2. 交易所为 Deribit
3. 至少有一条期权腿 (`options_legs` 非空)
4. **任意期权腿的 volume >= 阈值**
   - BTC: 200张
   - ETH: 5000张 (正式环境) / 1000张 (测试模式)

**日志输出**:
```
[ALERT_PREP] asset=BTC exchange=Deribit options_legs=4 non_options_legs=0 options_max_volume=300 threshold=200 trigger=true
[ALERT_LEG] type=OPTIONS side=LONG contract=BTC-27FEB26-80000-P volume=225 price_btc=0.0427 total_usd=278250.0 ref=86884.71
[ALERT_SEND] option_trade asset=BTC options_max_volume=300 threshold=200 contract=BTC-27FEB26-80000-P msg_id=342245
```

### 2. 消息解析引擎 (`report_generator.py`)

**功能描述**:
- 解析 Deribit 官方格式的交易消息
- 提取完整的多腿策略信息
- 识别 OPTIONS/FUTURES/PERPETUAL 类型
- 提取希腊字母、报价、现货价格等

**核心函数**:
```python
def parse_block_trade_message(text: str) -> dict:
    """
    解析大宗交易消息

    返回字段:
        asset: BTC | ETH
        strategy: 策略描述 (如 "LONG BTC CALL")
        instrument_type: OPTIONS | FUTURES | PERPETUAL
        volume: 总数量 (用于排序)
        amount_usd: 美元总金额
        exchange: 交易所名称
        side: LONG | SHORT
        spot_price: 现货价格 (字符串格式，用于显示)

        # 多腿结构 (v3.5+ 新增)
        options_legs: [
            {
                contract: 合约名称
                side: LONG | SHORT
                volume: 数量
                price_btc: 币本位价格
                price_usd: USD价格
                total_btc: 币本位总金额
                total_usd: USD总金额
                iv: 隐含波动率
                ref_spot_usd: 参考现货价 (该腿成交时)
                bid, mark, ask: 买卖报价
                bid_size, ask_size: 报价挂单量
            },
            ...
        ]

        non_options_legs: [
            {
                contract: 合约名称
                side: LONG | SHORT
                volume: 数量
                instrument_type: FUTURES | PERPETUAL
            },
            ...
        ]

        greeks: {
            delta: Δ
            gamma: Γ
            vega: ν
            theta: Θ
            rho: ρ
        }
    """
```

**支持的消息格式**:

1. **单腿期权**:
```
**LONG BTC CALL (225.0x):**
🟢 Bought 225.0x 🔶 BTC-27FEB26-95000-C 📈 at 0.0447 ₿ ($3,883.75)
Total Bought: 10.0575 ₿ ($875.00K), **IV**: 43.45%, **Ref**: $86884.71
```

2. **多腿策略 (CUSTOM STRATEGY)**:
```
**CUSTOM BTC STRATEGY:**
🟢 Bought 75.0x 🔶 BTC-27FEB26-80000-P 📉 at 0.0427 ₿ ($3,709.98)
Total Bought: 3.2025 ₿ ($278.25K), **IV**: 46.3%, **Ref**: $86884.71
🔴 Sold 100.0x 🔶 BTC-30JAN26-80000-P 📉 at 0.0287 ₿ ($2,493.59)
Total Sold: 2.8700 ₿ ($249.36K), **IV**: 46.32%, **Ref**: $86884.71
...
📖 **Risks**: Δ: 2.12, Γ: -0.0020, ν: 423.29, Θ: 3,879.16, ρ: 60.24
```

3. **期货/永续**:
```
**BTC FUTURES SPREAD:**
🟢 Bought 500.0x BTC-PERPETUAL at $87000
```

### 3. 日报生成器 (`report_generator.py`)

**功能描述**:
- 每日16:00自动生成HTML格式日报
- 统计过去24小时的交易数据
- 提取现货价格、交易统计、Top 3交易
- 支持中文/英文模板

**核心函数**:
```python
def build_daily_report_data(messages, block_trades, start_date, end_date, top_limit=3):
    """
    生成日报数据结构

    返回字段:
        report_date: 报告日期
        start_time, end_time: 统计时间范围
        timezone: 时区
        btc_spot_price, eth_spot_price: 现货价格
        total_trades: 总交易笔数
        btc_count, eth_count: BTC/ETH交易笔数
        btc_volume, eth_volume: BTC/ETH总交易量
        top_trades: Top 3 交易详情 (按 amount_usd 降序)
    """
```

**Top 3 排序规则**:
1. **过滤**: 仅统计 OPTIONS (排除 FUTURES/PERPETUAL)
2. **排序键**: `amount_usd` (期权总权利金，单位美元)
3. **多腿处理**: 每条腿完整展示，Greeks为策略总和

**日报内容结构**:
```
📊 每日交易报告
├── 统计时间范围: 2025-12-16 16:00 - 2025-12-17 16:00 (Asia/Shanghai)
├── 当日关键市场指标
│   ├── BTC 现货价: $87,032.45
│   └── ETH 现货价: $3,245.67
├── 大宗交易统计
│   ├── 总笔数: 24
│   ├── BTC: 18笔, 总量: 4,500x
│   └── ETH: 6笔, 总量: 125,000x
└── Top 3 影响力交易
    ├── #1: BTC CUSTOM STRATEGY (4腿)
    │   ├── 交易量: 300x (最大腿)
    │   ├── 总权利金: $1,053,000
    │   ├── 期权腿详情: [腿1, 腿2, 腿3, 腿4]
    │   └── Greeks: Δ: 2.12, Γ: -0.002, ν: 423.29, Θ: 3879.16, ρ: 60.24
    ├── #2: ETH CALL (1腿)
    └── #3: BTC PUT (1腿)
```

### 4. 邮件发送模块 (`email_sender.py`)

**功能描述**:
- 发送HTML格式的预警邮件和日报
- 支持Gmail SMTP
- 中文/英文双语模板
- 自动重试机制

**核心函数**:
```python
def send_single_trade_alert_html(trade_info, message_data, threshold, lang='zh', test_mode=False):
    """
    发送单笔大宗期权预警邮件

    Args:
        trade_info: parse_block_trade_message() 返回的字典
        message_data: {message_id, date, text, is_block_trade}
        threshold: 触发阈值 (200 for BTC, 5000 for ETH)
        lang: 'zh' | 'en'
        test_mode: 是否添加 [TEST] 标记

    邮件标题格式:
        【TEST】单笔大宗期权预警 - BTC - 2025-12-17 04:40:13 - Deribit
    """

def send_daily_report_email(report_data, lang='zh'):
    """
    发送每日报告邮件

    Args:
        report_data: build_daily_report_data() 返回的字典
        lang: 'zh' | 'en'

    邮件标题格式:
        📊 每日交易报告 - 2025-12-17 - SignalPlus Trade Alert
    """
```

### 5. 定时调度器 (`scheduler.py`)

**功能描述**:
- 使用 APScheduler 管理定时任务
- 东八区时间支持
- 自动生成并发送日报
- 自动发送待发送的报告

**任务列表**:
```python
# 每日16:00生成报告
scheduler.add_job(
    func=generate_and_send_report,
    trigger='cron',
    hour=16,
    minute=0,
    timezone='Asia/Shanghai'
)

# 每日16:05发送待发送报告
scheduler.add_job(
    func=send_pending_reports_job,
    trigger='cron',
    hour=16,
    minute=5,
    timezone='Asia/Shanghai'
)
```

---

## 📊 数据字段定义

### 消息解析字段映射表

| 字段名 | 类型 | 含义 | 示例值 | 备注 |
|--------|------|------|--------|------|
| `asset` | string | 资产类型 | `"BTC"` / `"ETH"` | 必填 |
| `strategy` | string | 策略描述 | `"LONG BTC CALL"` | 简短描述 |
| `strategy_title` | string | 完整策略标题 | `"CUSTOM BTC STRATEGY"` | 从消息标题行提取 |
| `volume` | float | 总交易量 | `300.0` | 用于排序，多腿时取最大值 |
| `amount_usd` | float | 美元总金额 | `1053000.0` | **期权总权利金** (仅期权腿) |
| `exchange` | string | 交易所 | `"Deribit"` | 固定值 |
| `contract` | string | 合约名称 | `"BTC-27FEB26-80000-P"` | 单腿时显示合约，多腿时显示"(多腿)" |
| `instrument_type` | string | 工具类型 | `"OPTIONS"` / `"FUTURES"` / `"PERPETUAL"` | **预警过滤关键字段** |
| `side` | string | 交易方向 | `"LONG"` / `"SHORT"` | 买入/卖出 |
| `spot_price` | string | 现货价格 | `"$87,032.45"` | 格式化字符串，用于显示 |
| `ref_price_usd` | float | 参考现货价 | `87032.45` | 数值型，用于计算 |
| `price` | string | 单腿价格 | `"0.0427 ₿ ($3,883.75)"` | 单腿时显示 |
| `iv` | string | 隐含波动率 | `"43.45%"` | 单腿时显示 |
| `greeks.delta` | float | Delta | `2.12` | 希腊字母 Δ |
| `greeks.gamma` | float | Gamma | `-0.002` | 希腊字母 Γ |
| `greeks.vega` | float | Vega | `423.29` | 希腊字母 ν |
| `greeks.theta` | float | Theta | `3879.16` | 希腊字母 Θ |
| `greeks.rho` | float | Rho | `60.24` | 希腊字母 ρ |

### 多腿结构字段 (v3.5+)

#### `options_legs` 数组

每个期权腿包含以下字段：

| 字段名 | 类型 | 含义 | 示例值 |
|--------|------|------|--------|
| `contract` | string | 合约名称 | `"BTC-27FEB26-80000-P"` |
| `side` | string | 方向 | `"LONG"` / `"SHORT"` |
| `volume` | float | 数量 | `225.0` |
| `price_btc` | float | 币本位价格 | `0.0427` |
| `price_usd` | float | USD价格 | `3709.98` |
| `total_btc` | float | 币本位总金额 | `3.2025` |
| `total_usd` | float | USD总金额 | `278250.0` |
| `iv` | float | 隐含波动率 | `46.3` |
| `ref_spot_usd` | float | 参考现货价 | `86884.71` |
| `bid` | float | 买价 | `0.0425` |
| `bid_size` | float | 买价挂单量 | `127.0` |
| `mark` | float | 标记价 | `0.0432` |
| `ask` | float | 卖价 | `0.0435` |
| `ask_size` | float | 卖价挂单量 | `0.3` |

#### `non_options_legs` 数组

每个非期权腿包含以下字段：

| 字段名 | 类型 | 含义 | 示例值 |
|--------|------|------|--------|
| `contract` | string | 合约名称 | `"BTC-PERPETUAL"` |
| `side` | string | 方向 | `"LONG"` / `"SHORT"` |
| `volume` | float | 数量 | `500.0` |
| `instrument_type` | string | 类型 | `"FUTURES"` / `"PERPETUAL"` |

---

## 🏗️ 系统架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────┐
│              Telegram API (Telethon Client)            │
│         SignalPlus Trade Alert (-1001881744197)        │
└──────────────────────┬──────────────────────────────────┘
                       │ 实时监听 (#block 标签)
                       ▼
┌─────────────────────────────────────────────────────────┐
│         MessageListener (message_listener.py)           │
│  ┌─────────────────────────────────────────────────┐  │
│  │ handle_new_message()                            │  │
│  │  1. 检测 #block 标签                             │  │
│  │  2. 保存到 DB                                    │  │
│  │  3. 调用 send_alert_email()                     │  │
│  └─────────────────┬───────────────────────────────┘  │
└────────────────────┼─────────────────────────────────────┘
                     │
           ┌─────────┴──────────┐
           │                    │
      保存到数据库         触发预警 (OPTIONS ONLY)
           │                    │
           ▼                    ▼
┌─────────────────────┐  ┌──────────────────────────────┐
│  SQLite Database    │  │  send_alert_email()          │
│   (reports.db)      │  │  1. parse_block_trade_message│
│                     │  │  2. 检查 options_legs 非空   │
│  ┌────────────┐    │  │  3. 计算 options_max_volume  │
│  │ messages   │    │  │  4. 阈值判断: BTC>200 ETH>5000│
│  │  - id      │    │  │  5. send_single_trade_alert_html│
│  │  - msg_id  │    │  └──────────────────────────────┘
│  │  - date    │    │               │
│  │  - text    │    │               ▼
│  │  - is_block│    │  ┌──────────────────────────────┐
│  └────────────┘    │  │  Gmail SMTP                  │
│                     │  │  kunkka@signalplus.com       │
│  ┌────────────┐    │  └──────────────────────────────┘
│  │daily_reports│   │
│  │  - date    │    │
│  │  - html    │    │
│  │  - is_sent │    │
│  └────────────┘    │
└──────┬──────────────┘
       │
       │ 每日 16:00 定时查询
       ▼
┌─────────────────────────────────────────────────────────┐
│      Scheduler (scheduler.py) - APScheduler             │
│  ┌──────────────────────────────────────────────────┐  │
│  │ generate_and_send_report()                       │  │
│  │  1. 查询过去24h消息 (16:00-16:00)                │  │
│  │  2. build_daily_report_data()                    │  │
│  │  3. build_daily_report_html()                    │  │
│  │  4. 保存到 daily_reports 表                      │  │
│  └──────────────────────────────────────────────────┘  │
│                                                          │
│  ┌──────────────────────────────────────────────────┐  │
│  │ send_pending_reports_job() - 16:05               │  │
│  │  1. 查询 is_sent=False 的报告                    │  │
│  │  2. send_daily_report_email()                    │  │
│  │  3. 更新 is_sent=True                            │  │
│  └──────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 文件依赖关系

```
main.py
  ├── config.py                  # 配置加载
  ├── database.py                # 数据库初始化
  ├── message_listener.py        # 实时监听
  │     ├── database.py          # 保存消息
  │     ├── report_generator.py  # 解析消息
  │     └── email_sender.py      # 发送预警
  ├── scheduler.py               # 定时任务
  │     ├── report_generator.py  # 生成日报
  │     └── email_sender.py      # 发送日报
  └── history_export.py          # 历史数据导出 (可选)
```

---

## ⚙️ 配置参数详解

### 核心配置文件: `config.py`

#### Telegram API 配置

```python
API_ID = '38073635'                          # Telegram API ID (预设)
API_HASH = '2c78d114834d147f1e46e0cbf9898ef6' # Telegram API Hash (预设)
PHONE_NUMBER = '+85264915979'                 # 你的手机号 (需修改)
TARGET_CHAT_ID = -1001881744197              # 目标群组ID (预设)
TARGET_CHAT_NAME = 'SignalPlus Trade Alert'  # 群组名称
SESSION_DIR = '/tmp/telegram-sessions-kunkka' # Session文件目录 (本地磁盘,非NFS)
```

#### 邮件配置

```python
EMAIL_ENABLED = True                          # 邮件功能开关
SMTP_SERVER = 'smtp.gmail.com'               # SMTP服务器
SMTP_PORT = 587                               # SMTP端口
SMTP_USE_TLS = True                           # 使用TLS
EMAIL_SENDER = 'kunkka@signalplus.com'       # 发件人邮箱
EMAIL_PASSWORD = 'your_app_password'          # Gmail应用专用密码 (需配置)
EMAIL_RECIPIENTS = ['kunkka@signalplus.com'] # 收件人列表 (逗号分隔)
```

**获取Gmail应用专用密码**:
1. 访问 https://myaccount.google.com/security
2. 开启"两步验证"
3. 生成"应用专用密码"
4. 复制密码到 `.env` 文件: `EMAIL_PASSWORD=abcd efgh ijkl mnop`

#### 阈值预警配置

```python
VOLUME_ALERT_ENABLED = True                   # 预警功能开关
MONITORED_EXCHANGE = 'Deribit'                # 监控的交易所
BTC_VOLUME_THRESHOLD = 200                    # BTC OPTIONS 阈值 (张)
ETH_VOLUME_THRESHOLD = 5000                   # ETH OPTIONS 阈值 (张)
ALERT_TEST_MODE = False                       # 测试模式开关
ETH_VOLUME_THRESHOLD_TEST = 1000              # 测试模式 ETH 阈值
```

**阈值触发逻辑**:
```python
# 计算期权腿的最大 volume
options_max_volume = max([leg['volume'] for leg in options_legs], default=0)

# 判断是否触发
if asset == 'BTC':
    threshold = BTC_VOLUME_THRESHOLD  # 200
elif asset == 'ETH':
    threshold = ETH_VOLUME_THRESHOLD_TEST if ALERT_TEST_MODE else ETH_VOLUME_THRESHOLD  # 1000 or 5000

if options_max_volume > threshold:
    send_single_trade_alert_html(...)
```

#### 日报配置

```python
REPORT_TIMEZONE = 'Asia/Shanghai'             # 报告时区 (东八区)
REPORT_HOUR = 16                              # 报告生成时间 (小时)
REPORT_MINUTE = 0                             # 报告生成时间 (分钟)
REPORT_WINDOW_HOURS = 24                      # 统计窗口 (小时)
EMAIL_SEND_TIME = '16:05'                     # 邮件发送时间
REPORT_TEMPLATE_VERSION = 'v1'                # 模板版本 (v1/v2)
```

#### 数据库配置

```python
DB_DIR = './data'                             # 数据库目录
DB_PATH = './data/reports.db'                 # 数据库文件路径
DB_JOURNAL_MODE = 'DELETE'                    # SQLite journal模式 (DELETE/WAL)
```

**journal_mode 选择**:
- `DELETE`: 默认模式，稳定，适合NFS
- `WAL`: 性能更好，但NFS上可能出现 Bus error

#### 标签配置

```python
BLOCK_TRADE_TAG = '#block'                    # 大宗交易标签
SPOT_PRICE_TAG = '🏷️ Spot Prices'            # 现货价格标签
```

---

## 🗄️ 数据库结构

### `messages` 表

存储所有 Telegram 消息。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | 主键 |
| `message_id` | INTEGER | UNIQUE, NOT NULL, INDEX | Telegram 消息ID |
| `date` | DATETIME | NOT NULL, INDEX | 消息时间戳 (UTC) |
| `text` | TEXT | NULL | 消息内容 |
| `is_block_trade` | BOOLEAN | DEFAULT FALSE, INDEX | 是否为大宗交易 (#block) |
| `created_at` | DATETIME | DEFAULT UTC NOW | 记录创建时间 |

**索引**:
- `idx_messages_message_id` (UNIQUE)
- `idx_messages_date`
- `idx_messages_is_block_trade`
- `idx_messages_date_block` (联合索引: date, is_block_trade)

**查询示例**:
```python
# 查询过去24小时的大宗交易
session.query(Message).filter(
    Message.date >= start_date,
    Message.date <= end_date,
    Message.is_block_trade == True
).order_by(Message.date.desc()).all()
```

### `daily_reports` 表

存储每日报告。

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| `id` | INTEGER | PRIMARY KEY, AUTOINCREMENT | 主键 |
| `report_date` | STRING(10) | UNIQUE, NOT NULL, INDEX | 报告日期 (YYYY-MM-DD) |
| `start_time` | DATETIME | NOT NULL, INDEX | 统计开始时间 |
| `end_time` | DATETIME | NOT NULL | 统计结束时间 |
| `total_messages` | INTEGER | DEFAULT 0 | 总消息数 |
| `total_block_trades` | INTEGER | DEFAULT 0 | 总大宗交易数 |
| `btc_trade_count` | INTEGER | DEFAULT 0 | BTC 交易笔数 |
| `btc_total_volume` | INTEGER | DEFAULT 0 | BTC 总交易量 |
| `eth_trade_count` | INTEGER | DEFAULT 0 | ETH 交易笔数 |
| `eth_total_volume` | INTEGER | DEFAULT 0 | ETH 总交易量 |
| `btc_spot_price` | STRING(20) | NULL | BTC 现货价格 |
| `eth_spot_price` | STRING(20) | NULL | ETH 现货价格 |
| `report_data` | TEXT | NULL | 完整报告数据 (JSON) |
| `html_content` | TEXT | NULL | HTML 邮件内容 |
| `is_sent` | BOOLEAN | DEFAULT FALSE, INDEX | 是否已发送 |
| `sent_at` | DATETIME | NULL | 邮件发送时间 |
| `created_at` | DATETIME | DEFAULT UTC NOW | 报告生成时间 |

**索引**:
- `idx_daily_reports_report_date` (UNIQUE)
- `idx_daily_reports_start_time`
- `idx_daily_reports_is_sent`

---

## 📧 邮件模板系统

### 单笔预警邮件模板 (`send_single_trade_alert_html`)

**邮件标题**:
```
【TEST】单笔大宗期权预警 - BTC - 2025-12-17 04:40:13 - Deribit
```

**邮件结构**:
```
┌─────────────────────────────────────────────────┐
│ 🚨 单笔大宗期权预警                              │
│ Alert Type: Single Block Trade (OPTIONS ONLY)  │
│ 触发时间: 2025-12-17 04:40:13 UTC+8            │
├─────────────────────────────────────────────────┤
│ 📊 交易概览                                      │
│ • 资产: BTC                                      │
│ • 策略: CUSTOM BTC STRATEGY                     │
│ • 交易所: Deribit                                │
│ • 总交易量: 300x (最大腿)                        │
│ • 阈值: 200x                                     │
│ • 触发: ✅ 超过阈值                              │
│ • 现货价: $87,032.45                            │
├─────────────────────────────────────────────────┤
│ 📈 期权腿信息 (Options Legs)                     │
│ ┌───────────────────────────────────────────┐  │
│ │ 腿 #1: BTC-27FEB26-80000-P  ✅ >=阈值     │  │
│ │ 方向/数量: LONG 225.0x                    │  │
│ │ 价格: 0.0427 ₿ ($3,709.98)               │  │
│ │ Total: 3.2025 ₿ ($278,250)               │  │
│ │ IV: 46.30%                                │  │
│ │ Ref (现货价): $86,884.71                  │  │
│ │ Quote: bid: 0.0425 (127.0) | mark: 0.0432│  │
│ └───────────────────────────────────────────┘  │
│ ┌───────────────────────────────────────────┐  │
│ │ 腿 #2: BTC-30JAN26-80000-P  ✅ >=阈值     │  │
│ │ ... (同上结构)                            │  │
│ └───────────────────────────────────────────┘  │
│ ... (腿3, 腿4)                                  │
├─────────────────────────────────────────────────┤
│ 📖 Greeks (策略总和)                             │
│ Δ: 2.12 | Γ: -0.002 | ν: 423.29 | Θ: 3879.16 │
├─────────────────────────────────────────────────┤
│ 📝 原始消息                                      │
│ [原始Telegram消息文本]                          │
└─────────────────────────────────────────────────┘
```

**关键特性**:
- 每条腿独立展示，包含完整的价格、IV、Ref
- 阈值判断：`>=阈值` 显示红色✅标记，`<阈值` 显示灰色—
- Greeks 为策略总和 (多腿加总)
- 支持非期权腿单独展示 (FUTURES/PERPETUAL)

### 每日报告邮件模板 (`send_daily_report_email`)

**邮件标题**:
```
📊 每日交易报告 - 2025-12-17 - SignalPlus Trade Alert
```

**邮件结构**:
```
┌─────────────────────────────────────────────────┐
│ 📊 每日交易报告                                  │
│ 2025-12-16 16:00 - 2025-12-17 16:00 (UTC+8)   │
├─────────────────────────────────────────────────┤
│ 📈 当日关键市场指标                              │
│ • BTC 现货价: $87,032.45                        │
│ • ETH 现货价: $3,245.67                         │
├─────────────────────────────────────────────────┤
│ 📊 大宗交易统计                                  │
│ • 总笔数: 24                                     │
│ • BTC: 18笔, 总量: 4,500x                       │
│ • ETH: 6笔, 总量: 125,000x                      │
├─────────────────────────────────────────────────┤
│ 🏆 Top 3 影响力交易                              │
│ ┌───────────────────────────────────────────┐  │
│ │ #1 BTC CUSTOM STRATEGY                    │  │
│ │ 策略: CUSTOM BTC STRATEGY                 │  │
│ │ 交易量: 300x (最大腿)                     │  │
│ │ 总权利金: $1,053,000                      │  │
│ │ 交易所: Deribit                           │  │
│ │ 现货价: $87,032.45                        │  │
│ │                                           │  │
│ │ 期权腿 (4腿):                             │  │
│ │ • 腿1: BTC-27FEB26-80000-P LONG 225x     │  │
│ │   价格: 0.0427₿ ($3,709.98)              │  │
│ │   Total: 3.2025₿ ($278,250)              │  │
│ │   IV: 46.30% | Ref: $86,884.71           │  │
│ │ • 腿2-4: ... (同上结构)                   │  │
│ │                                           │  │
│ │ Greeks: Δ: 2.12, Γ: -0.002, ν: 423.29   │  │
│ └───────────────────────────────────────────┘  │
│ ┌───────────────────────────────────────────┐  │
│ │ #2 ETH CALL                               │  │
│ │ ... (同上结构)                            │  │
│ └───────────────────────────────────────────┘  │
│ ... (#3)                                        │
└─────────────────────────────────────────────────┘
```

**Top 3 选择规则**:
1. **过滤**: 仅统计 `instrument_type=OPTIONS` (排除 FUTURES/PERPETUAL)
2. **排序**: 按 `amount_usd` (期权总权利金) 降序
3. **多腿**: 每条腿完整展示，Greeks为策略总和

---

## 🚨 警报触发机制

### 触发流程图

```
新消息到达
    │
    ├─> 检测 #block 标签? ──No──> 仅保存到DB
    │                      │
    │                     Yes
    │                      │
    ├─> 保存到 DB (is_block_trade=True)
    │
    ├─> EMAIL_ENABLED? ──No──> 跳过预警
    │                    │
    │                   Yes
    │                    │
    ├─> parse_block_trade_message(raw_text)
    │       │
    │       ├─> 提取 options_legs 和 non_options_legs
    │       └─> 返回 trade_info
    │
    ├─> options_legs 非空? ──No──> [ALERT_SKIP] reason=no_option_legs
    │                        │
    │                       Yes
    │                        │
    ├─> exchange == 'Deribit'? ──No──> [ALERT_SKIP] reason=wrong_exchange
    │                            │
    │                           Yes
    │                            │
    ├─> 计算 options_max_volume = max([leg['volume'] for leg in options_legs])
    │
    ├─> 确定阈值:
    │       if asset == 'BTC': threshold = 200
    │       elif asset == 'ETH': threshold = 5000 (or 1000 in test mode)
    │
    ├─> [ALERT_PREP] asset={asset} options_legs={count} options_max_volume={vol} threshold={t} trigger={vol>t}
    │
    ├─> 打印每条腿: [ALERT_LEG] type=OPTIONS side={s} contract={c} volume={v} ...
    │
    ├─> options_max_volume > threshold? ──No──> [ALERT_SKIP] reason=below_threshold
    │                                      │
    │                                     Yes
    │                                      │
    ├─> [ALERT_SEND] option_trade asset={asset} options_max_volume={vol} threshold={t}
    │
    └─> send_single_trade_alert_html(trade_info, message_data, threshold, lang='zh')
            │
            └─> 发送 HTML 邮件到 EMAIL_RECIPIENTS
```

### 关键判断逻辑

```python
# 1. OPTIONS ONLY - 必须有期权腿
if not options_legs:
    print(f"[ALERT_SKIP] reason=no_option_legs")
    return

# 2. 计算期权腿的最大 volume
options_max_volume = max([leg.get('volume', 0) for leg in options_legs], default=0)

# 3. 区分 BTC/ETH 阈值
if asset == 'BTC':
    threshold = config.BTC_VOLUME_THRESHOLD  # 200
elif asset == 'ETH':
    if config.ALERT_TEST_MODE:
        threshold = config.ETH_VOLUME_THRESHOLD_TEST  # 1000
    else:
        threshold = config.ETH_VOLUME_THRESHOLD  # 5000
else:
    print(f"[ALERT_SKIP] reason=unknown_asset asset={asset}")
    return

# 4. 阈值判断 (严格大于)
if options_max_volume <= threshold:
    print(f"[ALERT_SKIP] reason=below_threshold options_max_volume={options_max_volume} threshold={threshold}")
    return

# 5. 发送预警邮件
send_single_trade_alert_html(trade_info, message_data, threshold, lang='zh')
```

---

## 🔧 修改指南

### 常见修改场景

#### 1. 修改预警阈值

**位置**: `config.py`

```python
# 修改 BTC 阈值为 300 张
BTC_VOLUME_THRESHOLD = 300

# 修改 ETH 阈值为 8000 张
ETH_VOLUME_THRESHOLD = 8000
```

**或使用 `.env` 文件**:
```bash
BTC_VOLUME_THRESHOLD=300
ETH_VOLUME_THRESHOLD=8000
```

#### 2. 修改日报生成时间

**位置**: `config.py`

```python
# 修改为每日 20:00 生成报告
REPORT_HOUR = 20
REPORT_MINUTE = 0

# 修改邮件发送时间为 20:05
EMAIL_SEND_TIME = '20:05'
```

**重启服务生效**:
```bash
pm2 restart telegram-report
```

#### 3. 添加/删除收件人

**位置**: `config.py` 或 `.env`

```python
# 多个收件人用逗号分隔
EMAIL_RECIPIENTS = ['user1@example.com', 'user2@example.com', 'user3@example.com']
```

**或 `.env` 文件**:
```bash
EMAIL_RECIPIENTS=user1@example.com,user2@example.com,user3@example.com
```

#### 4. 修改 Top N 数量

**位置**: `report_generator.py` -> `build_daily_report_data()`

```python
# 修改为 Top 5
def build_daily_report_data(messages, block_trades, start_date, end_date, top_limit=5):
    ...
```

**或在调用时指定**:
```python
report_data = build_daily_report_data(messages, block_trades, start_date, end_date, top_limit=5)
```

#### 5. 添加新的解析字段

**位置**: `report_generator.py` -> `parse_block_trade_message()`

**示例：添加 `maker_taker` 字段**:

```python
def parse_block_trade_message(text):
    result = {
        'asset': 'Unknown',
        'strategy': 'Unknown',
        'volume': 0.0,
        'maker_taker': 'Unknown',  # 新增字段
        ...
    }

    # 提取 maker_taker
    maker_taker_match = re.search(r'Maker|Taker', text, re.IGNORECASE)
    if maker_taker_match:
        result['maker_taker'] = maker_taker_match.group(0).upper()

    return result
```

**对应修改 `normalize_block_trades()`**:
```python
def normalize_block_trades(block_trades, filter_non_options=False):
    normalized.append({
        'asset': parsed.get('asset', 'Unknown'),
        'volume': parsed.get('volume', 0.0),
        'maker_taker': parsed.get('maker_taker', 'Unknown'),  # 新增
        ...
    })
```

**对应修改邮件模板**:
```python
# email_sender.py -> send_single_trade_alert_html()
html_body = f"""
<div class="field-row">
    <span class="field-label">Maker/Taker:</span>
    <span class="field-value">{trade_info.get('maker_taker', 'Unknown')}</span>
</div>
"""
```

#### 6. 修改数据库表结构

**⚠️ 谨慎操作！需要数据库迁移**

**示例：添加 `sentiment` 字段到 messages 表**

```python
# database.py
class Message(Base):
    __tablename__ = 'messages'

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, unique=True, nullable=False)
    date = Column(DateTime, nullable=False)
    text = Column(Text, nullable=True)
    is_block_trade = Column(Boolean, default=False)
    sentiment = Column(String(20), nullable=True)  # 新增字段: BULLISH/BEARISH/NEUTRAL
    created_at = Column(DateTime, default=datetime.utcnow)
```

**手动迁移数据库**:
```bash
# 方法1: 删除数据库重建 (会丢失数据!)
rm data/reports.db
python database.py

# 方法2: 使用 Alembic 进行迁移 (推荐)
# 需要先安装: pip install alembic
alembic init alembic
alembic revision --autogenerate -m "Add sentiment field"
alembic upgrade head
```

#### 7. 切换邮件语言

**位置**: `message_listener.py` 和 `scheduler.py`

**单笔预警邮件**:
```python
# message_listener.py -> send_alert_email()
success = send_single_trade_alert_html(
    trade_info=trade_info,
    message_data=message_data,
    threshold=threshold,
    lang='en'  # 修改为英文
)
```

**每日报告邮件**:
```python
# scheduler.py -> generate_and_send_report()
success = send_daily_report_email(
    report_data=report_data,
    lang='en'  # 修改为英文
)
```

---

## 🎯 常用操作命令

### 服务管理 (PM2)

```bash
# 查看服务状态
pm2 ls

# 查看日志
pm2 logs telegram-report

# 实时日志 (带过滤)
pm2 logs telegram-report --lines 100 | grep ALERT

# 重启服务
pm2 restart telegram-report

# 停止服务
pm2 stop telegram-report

# 启动服务
pm2 start telegram-report

# 删除服务
pm2 delete telegram-report

# 保存 PM2 配置
pm2 save

# 查看详细信息
pm2 info telegram-report
```

### 数据库操作

```bash
# 进入 SQLite 命令行
sqlite3 data/reports.db

# 查看表结构
.schema messages

# 查询最近10条消息
SELECT message_id, date, is_block_trade FROM messages ORDER BY date DESC LIMIT 10;

# 统计大宗交易数量
SELECT COUNT(*) FROM messages WHERE is_block_trade = 1;

# 查询今天的大宗交易
SELECT message_id, date FROM messages
WHERE is_block_trade = 1
AND date >= datetime('now', 'start of day');

# 退出
.quit
```

### 手动测试

```bash
# 激活虚拟环境
source .venv/bin/activate

# 测试单笔预警 (不发邮件)
python test_single_alert.py

# 测试单笔预警 (发送测试邮件)
python test_single_alert.py --send-test

# 指定消息ID测试
python test_single_alert.py --msg-id 342245 --send-test

# 手动生成并发送日报
python generate_yesterday_report.py

# 发送待发送的报告
python send_pending_reports.py

# 测试Ref提取
python test_alert_ref.py

# 导出历史数据
python main.py export

# 手动触发定时任务
python trigger_scheduler_job.py
```

### 日志查询

```bash
# 查询预警日志
pm2 logs telegram-report | grep "\[ALERT"

# 查询预警准备日志
pm2 logs telegram-report | grep "\[ALERT_PREP\]"

# 查询预警腿信息
pm2 logs telegram-report | grep "\[ALERT_LEG\]"

# 查询预警发送日志
pm2 logs telegram-report | grep "\[ALERT_SEND\]"

# 查询跳过的预警
pm2 logs telegram-report | grep "\[ALERT_SKIP\]"

# 查询邮件发送日志
pm2 logs telegram-report | grep "\[EMAIL\]"

# 查询数据库操作日志
pm2 logs telegram-report | grep "\[DB\]"

# 查询监听器日志
pm2 logs telegram-report | grep "\[LISTENER\]"
```

### 环境变量管理

```bash
# 查看当前配置
python config.py

# 编辑 .env 文件
nano .env

# 示例 .env 配置
cat > .env << 'EOF'
# Telegram
PHONE_NUMBER=+85264915979

# 邮件
EMAIL_ENABLED=true
EMAIL_PASSWORD=your_app_password_here
EMAIL_RECIPIENTS=kunkka@signalplus.com

# 阈值
BTC_VOLUME_THRESHOLD=200
ETH_VOLUME_THRESHOLD=5000
ALERT_TEST_MODE=false

# 日报
REPORT_HOUR=16
REPORT_MINUTE=0
EOF
```

### 重新认证 Telegram

```bash
# 删除旧的 session 文件
rm -rf /tmp/telegram-sessions-kunkka/*

# 重新认证
python telegram_client.py

# 输入验证码和两步验证密码
```

### 数据库健康检查

```bash
# Python 脚本检查
python check_db_health.py

# SQLite 命令行检查
sqlite3 data/reports.db "PRAGMA integrity_check;"

# 查看 journal_mode
sqlite3 data/reports.db "PRAGMA journal_mode;"

# 优化数据库 (VACUUM)
sqlite3 data/reports.db "VACUUM;"
```

---

## 📞 支持与联系

### 文档

- **完整文档**: `README.md`
- **快速启动**: `QUICKSTART.md`
- **项目概览**: `PROJECT_OVERVIEW.md`
- **本文档**: `PROJECT_DOCUMENTATION.md`

### 日志位置

- **PM2 日志**: `~/.pm2/logs/`
- **数据库**: `./data/reports.db`
- **历史数据**: `./history/`
- **生成报告**: `./reports/`

### 常见问题排查

| 问题 | 排查步骤 |
|------|---------|
| 邮件未发送 | 1. 检查 EMAIL_ENABLED=true<br>2. 检查 EMAIL_PASSWORD 是否正确<br>3. 查看 `pm2 logs` 中的 [EMAIL] 日志 |
| 预警未触发 | 1. 检查 VOLUME_ALERT_ENABLED=true<br>2. 检查交易量是否超过阈值<br>3. 查看 [ALERT_SKIP] 日志原因 |
| 数据库损坏 | 1. 运行 `python check_db_health.py`<br>2. 备份数据库<br>3. 执行 VACUUM 压缩 |
| Session 过期 | 1. 删除 `/tmp/telegram-sessions-kunkka/`<br>2. 重新运行 `python telegram_client.py` |

### 技术栈

- **Python**: 3.12+
- **Telegram API**: Telethon
- **数据库**: SQLite + SQLAlchemy
- **任务调度**: APScheduler
- **邮件发送**: smtplib (Gmail SMTP)
- **进程管理**: PM2

---

## 🎉 更新历史

### v3.5.0 (2025-12-17)
- ✅ 多腿策略完整解析 (`options_legs` / `non_options_legs`)
- ✅ 预警邮件显示全部腿信息
- ✅ 阈值判断基于 `options_max_volume`
- ✅ 修复 IV/Ref 提取正则表达式
- ✅ 结构化日志: `[ALERT_PREP]` / `[ALERT_LEG]`

### v3.4.0 (2025-12-16)
- ✅ 日报数据正确性修复 (5个问题)
- ✅ Ref 价格三级回退提取
- ✅ Top3 多腿完整展示
- ✅ Greeks 横向紧凑布局
- ✅ BTC/ETH 排序修正

### v3.0.0 (2025-12-15)
- ✅ 邮件发送功能完整实现
- ✅ 中文邮件模板
- ✅ 单笔预警邮件
- ✅ 每日报告邮件
- ✅ Gmail SMTP 集成

### v2.0.0 (2025-12-11)
- ✅ 实时消息监听
- ✅ 定时任务调度
- ✅ 日报生成
- ✅ 数据库持久化

---

**文档维护**: kunkka@signalplus.com
**最后更新**: 2025-12-17
**项目路径**: `/home/kunkka/projects/dailyreport`
