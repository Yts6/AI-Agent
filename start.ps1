# AI Agent Demo 一键启动
#
# 用法：
#   双击本文件，或在终端执行 .\start.ps1
#   关闭窗口即停止服务

$ErrorActionPreference = "Stop"
$root = "D:\A-Code"
$py = Join-Path $root ".venv\Scripts\python.exe"
$oneDir = (Get-ChildItem $root -Directory | Where-Object { Test-Path (Join-Path $_.FullName "server.py") } | Select-Object -First 1).FullName
$port = 8000

function Pause-Exit($msg) {
    Write-Host ""
    Write-Host $msg -ForegroundColor Red
    Write-Host ""
    # 双击运行时窗口会一闪而过，停一下让人看到错误
    try { Read-Host "按 Enter 退出" | Out-Null } catch { }
    exit 1
}

# ---------- 环境检查 ----------
if (-not (Test-Path $py)) {
    Pause-Exit "找不到虚拟环境：$py`n请先确认 .venv 目录存在"
}
if (-not (Test-Path (Join-Path $oneDir "server.py"))) {
    Pause-Exit "找不到 server.py：$oneDir"
}

$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Agent Demo" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 清理旧进程 ----------
# 不清理的话会报 [Errno 10048] 端口被占用
$listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($listeners) {
    Write-Host "端口 $port 已被占用，正在停止旧进程..." -ForegroundColor DarkGray
    $listeners | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Seconds 3
}

# ---------- 启动服务（前台，方便看日志） ----------
Write-Host "启动服务中..." -ForegroundColor Yellow
Write-Host ""

$ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
    Select-Object -First 1).IPAddress

Write-Host "──────────────────────────────────────" -ForegroundColor Green
Write-Host "  本机访问   http://127.0.0.1:$port" -ForegroundColor Green
if ($ip) {
    Write-Host "  局域网     http://$ip`:$port" -ForegroundColor Green
}
Write-Host "──────────────────────────────────────" -ForegroundColor Green
Write-Host ""
Write-Host "  浏览器打开上面地址即可使用" -ForegroundColor DarkGray
Write-Host "  想让外网访问，用另一个窗口运行 expose.ps1" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  关闭本窗口 = 停止服务" -ForegroundColor DarkGray
Write-Host "  下面是服务日志：" -ForegroundColor DarkGray
Write-Host ""

Set-Location $oneDir
& $py server.py --host 0.0.0.0 --port $port

# 服务退出（Ctrl+C 或崩溃）后停住，让人看到最后的日志
Write-Host ""
Write-Host "服务已停止。" -ForegroundColor Yellow
try { Read-Host "按 Enter 关闭" | Out-Null } catch { }