# 🚀 快速启动指南

完整的系统部署和运行步骤。

## 📋 前提条件

- ✅ Python 3.12+ 已安装
- ✅ uv 包管理器已安装
- ✅ 已从 https://my.telegram.org/apps 获取 API 凭证（本项目已预设）
- ✅ 有 Telegram 账号和手机号

## ⚡ 5 分钟快速部署

### 步骤 1：安装依赖（2 分钟）

```bash
cd /home/kunkka/projects/dailyreport

# 创建虚拟环境
uv venv

# 激活虚拟环境
source .venv/bin/activate

# 安装所有依赖
uv pip install -r requirements.txt
```

### 步骤 2：配置手机号（30 秒）

编辑 `config.py`，设置你的手机号：

```python
PHONE_NUMBER = '+8613800138000'  # 替换为你的手机号（国际格式）
```

**注意：** 其他配置（API_ID, API_HASH, TARGET_CHAT_ID）已预设，无需修改。

### 步骤 3：首次认证（1 分钟）

```bash
python telegram_client.py
```

按提示操作：
1. 确认手机号
2. 输入 Telegram 发送的验证码
3. 输入两步验证密码（如果启用）

成功后会显示你的账号信息和前 5 个对话框。

### 步骤 4：导出历史数据（1 分钟）

```bash
python main.py export
```

提示"是否同时保存到数据库"时，输入 `1` 选择"是"。

这将导出并保存最近 30 天的消息到数据库。

### 步骤 5：启动系统（30 秒）

```bash
python main.py
```

系统启动后会显示：

```
==================================================
Telegram Trade Alert 报告系统
==================================================

[1/5] 验证配置...
✓ 配置验证通过

[2/5] 初始化数据库...
✓ 数据库已初始化

[3/5] 连接 Telegram...
✓ 已登录: 张三 (@your_username)

[4/5] 设置消息监听器...
✓ 消息监听器已设置

[5/5] 设置定时任务...
✓ 定时任务已设置
  任务: 每日报告生成
  触发时间: 每日 16:00 (Asia/Shanghai)
  下次执行时间: 2025-12-12 16:00:00 CST

==================================================
✓ 系统初始化完成！
==================================================

系统正在运行...
按 Ctrl+C 停止
```

## ✅ 验证系统运行

### 1. 检查实时监听

发送一条测试消息到目标群组，系统会显示：

```
==================================================
[新消息] ID: 12345
时间: 2025-12-11 14:30:45
大宗交易: 否
==================================================
✓ 消息已保存: ID=12345, Block=False

统计: 总消息 1 | 大宗交易 0 | 警报 0
```

### 2. 测试大宗交易警报

发送包含 `#block` 标签的消息，系统会触发警报：

```
==================================================
[新消息] ID: 12346
时间: 2025-12-11 14:31:00
大宗交易: 是
内容预览: #block BTC Call Option...
==================================================
✓ 消息已保存: ID=12346, Block=True

🚨 触发大宗交易警报！
  [占位符] 发送警报邮件
  消息ID: 12346

统计: 总消息 2 | 大宗交易 1 | 警报 1
```

### 3. 手动生成测试报告

打开新终端：

```bash
cd /home/kunkka/projects/dailyreport
source .venv/bin/activate
python main.py report
```

报告将保存到 `reports/` 目录，可以用浏览器打开查看。

## 🚀 使用 pm2 部署（推荐）

### 安装和配置

```bash
# 确保在虚拟环境中
cd /home/kunkka/projects/dailyreport
source .venv/bin/activate

# 启动服务
pm2 start python --name telegram-report -- main.py

# 查看状态
pm2 ls

# 查看日志
pm2 logs telegram-report

# 保存配置
pm2 save

# 设置开机自启
pm2 startup
```

### pm2 常用命令

```bash
# 重启服务
pm2 restart telegram-report

# 停止服务
pm2 stop telegram-report

# 删除服务
pm2 delete telegram-report

# 查看详细信息
pm2 show telegram-report

# 查看实时日志
pm2 logs telegram-report --lines 100
```

## 📊 功能验证清单

- [ ] 依赖安装成功
- [ ] 配置文件已正确设置
- [ ] Telegram 认证成功
- [ ] 历史数据导出完成
- [ ] 主程序启动正常
- [ ] 实时消息监听工作
- [ ] 大宗交易警报触发
- [ ] 定时任务已设置
- [ ] 测试报告生成成功

## 🔧 常用操作

### 查看数据库统计

```bash
python database.py
```

### 查看当前配置

```bash
python config.py
```

### 重新导出历史数据

```bash
python main.py export
```

### 测试定时任务

```bash
python scheduler.py
```

### 测试消息监听

```bash
python message_listener.py
```

## 🐛 常见问题

### Q: 提示 "请在 config.py 中设置你的手机号"

**A:** 编辑 `config.py`，将 `PHONE_NUMBER` 设置为你的手机号：

```python
PHONE_NUMBER = '+8613800138000'  # 替换为你的手机号
```

### Q: 无法收到验证码

**A:**
1. 确认手机号格式正确（必须包含 +86 等国家代码）
2. 检查 Telegram 应用中的 "Telegram" 官方账号
3. 可能会发送短信验证码

### Q: Session 文件找不到

**A:** 重新运行认证：

```bash
rm -f telegram_session.session*
python telegram_client.py
```

### Q: 数据库错误

**A:** 删除数据库重新初始化：

```bash
rm -rf data/
python database.py
```

### Q: pm2 启动失败

**A:** 检查以下几点：
1. 确保在项目目录
2. 确保虚拟环境已激活
3. 检查 Python 路径：`which python`
4. 查看错误日志：`pm2 logs telegram-report --err`

### Q: 定时任务未触发

**A:**
1. 确认主程序持续运行
2. 检查系统时间：`date`
3. 查看"下次执行时间"是否正确

## 📞 获取帮助

- 查看详细文档：`README.md`
- 阶段一配置指南：`TELEGRAM_SETUP.md`
- Telethon 文档：https://docs.telethon.dev/

## 🎉 完成！

系统现在应该正常运行了。接下来：

1. **监控运行状态** - 定期检查 pm2 日志
2. **等待数据积累** - 让系统运行几天收集数据
3. **查看每日报告** - 每天 16:00 后查看 `reports/` 目录
4. **开发 Phase III** - 实现邮件发送和高级分析功能

---

**祝使用愉快！** 🚀
