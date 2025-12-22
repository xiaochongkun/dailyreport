# 邮件发送场景、过滤条件与订阅人配置

**生成时间**: 2025-12-22
**项目**: Telegram Trade Alert 日报系统

---

## 一、邮件订阅人配置

### 1. TEST 模式订阅人（调试/验证）

**环境变量**:
```bash
EMAIL_MODE=test
TEST_RECIPIENTS=kunkka@signalplus.com
```

**收件人清单**:
- ✅ kunkka@signalplus.com

**特征**:
- 邮件标题自动添加 `🧪 [TEST]` 前缀
- 用于调试、功能验证、测试邮件
- **绝不会发给正式订阅用户**

---

### 2. PROD 模式订阅人（线上正式）

**环境变量**:
```bash
EMAIL_MODE=prod
PROD_RECIPIENTS=parabolic.09@pm.me,kunkka@signalplus.com
```

**收件人清单**:
- ✅ parabolic.09@pm.me（正式用户）
- ✅ kunkka@signalplus.com（开发者）

**特征**:
- 邮件标题**没有** TEST 前缀
- 用于线上正式发送
- 所有订阅用户都会收到

---

## 二、邮件类型与触发场景（3+1 类）

### 类型 1: 每日日报总结（Daily Report）

**邮件类型**: `email_type=daily`

**触发条件**:
- ✅ 定时触发：每天东八区 16:00
- ✅ 无过滤条件（即使当天无交易也会发送）

**发送函数**: `send_daily_report_email_simple()`

**邮件内容**:
- 过去 24 小时交易汇总
- BTC/ETH 交易笔数和总张数
- 总消息数和大宗交易数

**收件人路由**:
- TEST 模式 → kunkka@signalplus.com
- PROD 模式 → parabolic.09@pm.me, kunkka@signalplus.com

**标题示例**:
- TEST: `🧪 [TEST] Daily Trade Report - 2025-12-22`
- PROD: `Daily Trade Report - 2025-12-22`

---

### 类型 2: 大宗订单张数预警（Volume Alert）

**邮件类型**: `email_type=alert`
**预警原因**: `alert_reasons=['volume']`

**触发条件（全部满足才发送）**:

1. ✅ **VOLUME_ALERT_ENABLED=true**（配置开关）
2. ✅ **EMAIL_ENABLED=true**（邮件总开关）
3. ✅ **OPTIONS ONLY**（必须有至少 1 条 OPTIONS 腿）
   - `options_count > 0`
   - 排除 FUTURES/PERPETUAL/SPOT
4. ✅ **交易所匹配**
   - `exchange == MONITORED_EXCHANGE`（默认: Deribit）
5. ✅ **资产 + 张数阈值**（二选一）:
   - BTC: `options_sum > BTC_VOLUME_THRESHOLD`（默认: 200）
   - ETH: `options_sum > ETH_VOLUME_THRESHOLD`（默认: 5000）
6. ❌ **跳过条件**:
   - 资产不是 BTC/ETH → SKIP
   - 未超过对应阈值 → SKIP

**发送时机**: 实时（收到消息后立即判断）

**发送函数**: `send_single_trade_alert_html()`

**邮件内容**:
- 期权腿总张数（options_sum）
- 期权腿数量（options_count）
- 张数阈值和超出幅度
- 每条期权腿详细信息（合约、方向、张数、价格、IV）
- Greeks、原始消息

**收件人路由**:
- TEST 模式 → kunkka@signalplus.com
- PROD 模式 → parabolic.09@pm.me, kunkka@signalplus.com

**标题示例**:
- TEST: `🧪 [TEST] 单笔大宗期权预警 - BTC - 2025-12-22 09:22:43 - Deribit`
- PROD: `单笔大宗期权预警 - BTC - 2025-12-22 09:22:43 - Deribit`

---

### 类型 3: 权利金净值预警（Net Premium Alert）

**邮件类型**: `email_type=alert`
**预警原因**: `alert_reasons=['premium']`

**触发条件（全部满足才发送）**:

1. ✅ **VOLUME_ALERT_ENABLED=true**（配置开关，复用）
2. ✅ **EMAIL_ENABLED=true**（邮件总开关）
3. ✅ **OPTIONS ONLY**（必须有至少 1 条 OPTIONS 腿）
   - `options_count > 0`
   - 排除 FUTURES/PERPETUAL/SPOT
4. ✅ **交易所匹配**
   - `exchange == MONITORED_EXCHANGE`（默认: Deribit）
5. ✅ **净权利金阈值**:
   - `abs(net_premium_usd) >= PREMIUM_USD_THRESHOLD`（默认: $1,000,000）
   - `net_premium_usd = premium_received_usd - premium_paid_usd`
