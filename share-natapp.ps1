# natapp 一键发布（地址每次启动都不同）
#
# 前提：natapp.exe 已放在 D:\A-Code\tools\natapp\ 目录
# 用法：.\share-natapp.ps1

param(
    [string]$Token = "",   # 留空则从环境变量 NATAPP_TOKEN 读取，或运行时输入
    [int]$Port = 8000
)

$ErrorActionPreference = "Continue"
$root = "D:\A-Code"
$py = Join-Path $root ".venv\Scripts\python.exe"
$natapp = Join-Path $root "tools\natapp\natapp.exe"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Agent - natapp 公网发布" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 1. 检查 natapp ----------
if (-not (Test-Path $natapp)) {
    Write-Host "找不到 natapp.exe" -ForegroundColor Red
    Write-Host ""
    Write-Host "请先下载：" -ForegroundColor Yellow
    Write-Host "  1. 浏览器打开  https://natapp.cn/download" -ForegroundColor White
    Write-Host "  2. 点「Windows 64位」下载 zip" -ForegroundColor White
    Write-Host "  3. 解压，把 natapp.exe 放到：" -ForegroundColor White
    Write-Host "     $root\tools\natapp\" -ForegroundColor Green
    Write-Host ""
    Read-Host "按 Enter 退出" | Out-Null
    exit 1
}

# ---------- 2. 停止旧 natapp ----------
$old = Get-Process natapp -ErrorAction SilentlyContinue
if ($old) {
    Write-Host "停止旧隧道..." -ForegroundColor DarkGray
    $old | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
}

# ---------- 3. 确保 Web 服务在跑 ----------
$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Write-Host "[1/2] 启动 Web 服务..." -ForegroundColor Yellow
    Start-Process -FilePath $py -ArgumentList @("server.py", "--host", "0.0.0.0", "--port", $Port) -WorkingDirectory ((Get-ChildItem $root -Directory | Where-Object { Test-Path (Join-Path $_.FullName "server.py") } | Select-Object -First 1).FullName) -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 6
} else {
    Write-Host "[1/2] Web 服务已在运行" -ForegroundColor Green
}

# ---------- 4. 开 natapp 隧道 ----------
Write-Host "[2/2] 建立 natapp 隧道..." -ForegroundColor Yellow
Write-Host ""

$log = Join-Path $env:TEMP "natapp_out.txt"
$proc = Start-Process -FilePath $natapp `
    -ArgumentList @("-authtoken=$Token") `
    -RedirectStandardOutput $log `
    -RedirectStandardError ($log + ".err") `
    -PassThru -WindowStyle Hidden

# ---------- 5. 解析地址 ----------
$url = $null
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 700
    if (Test-Path $log) {
        $c = Get-Content $log -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($c) {
            $m = [regex]::Match($c, "Forwarding\s+(https?://[^\s" + [char]34 + "]+)")
            if ($m.Success) { $url = $m.Groups[1].Value; break }
            $m2 = [regex]::Match($c, "(https?://[a-z0-9]+\.natappfree\.cc)")
            if ($m2.Success) { $url = $m2.Groups[1].Value; break }
        }
    }
}

Write-Host ""
if ($url) {
    Write-Host "════════════════════════════════════════" -ForegroundColor Green
    Write-Host ""
    Write-Host "  公网地址（本次有效）" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  $url" -ForegroundColor Green
    Write-Host ""
    Write-Host "════════════════════════════════════════" -ForegroundColor Green
    Write-Host ""
    Write-Host "本机：   http://127.0.0.1:$Port" -ForegroundColor DarkGray
    Write-Host "特点：   每次重启 natapp 都会分配新地址" -ForegroundColor DarkGray
    Write-Host ""
    try { Set-Clipboard -Value $url; Write-Host "已复制到剪贴板" -ForegroundColor Green } catch {}
} else {
    Write-Host "未解析到地址，原始输出：" -ForegroundColor Yellow
    Write-Host ""
    if (Test-Path $log) { Get-Content $log -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -First 20 }
    if (Test-Path ($log + ".err")) { Get-Content ($log + ".err") -Encoding UTF8 -ErrorAction SilentlyContinue | Select-Object -First 10 }
}

Write-Host ""
Write-Host "隧道 PID: $($proc.Id)" -ForegroundColor DarkGray
Write-Host "注意：natapp 免费版地址约 30 天有效，到期需重新购买隧道" -ForegroundColor DarkGray
Write-Host ""
