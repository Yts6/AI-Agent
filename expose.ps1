# 一键启动：Web 服务 + cpolar 公网隧道
# 用法：.\expose.ps1
#       .\expose.ps1 -Token 你的cpolar-authtoken   （首次配置）

param(
    [string]$Token = "",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = "D:\A-Code"
$py = Join-Path $root ".venv\Scripts\python.exe"
# cpolar 可能装在多个位置，按优先级自动探测
$cpolarCandidates = @()
$cpolarCandidates += (Join-Path $root "tools\cpolar\cpolar.exe")
$cpolarCandidates += "D:\Download\APP\cpolar\cpolar.exe"
$cpolarCandidates += (Join-Path $env:LOCALAPPDATA "cpolar\cpolar.exe")
$cpolarCandidates += "C:\Program Files\cpolar\cpolar.exe"

$cpolar = ""
foreach ($cand in $cpolarCandidates) {
    if (Test-Path $cand) { $cpolar = $cand; break }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Agent 公网发布" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 1. 检查 ----------
if (-not (Test-Path $py)) {
    Write-Host "[错误] 找不到虚拟环境" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $cpolar)) {
    Write-Host "[错误] 找不到 cpolar：$cpolar" -ForegroundColor Red
    Write-Host "请确认 cpolar.exe 存在，或放到以下任一位置：" -ForegroundColor Yellow
    $cpolarCandidates | ForEach-Object { Write-Host "  $_" -ForegroundColor DarkGray }
    exit 1
}

# ---------- 2. 安全提醒 ----------
$envFile = Join-Path $root ".env"
$hasPassword = $false
if (Test-Path $envFile) {
    $hasPassword = (Get-Content $envFile -Raw) -match "ACCESS_PASSWORD=\S+"
}

if (-not $hasPassword) {
    Write-Host "⚠️  安全警告" -ForegroundColor Yellow
    Write-Host "   你没有设置访问密码，公网暴露后任何人都能用你的 API 额度。" -ForegroundColor Yellow
    Write-Host ""
    $choice = Read-Host "   现在设置一个密码？(Y/n)"
    if ($choice -ne "n") {
        $pw = Read-Host "   输入密码"
        if ($pw) {
            Add-Content -Path $envFile -Value "ACCESS_PASSWORD=$pw" -Encoding utf8
            Write-Host "   已写入 .env，重启服务后生效" -ForegroundColor Green
            Write-Host ""
        }
    }
}

# ---------- 3. cpolar token ----------
$cpolarCfg = Join-Path $env:USERPROFILE ".cpolar\cpolar.yml"
$hasToken = (Test-Path $cpolarCfg) -and ((Get-Content $cpolarCfg -Raw -ErrorAction SilentlyContinue) -match "authtoken.*\S+")

if ($Token) {
    Write-Host "[1/4] 配置 cpolar token..." -ForegroundColor Yellow
    & $cpolar authtoken $Token
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  token 配置失败，请检查是否复制完整（不要带空格）" -ForegroundColor Red
        Read-Host "按 Enter 退出" | Out-Null
        exit 1
    }
    Write-Host "  配置成功，下次不用再传" -ForegroundColor Green
    $hasToken = $true
} elseif (-not $hasToken) {
    Write-Host ""
    Write-Host "还没有配置 cpolar token，无法开公网隧道。" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  获取步骤（2 分钟，不用实名）：" -ForegroundColor Cyan
    Write-Host "    1. 浏览器打开  https://www.cpolar.com" -ForegroundColor White
    Write-Host "    2. 右上角「免费注册」，用邮箱注册" -ForegroundColor White
    Write-Host "    3. 登录后进「验证」页面，复制 authtoken" -ForegroundColor White
    Write-Host "    4. 回来运行：" -ForegroundColor White
    Write-Host "         .\expose.ps1 -Token 你复制的token" -ForegroundColor Green
    Write-Host ""
    Write-Host "  如果只是让同一 WiFi 的人用，不需要 token：" -ForegroundColor Cyan
    Write-Host "    先运行 .\setup-lan.ps1（管理员），再用 .\start.ps1 启动" -ForegroundColor White
    Write-Host ""
    Read-Host "按 Enter 退出" | Out-Null
    exit 0
}
Write-Host "[2/3] 启动 Web 服务 (端口 $Port)..." -ForegroundColor Yellow

# 先杀掉占用端口的旧进程
$existing = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    $pid = $existing[0].OwningProcess
    Write-Host "  端口被占用 (PID $pid)，先停止..." -ForegroundColor DarkGray
    Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

$env:PYTHONIOENCODING = "utf-8"
$server = Start-Process -FilePath $py -ArgumentList @("server.py", "--host", "0.0.0.0", "--port", $Port) -WorkingDirectory ((Get-ChildItem $root -Directory | Where-Object { Test-Path (Join-Path $_.FullName "server.py") } | Select-Object -First 1).FullName) -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 6

try {
    $h = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 10
    $info = $h.Content | ConvertFrom-Json
    Write-Host "  服务已启动 (PID $($server.Id))" -ForegroundColor Green
    if ($info.auth_required) {
        Write-Host "  密码保护：已开启 ✓" -ForegroundColor Green
    } else {
        Write-Host "  密码保护：未开启 ⚠" -ForegroundColor Yellow
    }
} catch {
    Write-Host "  启动失败，请手动运行 python AI-Agent/server.py 查看错误" -ForegroundColor Red
    Read-Host "按 Enter 退出"
    exit 1
}

# ---------- 5. 局域网地址 ----------
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "本机访问：   http://127.0.0.1:$Port"
if ($ip) { Write-Host "局域网访问： http://$ip`:$Port" }
Write-Host ""

# ---------- 6. 启动隧道 ----------
Write-Host "[3/3] 启动 cpolar 隧道..." -ForegroundColor Yellow
Write-Host "      正在申请公网地址，约 10 秒..." -ForegroundColor DarkGray
Write-Host "      下方出现的 https://xxx.cpolar.cn 就是公网地址" -ForegroundColor DarkGray
Write-Host ""
Write-Host "------------------ cpolar 输出 ------------------" -ForegroundColor DarkGray

# 带 HTTP Basic Auth 双保险（cpolar 层面再拦一道）
if ($hasPassword) {
    $pwVal = (Get-Content $envFile | Select-String "^ACCESS_PASSWORD=(.+)$").Matches.Groups[1].Value
    & $cpolar http $Port -httpauth "user:$pwVal"
} else {
    & $cpolar http $Port
}