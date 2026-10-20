# 局域网访问配置（需要管理员权限运行一次）
#
# 作用：在 Windows 防火墙放行 8000 端口，让同一 WiFi 下的设备能访问
# 用法：右键 -> 以管理员身份运行

$ErrorActionPreference = "Continue"

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host ""
    Write-Host "需要管理员权限" -ForegroundColor Red
    Write-Host "请右键本文件 -> 以管理员身份运行" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "按 Enter 退出" | Out-Null
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  配置局域网访问" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$name = "AI Agent Demo 8000"
$existing = Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue

if ($existing) {
    Write-Host "规则已存在，更新中..." -ForegroundColor Yellow
    Remove-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue
}

# 只对「专用网络」放行（家里 WiFi 属于专用网络，咖啡馆等公共网络不放行）
New-NetFirewallRule `
    -DisplayName $name `
    -Direction Inbound `
    -LocalPort 8000 `
    -Protocol TCP `
    -Action Allow `
    -Profile Private,Domain `
    -Description "允许局域网访问 AI Agent 演示服务" | Out-Null

Write-Host "  已放行 8000 端口（仅专用网络）" -ForegroundColor Green
Write-Host ""

# 显示当前内网地址
$ip = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -notlike "172.17.*" } |
    Select-Object -First 1).IPAddress

if ($ip) {
    Write-Host "其他人（同一 WiFi）访问地址：" -ForegroundColor Cyan
    Write-Host "  http://$ip`:8000" -ForegroundColor Green
}
Write-Host ""
Write-Host "注意：必须是同一个 WiFi / 局域网" -ForegroundColor DarkGray
Write-Host "      要让外网访问，用 expose.ps1" -ForegroundColor DarkGray
Write-Host ""
Read-Host "按 Enter 退出" | Out-Null