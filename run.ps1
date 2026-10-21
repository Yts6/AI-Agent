# ============================================================
#  AI Agent 统一启动脚本
#
#  用法:
#    .\run.ps1                  启动服务 + 自动开公网隧道
#    .\run.ps1 -NoTunnel        只本地运行，不开隧道
#    .\run.ps1 -Port 8080       指定端口
#    .\run.ps1 -NewTunnel       强制新建隧道（地址会变）
#    .\run.ps1 -SetupLan        配置局域网防火墙（需管理员）
#    .\run.ps1 -FixCpolar       修复 cpolar 服务冲突（需管理员）
# ============================================================

param(
    [int]$Port = 8000,
    [switch]$NoTunnel,
    [switch]$NewTunnel,
    [switch]$SetupLan,
    [switch]$FixCpolar
)

$ErrorActionPreference = "Continue"
$ROOT = Split-Path -Parent $MyInvocation.MyCommand.Path

# ---- 自动探测代码目录 ----
$codeDir = (Get-ChildItem $ROOT -Directory |
    Where-Object { Test-Path (Join-Path $_.FullName "server.py") } |
    Select-Object -First 1).FullName

if (-not $codeDir) {
    Write-Host ""
    Write-Host "  [错误] 找不到 server.py" -ForegroundColor Red
    Write-Host "  请确认 AI-Agent 目录存在" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "按 Enter 退出"
    exit 1
}

# ---- 找 Python ----
$py = Join-Path $ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) {
    $py = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $py) {
    Write-Host "  [错误] 找不到 Python" -ForegroundColor Red
    exit 1
}

# ============ 模式 1: 修复 cpolar ============
if ($FixCpolar) {
    $me = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($me)
    $isAdmin = $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    if (-not $isAdmin) {
        Write-Host ""
        Write-Host "  需要管理员权限" -ForegroundColor Red
        Write-Host "  请右键此文件 -> 使用 PowerShell 运行" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "按 Enter 退出"
        exit 1
    }

    Write-Host ""
    Write-Host "  修复 cpolar 服务冲突" -ForegroundColor Cyan
    Write-Host "  " + ("-" * 40) -ForegroundColor DarkGray

    $svc = Get-Service cpolar -ErrorAction SilentlyContinue
    if ($svc -and $svc.Status -eq "Running") {
        Stop-Service cpolar -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 3
        Write-Host "  服务已停止" -ForegroundColor Green
    }
    if ($svc) {
        Set-Service cpolar -StartupType Manual -ErrorAction SilentlyContinue
        Write-Host "  启动类型: Manual" -ForegroundColor Green
    }

    taskkill /F /IM cpolar.exe 2>&1 | Out-Null
    Start-Sleep -Seconds 2
    $left = Get-Process cpolar -ErrorAction SilentlyContinue
    if ($left) {
        Write-Host "  仍有 " + $left.Count + " 个进程" -ForegroundColor Red
    } else {
        Write-Host "  进程已清理" -ForegroundColor Green
    }

    Write-Host ""
    Read-Host "按 Enter 退出"
    exit 0
}

# ============ 模式 2: 配置局域网 ============
if ($SetupLan) {
    $me = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($me)
    $isAdmin = $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

    if (-not $isAdmin) {
        Write-Host ""
        Write-Host "  需要管理员权限" -ForegroundColor Red
        Write-Host "  请右键此文件 -> 使用 PowerShell 运行" -ForegroundColor Yellow
        Write-Host ""
        Read-Host "按 Enter 退出"
        exit 1
    }

    Write-Host ""
    Write-Host "  配置局域网防火墙" -ForegroundColor Cyan
    Write-Host "  " + ("-" * 40) -ForegroundColor DarkGray

    netsh advfirewall firewall delete rule name="AI Agent $Port" 2>&1 | Out-Null
    netsh advfirewall firewall add rule name="AI Agent $Port" dir=in action=allow protocol=TCP localport=$Port 2>&1 | Out-Null

    $ip = (Get-NetIPAddress -AddressFamily IPv4 |
        Where-Object { $_.IPAddress -like "192.168.*" -or $_.IPAddress -like "10.*" } |
        Select-Object -First 1).IPAddress

    Write-Host "  规则已添加: TCP $Port" -ForegroundColor Green
    if ($ip) {
        Write-Host "  局域网访问: http://" + $ip + ":" + $Port -ForegroundColor Cyan
    }
    Write-Host ""
    Read-Host "按 Enter 退出"
    exit 0
}

# ============ 模式 3: 启动服务 ============
Set-Location $codeDir

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:PYTHONUNBUFFERED = "1"
$env:NO_COLOR = "1"
$env:TERM = "dumb"

# 构建参数
$argsList = @("server.py", "--port", "$Port")
if ($NoTunnel) {
    $argsList += "--no-tunnel"
}
if ($NewTunnel) {
    $argsList += "--new-tunnel"
}

Write-Host ""
Write-Host "  AI Agent 启动中..." -ForegroundColor Cyan
if ($NoTunnel) {
    Write-Host "  模式: 本地（无隧道）" -ForegroundColor DarkGray
} else {
    Write-Host "  模式: 公网（含隧道）" -ForegroundColor DarkGray
}
Write-Host ""

& $py @argsList
