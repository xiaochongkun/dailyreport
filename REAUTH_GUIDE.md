# Telegram 重新认证指南

## 问题说明

由于 Telegram session 数据库损坏，系统需要重新进行 Telegram 认证才能启动。

## 快速认证步骤

### 步骤 1: 获取新的验证码

运行以下命令来请求验证码（这会向你的 Telegram 发送验证码）：

```bash
.venv/bin/python auto_auth.py
```

这将显示：
- 手机号: +85264915979
- 验证码请求已发送
- 请查看 Telegram 获取验证码

### 步骤 2: 输入验证码

查看你的 Telegram 应用（手机或桌面版），找到收到的验证码。

然后运行：

```bash
.venv/bin/python auto_auth.py <你的验证码>
```

例如：
```bash
.venv/bin/python auto_auth.py 12345
```

### 步骤 3: 验证成功后启动服务

如果认证成功，你会看到：
```
✓ Session 文件已生成: telegram_session.session
✓ 现在可以启动 telegram-report 服务了！
```

然后运行：
```bash
pm2 restart telegram-report
```

## 验证服务运行状态

```bash
# 查看服务状态
pm2 ls

# 查看实时日志
pm2 logs telegram-report

# 应该看到类似以下的输出：
# [4/5] 设置定时任务...
# [5/5] 启动消息监听...
# ✓ 系统已成功启动！
```

## 故障排查

### 验证码无效或已过期

如果收到 "验证码无效或已过期" 错误，请重新运行步骤 1 和步骤 2。

### 两步验证

如果你的 Telegram 账户启用了两步验证，系统会提示输入密码。这种情况下需要手动完成认证。

## 联系支持

如果遇到任何问题，请联系管理员。