6. ✅ **必须有有效的净权利金数据**:
   - `abs_net_premium_usd is not None`
7. ❌ **跳过条件**:
   - 无法计算净权利金（缺失 ref_price_usd） → SKIP
   - 未超过权利金阈值 → SKIP

**发送时机**: 实时（收到消息后立即判断）

**发送函数**: `send_single_trade_alert_html()`

**邮件内容**:
- 支付权利金（premium_paid_usd）- 红色
- 收到权利金（premium_received_usd）- 绿色
- 净权利金（net_premium_usd）- 带正负号，颜色区分
- 净权利金绝对值（abs_net_premium_usd）- 紫色高亮
- 权利金阈值和超出幅度
- 每条期权腿详细信息
- Greeks、原始消息

**收件人路由**:
- TEST 模式 → kunkka@signalplus.com
- PROD 模式 → parabolic.09@pm.me, kunkka@signalplus.com

**标题示例**:
- TEST: `🧪 [TEST] 单笔大宗期权预警 - BTC - 2025-12-22 09:22:43 - Deribit`
- PROD: `单笔大宗期权预警 - BTC - 2025-12-22 09:22:43 - Deribit`

---

### 类型 4: 合并预警（Volume + Premium 同时触发）

**邮件类型**: `email_type=alert`
**预警原因**: `alert_reasons=['volume', 'premium']`

**触发条件**:
- ✅ 同时满足"类型 2"和"类型 3"的所有条件

**发送规则**:
- 🚨 **只发送 1 封邮件**（不是 2 封）
- 邮件 Header 同时显示两个标签：
  - `📊 张数预警`
  - `💰 净权利金预警`

**邮件内容**:
- 同时展示张数指标和权利金指标
- 两种阈值和超出幅度都显示

**收件人路由**:
- TEST 模式 → kunkka@signalplus.com
- PROD 模式 → parabolic.09@pm.me, kunkka@signalplus.com

---

## 三、过滤条件总结表

### 全局开关

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `EMAIL_ENABLED` | false | 邮件总开关（必须为 true） |
| `VOLUME_ALERT_ENABLED` | true | 预警开关（张数+权利金复用） |
| `EMAIL_MODE` | prod | 邮件模式（test/prod） |
| `EMAIL_DRY_RUN` | false | Dry Run 模式（只打印不发送） |

### 资产 + 阈值配置

| 资产 | 张数阈值 | 权利金阈值 | 交易所 |
|------|----------|-----------|--------|
| **BTC** | 200 | $1,000,000 | Deribit |
| **ETH** | 5000 | $1,000,000 | Deribit |

### OPTIONS ONLY 硬规则

| 规则 | 说明 |
|------|------|
| ✅ 必须有 OPTIONS 腿 | `options_count > 0` |
| ❌ 排除 FUTURES | `instrument_type != FUTURES` |
| ❌ 排除 PERPETUAL | `instrument_type != PERPETUAL` |
| ❌ 排除 SPOT | `instrument_type != SPOT` |

### 跳过条件汇总

| 场景 | 条件 | 日志 |
|------|------|------|
| 邮件未启用 | `EMAIL_ENABLED=false` | `[ALERT_SKIP] reason=email_disabled` |
| 预警未启用 | `VOLUME_ALERT_ENABLED=false` | `[ALERT_SKIP] reason=volume_alert_disabled` |
| 无期权腿 | `options_count == 0` | `[ALERT_SKIP] reason=no_option_legs` |
| 交易所不匹配 | `exchange != Deribit` | `[ALERT_SKIP] reason=wrong_exchange` |
| 资产不支持 | `asset not in [BTC, ETH]` | `[ALERT_SKIP] reason=unknown_asset` |
| 张数未达阈值 | `options_sum <= threshold` | `[ALERT_SKIP] reason=below_volume_threshold` |
| 权利金未达阈值 | `abs_net_premium_usd < 1M` | `[ALERT_SKIP] reason=below_premium_threshold` |
| 无权利金数据 | `abs_net_premium_usd is None` | `[ALERT_SKIP] reason=no_premium_data` |
| 两种预警都未触发 | volume=false & premium=false | `[ALERT_SKIP] reason=both_below_threshold` |

---

## 四、收件人路由逻辑

### 路由函数: `resolve_recipients(email_type, mode)`

**输入**:
- `email_type`: 邮件类型 ('daily', 'alert')
- `mode`: 邮件模式 ('test', 'prod', None=自动从 config 读取)

