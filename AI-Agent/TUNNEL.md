# 公网访问完整指南

本项目已内置一键发布脚本（`expose.ps1`），也支持手动配置。

---

## 快速开始（推荐）

### 第一步：注册 cpolar 拿 token

1. 打开 https://www.cpolar.com
2. 右上角「免费注册」，用邮箱注册
3. 登录后进入「验证」页面，复制 **authtoken**

### 第二步：一键发布

```powershell
cd D:\A-Code
.\expose.ps1 -Token 你复制的token
```

脚本会自动：检查密码 → 配置 token → 启动服务 → 启动隧道。

看到这样一行就是成功：

```
Forwarding    https://a1b2c3d4.r3.cpolar.cn -> http://localhost:8000
```

把 `https://a1b2c3d4.r3.cpolar.cn` 发给别人即可。

### 后续启动

token 已保存，之后直接：

```powershell
.\expose.ps1
```

---

## ⚠️ 公网使用前必须做的事

### 1. 设置访问密码

```
# 在 D:\A-Code\.env 里加一行
ACCESS_PASSWORD=你设的密码
```

浏览器会弹窗要求输入。`expose.ps1` 检测到没设密码会警告并引导设置。

服务端还有一层保护：`ACCESS_PASSWORD` 会同时用于 cpolar 的 HTTP Basic Auth，
双重拦截，即使有人猜到 URL 也进不来。

### 2. 设置 API 消费上限

去 https://platform.deepseek.com/usage 设每日上限。

---

## 手动操作

```powershell
# 服务（--host 0.0.0.0 必须，否则只有本机能访问）
cd D:\A-Code\one
D:\A-Code\.venv\Scripts\python.exe server.py --host 0.0.0.0 --port 8000

# 隧道（另开窗口）
cd D:\A-Code\tools\cpolar
.\cpolar.exe authtoken 你的token
.\cpolar.exe http 8000
```

---

## 方案对比

| 方式 | 免费 | 实名 | 地址变化 | 推荐度 |
|---|---|---|---|---|
| **cpolar**（已内置） | ✅ | 不需要 | 每 24 小时 | ⭐⭐⭐⭐⭐ |
| natapp | ✅ | 需要 | 每月 | ⭐⭐⭐ |
| ngrok.cc | ✅ | 需要 | 定期 | ⭐⭐⭐ |
| Cloudflare Tunnel | ✅ | 不需要 | 固定 | ❌ 当前网络装不上 |

### natapp

1. https://natapp.cn 注册 + **实名认证**
2. 购买免费隧道，类型 Web，端口 8000
3. `.\natapp.exe -authtoken=你的token`

### ngrok.cc

1. https://ngrok.cc 注册 + 实名
2. 开通免费隧道，端口 8000
3. `.\sunny.exe clientid 你的隧道id`

---

## 局域网访问

同一 WiFi 不用穿透：

```powershell
.\expose.ps1
```

会打印 `http://192.168.x.x:8000`。

**防火墙**：首次运行会弹窗选「允许」。没弹窗就手动：

```powershell
New-NetFirewallRule -DisplayName "AI Agent Demo" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

---

## 常见问题

| 现象 | 原因 | 解决 |
|---|---|---|
| 502 / 无法连接 | 服务挂了 | 访问 `127.0.0.1:8000/api/health` 检查 |
| 页面能开但发消息无响应 | API Key 失效 | 看服务端控制台报错 |
| 提示 authtoken 无效 | 复制有误 | 重新复制，别带空格 |
| 地址隔天失效 | cpolar 免费版 24h 换域名 | 重跑 `expose.ps1` |
| 想固定域名 | 需付费版或自建 frp | 买云服务器搭 frp |

---

## 成本估算

DeepSeek 单次对话约 1500 token ≈ **0.008 元**。

10 人每天各 20 轮 = 200 轮/天 ≈ 1.6 元/天。

配上每日上限，不会失控。