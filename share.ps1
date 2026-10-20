# 一键发布：启动服务 + 自动开新隧道并显示地址
#
# 特点：
#   - 每次运行都会得到一个新的公网地址（cpolar 免费版特性）
#   - 自动从日志解析地址并高亮显示
#   - 自动复制到剪贴板

param(
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$root = "D:\A-Code"
$py = Join-Path $root ".venv\Scripts\python.exe"

# 找 cpolar
$cpolar = ""
foreach ($c in @(
    (Join-Path $root "tools\cpolar\cpolar.exe"),
    "D:\Download\APP\cpolar\cpolar.exe",
    (Join-Path $env:LOCALAPPDATA "cpolar\cpolar.exe")
)) {
    if (Test-Path $c) { $cpolar = $c; break }
}
if (-not $cpolar) {
    Write-Host "找不到 cpolar.exe" -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AI Agent - 公网发布" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---------- 1. 清理旧隧道 ----------
$old = Get-Process cpolar -ErrorAction SilentlyContinue
if ($old) {
    Write-Host "清理旧隧道 ($($old.Count) 个进程)..." -ForegroundColor DarkGray
    $old | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

# ---------- 2. 确保 Web 服务在跑 ----------
$listening = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listening) {
    Write-Host "[1/2] 启动 Web 服务..." -ForegroundColor Yellow
    Start-Process -FilePath $py -ArgumentList @("server.py", "--host", "0.0.0.0", "--port", $Port) -WorkingDirectory ((Get-ChildItem $root -Directory | Where-Object { Test-Path (Join-Path $_.FullName "server.py") } | Select-Object -First 1).FullName) -WindowStyle Hidden | Out-Null
    Start-Sleep -Seconds 6
} else {
    Write-Host "[1/2] Web 服务已在运行" -ForegroundColor Green
}

# ---------- 3. 开新隧道 ----------
Write-Host "[2/2] 申请新公网地址..." -ForegroundColor Yellow

$logFile = Join-Path $env:TEMP ("cpolar_" + [guid]::NewGuid().ToString("N").Substring(0,8))
$proc = Start-Process -FilePath $cpolar `
    -ArgumentList @("http", "$Port", "-log", $logFile, "-log-level", "info") `
    -PassThru -WindowStyle Hidden

# 轮询日志找地址
$url = $null
for ($i = 0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 800
    foreach ($f in (Get-ChildItem (Split-Path $logFile) -Filter ((Split-Path $logFile -Leaf) + "*") -ErrorAction SilentlyContinue)) {
        $content = Get-Content $f.FullName -Raw -Encoding UTF8 -ErrorAction SilentlyContinue
        if ($content) {
            $m = [regex]::Match($content, "Tunnel established at (https://[^\s" + [char]34 + "]+)")
            if ($m.Success) {
                $url = $m.Groups[1].Value
                break
            }
        }
    }
    if ($url) { break }
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
    Write-Host "提示：   cpolar 免费版地址与账号绑定，重启后不变" -ForegroundColor DarkGray
    Write-Host ""

    try { Set-Clipboard -Value $url; Write-Host "已复制到剪贴板 ✓" -ForegroundColor Green } catch {}
} else {
    Write-Host "地址获取超时，请手动查看：" -ForegroundColor Yellow
    Write-Host "  $logFile" -ForegroundColor DarkGray
}
Write-Host ""
Write-Host "隧道进程 PID: $($proc.Id)  （关掉服务时记得停止它）" -ForegroundColor DarkGray
Write-Host ""