**输出**:
- `(recipients_list, resolved_mode)`: 收件人列表, 实际使用的模式

**路由规则**:

```
IF mode == 'test':
    recipients = [kunkka@signalplus.com]
    subject = auto_add_prefix("🧪 [TEST] " + subject)
ELIF mode == 'prod':
    recipients = [parabolic.09@pm.me, kunkka@signalplus.com]
    subject = (no TEST prefix, block if contains TEST)
ELSE:
    # 默认安全：未知模式当作 test 处理
    recipients = [kunkka@signalplus.com]
    subject = auto_add_prefix("🧪 [TEST] " + subject)
```

**安全机制**:
- ✅ TEST 模式邮件标题必须包含 `🧪 [TEST]`（自动添加）
- ✅ PROD 模式邮件标题必须不包含 `🧪 [TEST]`（否则阻断发送）
- ✅ 无法识别的模式默认当作 TEST 处理（最安全）

---

## 五、结构化日志格式

### 启动时配置日志

```
[EMAIL_CFG] mode=test test_recipients=kunkka@signalplus.com prod_recipients=parabolic.09@pm.me,kunkka@signalplus.com force_test_prefix=True dry_run=False
```

### 路由日志

```
[EMAIL_ROUTE] mode=test email_type=daily recipients_count=1 recipients=kunkka@signalplus.com
[EMAIL_ROUTE] mode=prod email_type=alert recipients_count=2 recipients_sample=parabolic.09@pm.me,kunkka@signalplus.com
```

### 发送准备日志

```
[EMAIL_PREP] mode=test email_type=daily recipients_count=1 recipients_sample=kunkka@signalplus.com subject=🧪 [TEST] Daily Trade Report - 2025-12-22 msg_id=N/A report_date=2025-12-22
```

### 发送成功日志

```
[EMAIL_SENT] mode=test email_type=daily recipients_count=1 subject=🧪 [TEST] Daily Trade Report - 2025-12-22
```

### DRY RUN 日志

```
[EMAIL_DRY_RUN] mode=prod email_type=alert recipients_count=2 recipients=parabolic.09@pm.me,kunkka@signalplus.com subject=单笔大宗期权预警 - BTC - 2025-12-22 09:22:43 - Deribit
```

### 预警跳过日志

```
[ALERT_SKIP] reason=no_option_legs asset=BTC options_count=0 msg_id=343752
[ALERT_SKIP] reason=wrong_exchange exchange=Binance msg_id=343753
[ALERT_SKIP] reason=both_below_threshold asset=BTC options_sum=150 volume_threshold=200 abs_net_premium_usd=500000 premium_threshold=1000000 msg_id=343754
```

---

## 六、环境变量快速参考

### TEST 模式（调试）

```bash
export EMAIL_MODE=test
export EMAIL_ENABLED=true
export EMAIL_DRY_RUN=false  # 实际发送到 kunkka@signalplus.com

# 可选：覆盖默认配置
export TEST_RECIPIENTS=kunkka@signalplus.com
```

### PROD 模式（线上）

```bash
export EMAIL_MODE=prod
export EMAIL_ENABLED=true
export EMAIL_DRY_RUN=false  # 实际发送

# 可选：覆盖默认配置
export PROD_RECIPIENTS=parabolic.09@pm.me,kunkka@signalplus.com
```

### DRY RUN 验证

```bash
export EMAIL_MODE=prod
export EMAIL_DRY_RUN=true  # 只打印不发送，验证路由
```

---

## 七、快速问答

**Q1: 我调试时会不会误发给 parabolic.09@pm.me？**
A: ✅ 不会！只要设置 `EMAIL_MODE=test`，邮件只会发给 `kunkka@signalplus.com`。

**Q2: 线上正式发送会不会带 TEST 标记？**
A: ✅ 不会！PROD 模式下标题没有 `🧪 [TEST]` 前缀，且如果意外包含会被阻断。

**Q3: 如何验证 PROD 模式路由但不实际发送？**
A: 使用 `EMAIL_MODE=prod EMAIL_DRY_RUN=true`，会打印路由日志但不发送 SMTP。

**Q4: 同时满足张数和权利金阈值会发几封邮件？**
A: ✅ 只发 1 封！邮件会同时显示两个标签：`📊 张数预警` + `💰 净权利金预警`。

**Q5: 如何添加新的订阅用户？**
A: 修改 `PROD_RECIPIENTS` 环境变量，逗号分隔多个邮箱：
```bash
export PROD_RECIPIENTS=user1@example.com,user2@example.com,kunkka@signalplus.com
```

---

**最后更新**: 2025-12-22
**维护者**: kunkka@signalplus.com
