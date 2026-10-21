# 让别人使用你的 AI Agent

## 快速开始

```powershell
cd D:\A-Code
.\run.ps1
```

启动后会显示三种地址：

```
   🖥  本机访问     http://127.0.0.1:8000
   📡 局域网访问   http://192.168.x.x:8000

   🌍 公网访问     https://xxx.cpolar.top
```

根据对方的位置，给他不同的地址。

---

## 方式一：局域网（同一 WiFi）

### 步骤

1. 启动服务：

```powershell
.\run.ps1 -NoTunnel
```

2. 记下显示的「局域网访问」地址，例如 `http://192.168.0.136:8000`

3. 发给对方，他连同一个 WiFi 就能打开

### 如果对方打不开

通常是防火墙拦截。用管理员权限运行：

```powershell
# 右键 PowerShell -> 以管理员身份运行
cd D:\A-Code
.\run.ps1 -SetupLan
```

会添加一条防火墙规则（TCP 8000 入站允许）。

### 注意

- 需要**同一个 WiFi**（连同一个路由器）
- 你的 IP 可能变（重连 WiFi 后），以启动时显示的为准
- 加 `-NoTunnel` 启动更快，不用等隧道建立

---

## 方式二：公网（任何地方都能访问）

### 首次配置 cpolar

1. 访问 [cpolar.com](https://www.cpolar.com/) 注册（用邮箱）
2. 登录后进入「验证」页面，复制 **Authtoken**
3. 下载 Windows 客户端，解压得到 `cpolar.exe`
4. 配置 token：

```powershell
cd D:\A-Code\tools\cpolar
.\cpolar.exe authtoken 你的authtoken
```

5. 确认 `cpolar.exe` 在 `D:\A-Code\tools\cpolar\` 目录

### 启动

```powershell
cd D:\A-Code
.\run.ps1
```

启动时会弹出 cpolar 控制台窗口，**不要关闭**（可以最小化）。

等几秒后显示：

```
   🌍 公网访问     https://xxx.cpolar.top
```

把这个链接发给对方，他在任何网络都能打开。

### 地址会变吗

cpolar 免费版**每 24 小时**轮换一次子域名，不是每次重启都变。

| 操作 | 地址 |
|------|------|
| 重启服务（默认） | **不变** |
| 加 `-NewTunnel` | 会变 |
| 超过 24 小时 | 可能变 |
| 关闭 cpolar 窗口 | 下次会变 |

所以只要不关 cpolar 窗口，地址就稳定。

---

## ⚠️ 公网访问前必须做的事

### 风险

开启公网访问后，**任何人都能打开这个地址**：
- 消耗你的 API 额度（别人问问题你付钱）
- 可能上传恶意文件到你的知识库

### 解决方法：设置访问密码

在 `D:\A-Code\.env` 里加一行：

```ini
ACCESS_PASSWORD=你自己设一个密码
```

重启服务后，打开网页会要求输入密码。

### 检查是否已设置

```powershell
type D:\A-Code\.env | findstr ACCESS_PASSWORD
```

有输出说明已设置，没输出就是没设。

---

## 常见问题

### Q: 公网地址打不开（404）

**原因**：cpolar 进程退出了，服务器上还留着域名记录。

**解决**：

```powershell
# 检查进程
Get-Process cpolar

# 没有输出就重启
cd D:\A-Code
.\run.ps1
```

### Q: 局域网地址打不开

1. 确认在同一 WiFi
2. 确认启动时用的是 `-NoTunnel` 或看的是局域网地址
3. 用管理员运行 `.\run.ps1 -SetupLan` 加防火墙规则

### Q: 端口 8000 被占用

服务会自动切换到 8001、8002...，看启动日志里的实际端口。

### Q: 换了网络后地址失效

公网地址依赖你本机网络。换 WiFi 或断网后，隧道会重建，地址可能变。

---

## 快速对照表

| 谁要访问 | 用什么命令 | 需要管理员 | 需要 cpolar |
|---------|-----------|-----------|------------|
| 自己 | `.\run.ps1 -NoTunnel` | 否 | 否 |
| 同一 WiFi 的人 | `.\run.ps1 -NoTunnel` + `-SetupLan` | 是（一次） | 否 |
| 任何地方的人 | `.\run.ps1` | 否 | 是 |

---

## 相关文档

- [README.md](README.md) —— 项目主文档
- [AI-Agent/TUNNEL.md](AI-Agent/TUNNEL.md) —— 内网穿透详细说明
- [AI-Agent/SHARE-URL.md](AI-Agent/SHARE-URL.md) —— 公网地址说明
