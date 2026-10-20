# 修复 cpolar 服务冲突
# 用法：右键此文件 -> 使用 PowerShell 运行
# 或管理员 PowerShell 中： .\fix-cpolar-service.ps1

$ErrorActionPreference = "Continue"

# ---- 检查管理员权限 ----
$me = [Security.Principal.WindowsIdentity]::GetCurrent()
$pr = New-Object Security.Principal.WindowsPrincipal($me)
$isAdmin = $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    Write-Host ""
    Write-Host "  [错误] 需要管理员权限" -ForegroundColor Red
    Write-Host ""
    Write-Host "  请右键点击本文件，选择：使用 PowerShell 运行" -ForegroundColor Yellow
    Write-Host "  UAC 弹窗时点 是" -ForegroundColor Yellow
    Write-Host ""
    Read-Host "按 Enter 退出"
    exit 1
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  修复 cpolar 服务冲突" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# ---- 1. 检查服务 ----
Write-Host ""
Write-Host "[1/4] 检查 cpolar 服务..." -ForegroundColor Yellow
$svc = Get-Service cpolar -ErrorAction SilentlyContinue
if ($svc) {
    Write-Host "  找到服务，状态: $($svc.Status)" -ForegroundColor DarkGray
} else {
    Write-Host "  未安装 cpolar 服务，跳过" -ForegroundColor DarkGray
}

# ---- 2. 停止服务 ----
Write-Host ""
Write-Host "[2/4] 停止服务..." -ForegroundColor Yellow
if ($svc -and $svc.Status -eq "Running") {
    try {
        Stop-Service cpolar -Force -ErrorAction Stop
        Start-Sleep -Seconds 3
        $svc.Refresh()
        Write-Host "  已停止，当前状态: $($svc.Status)" -ForegroundColor Green
    } catch {
        Write-Host "  停止失败: $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "  无需停止" -ForegroundColor DarkGray
}

# ---- 3. 设为手动启动 ----
Write-Host ""
Write-Host "[3/4] 设置为手动启动..." -ForegroundColor Yellow
if ($svc) {
    try {
        Set-Service cpolar -StartupType Manual -ErrorAction Stop
        $newType = (Get-Service cpolar).StartType
        Write-Host "  启动类型: $newType" -ForegroundColor Green
    } catch {
        Write-Host "  设置失败: $($_.Exception.Message)" -ForegroundColor Red
    }
}

# ---- 4. 清理残留进程 ----
Write-Host ""
Write-Host "[4/4] 清理残留进程..." -ForegroundColor Yellow
taskkill /F /IM cpolar.exe 2>&1 | Out-Null
Start-Sleep -Seconds 2

$remain = Get-Process cpolar -ErrorAction SilentlyContinue
if ($remain) {
    Write-Host "  仍有 $($remain.Count) 个进程: $($remain.Id -join ', ')" -ForegroundColor Red
} else {
    Write-Host "  已全部清理" -ForegroundColor Green
}

# ---- 结果 ----
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  完成" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  现在启动服务：" -ForegroundColor White
Write-Host "    cd D:\A-Code\AI-Agent" -ForegroundColor Cyan
Write-Host "    ..\.venv\Scripts\python.exe server.py" -ForegroundColor Cyan
Write-Host ""
Read-Host "按 Enter 退出"
