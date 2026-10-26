<#
.SYNOPSIS
    经销商收车检测模块 端到端部署脚本
    覆盖：数据库变更 → 后端编译发布 → 前端构建发布 → 健康验证

.DESCRIPTION
    执行顺序：
      1. 数据库 DDL/DML 变更（deploy.sql + 检测项插入.sql + T25-菜单配置.sql）
      2. MSBuild 编译 project-v-ucm 后端
      3. 回收 IIS 应用池 ProjectVUCMApi
      4. 构建 nbms-usedcar-h5（H5 前端）
      5. 构建 project-v-admin（PC 管理端前端）
      6. 健康检查：后端接口 + H5 首页可访问

.PARAMETER Env
    部署目标环境：dev（默认）/ test / prod

.EXAMPLE
    .\deploy.ps1 -Env dev
    .\deploy.ps1 -Env test
#>

param(
    [ValidateSet("dev","test","prod")]
    [string]$Env = "dev"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ─────────────────────────────────────────────
# 0. 配置区（按实际环境修改）
# ─────────────────────────────────────────────
$Config = @{
    dev = @{
        SqlServer      = "localhost"
        SqlDb          = "PvUCM"
        SqlUser        = "sa"
        SqlPass        = "ChangeMe123!"   # 或改用 -E (Windows Auth)
        UseWinAuth     = $true            # $true = Windows 集成身份验证，忽略 SqlUser/SqlPass

        BackendSln     = "D:\Projects\ProjectV\project-v-ucm\ProjectVUCM.Dealer.WebApi.csproj"
        MsBuild        = "D:\IDE\Visual Studio 2022\MSBuild\Current\Bin\MSBuild.exe"
        AppPool        = "ProjectVUCMApi"
        BackendUrl     = "http://localhost:9003"

        H5Dir          = "D:\Projects\ProjectV\nbms-usedcar-h5"
        H5Dist         = "D:\Projects\ProjectV\nbms-usedcar-h5\dist"
        H5WebRoot      = "C:\inetpub\wwwroot\nbms-usedcar-h5"

        AdminDir       = "D:\Projects\ProjectV\project-v-admin"
        AdminDist      = "D:\Projects\ProjectV\project-v-admin\dist"
        AdminWebRoot   = "C:\inetpub\wwwroot\project-v-admin"
    }
    test = @{
        SqlServer      = "test-db.project-v.internal"
        SqlDb          = "PvUCM"
        SqlUser        = ""
        SqlPass        = ""
        UseWinAuth     = $true
        BackendSln     = "D:\Projects\ProjectV\project-v-ucm\ProjectVUCM.Dealer.WebApi.csproj"
        MsBuild        = "D:\IDE\Visual Studio 2022\MSBuild\Current\Bin\MSBuild.exe"
        AppPool        = "ProjectVUCMApi"
        BackendUrl     = "http://test-api.project-v.internal:9003"
        H5Dir          = "D:\Projects\ProjectV\nbms-usedcar-h5"
        H5Dist         = "D:\Projects\ProjectV\nbms-usedcar-h5\dist"
        H5WebRoot      = "\\test-web\wwwroot\nbms-usedcar-h5"
        AdminDir       = "D:\Projects\ProjectV\project-v-admin"
        AdminDist      = "D:\Projects\ProjectV\project-v-admin\dist"
        AdminWebRoot   = "\\test-web\wwwroot\project-v-admin"
    }
}

$cfg = $Config[$Env]
$ScriptDir = $PSScriptRoot
$LogFile   = "$ScriptDir\deploy-$(Get-Date -Format 'yyyyMMdd-HHmmss').log"

# ─────────────────────────────────────────────
# 工具函数
# ─────────────────────────────────────────────
function Log {
    param([string]$Msg, [string]$Level = "INFO")
    $ts  = Get-Date -Format "HH:mm:ss"
    $line = "[$ts][$Level] $Msg"
    Write-Host $line -ForegroundColor $(if ($Level -eq "ERROR") {"Red"} elseif ($Level -eq "WARN") {"Yellow"} else {"Cyan"})
    Add-Content -Path $LogFile -Value $line
}

function Step {
    param([string]$Title)
    $border = "=" * 60
    Log ""
    Log $border
    Log "  $Title"
    Log $border
}

function Exec {
    param([string]$Cmd)
    Log "RUN: $Cmd"
    $result = Invoke-Expression $Cmd 2>&1
    if ($LASTEXITCODE -ne 0) {
        Log "命令失败（exit $LASTEXITCODE）：$result" "ERROR"
        throw "执行失败，部署中止"
    }
    return $result
}

function SqlExec {
    param([string]$SqlFile, [string]$Description)
    Log "执行 SQL：$Description  →  $SqlFile"
    if (-not (Test-Path $SqlFile)) {
        Log "SQL 文件不存在：$SqlFile" "ERROR"
        throw "SQL 文件缺失"
    }
    if ($cfg.UseWinAuth) {
        $auth = "-E"
    } else {
        $auth = "-U `"$($cfg.SqlUser)`" -P `"$($cfg.SqlPass)`""
    }
    $cmd = "sqlcmd -S `"$($cfg.SqlServer)`" -d `"$($cfg.SqlDb)`" $auth -i `"$SqlFile`" -b"
    Exec $cmd
    Log "✓ $Description 执行成功"
}

function WaitForUrl {
    param([string]$Url, [int]$TimeoutSec = 60)
    Log "等待服务就绪：$Url（超时 ${TimeoutSec}s）"
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        try {
            $resp = Invoke-WebRequest -Uri $Url -TimeoutSec 3 -UseBasicParsing -ErrorAction SilentlyContinue
            if ($resp.StatusCode -lt 500) {
                Log "✓ 服务就绪（HTTP $($resp.StatusCode)）"
                return
            }
        } catch { }
        Start-Sleep -Seconds 3
    }
    throw "服务在 ${TimeoutSec}s 内未就绪：$Url"
}

# ─────────────────────────────────────────────
# 部署开始
# ─────────────────────────────────────────────
Log "=================================================="
Log "  经销商收车检测模块 部署脚本"
Log "  环境: $Env    时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Log "  日志: $LogFile"
Log "=================================================="

# ─────────────────────────────────────────────
# Step 1：数据库变更
# ─────────────────────────────────────────────
Step "Step 1/5  数据库变更"

# 1-a: 主表结构变更（ALTER + 旧表字段补齐）
SqlExec "$ScriptDir\deploy.sql" "VOV_DealerVehicleInspectTask 表结构维护"

# 1-b: 检测项字典数据（幂等，重复执行安全）
SqlExec "$ScriptDir\..\04-Plan\检测项插入.sql" "检测项字典数据初始化"

# 1-c: PC 端菜单配置
SqlExec "$ScriptDir\T25-菜单配置.sql" "PC端菜单配置"

Log "✓ 数据库变更全部完成"

# ─────────────────────────────────────────────
# Step 2：后端编译
# ─────────────────────────────────────────────
Step "Step 2/5  后端编译（project-v-ucm）"

if (-not (Test-Path $cfg.MsBuild)) {
    Log "MSBuild 未找到：$($cfg.MsBuild)" "ERROR"
    throw "MSBuild 不存在"
}
if (-not (Test-Path $cfg.BackendSln)) {
    Log "项目文件未找到：$($cfg.BackendSln)" "ERROR"
    throw "csproj 不存在"
}

# ⚠️ 只编译 Dealer.WebApi 单个 csproj，避免 NewBIeRocketMQService 证书签名问题
$msbuildArgs = "`"$($cfg.BackendSln)`" /t:Build /p:Configuration=Debug /p:Platform=AnyCPU /v:minimal /nologo"
Exec "`"$($cfg.MsBuild)`" $msbuildArgs"
Log "✓ 后端编译成功"

# ─────────────────────────────────────────────
# Step 3：回收 IIS 应用池 & 验证后端
# ─────────────────────────────────────────────
Step "Step 3/5  回收 IIS 应用池"

Exec "& '$env:windir\system32\inetsrv\appcmd.exe' recycle apppool /apppool.name:`"$($cfg.AppPool)`""
Log "✓ 应用池已回收"

Start-Sleep -Seconds 5
WaitForUrl "$($cfg.BackendUrl)/api/health" 60

# ─────────────────────────────────────────────
# Step 4：H5 前端构建 & 发布
# ─────────────────────────────────────────────
Step "Step 4/5  H5 前端构建（nbms-usedcar-h5）"

if (-not (Test-Path $cfg.H5Dir)) {
    Log "H5 目录不存在，跳过 H5 构建：$($cfg.H5Dir)" "WARN"
} else {
    Push-Location $cfg.H5Dir
    try {
        Exec "npm install --prefer-offline"
        Exec "npm run build"
        Log "✓ H5 构建完成"

        if (Test-Path $cfg.H5WebRoot) {
            Log "清空旧 H5 WebRoot：$($cfg.H5WebRoot)"
            Remove-Item "$($cfg.H5WebRoot)\*" -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            New-Item -ItemType Directory -Path $cfg.H5WebRoot -Force | Out-Null
        }
        Copy-Item "$($cfg.H5Dist)\*" $cfg.H5WebRoot -Recurse -Force
        Log "✓ H5 dist 已部署到 WebRoot"
    } finally {
        Pop-Location
    }
}

# ─────────────────────────────────────────────
# Step 5：PC 管理端构建 & 发布
# ─────────────────────────────────────────────
Step "Step 5/5  PC 管理端构建（project-v-admin）"

if (-not (Test-Path $cfg.AdminDir)) {
    Log "Admin 目录不存在，跳过 Admin 构建：$($cfg.AdminDir)" "WARN"
} else {
    Push-Location $cfg.AdminDir
    try {
        Exec "npm install --prefer-offline"
        Exec "npm run build"
        Log "✓ Admin 构建完成"

        if (Test-Path $cfg.AdminWebRoot) {
            Log "清空旧 Admin WebRoot：$($cfg.AdminWebRoot)"
            Remove-Item "$($cfg.AdminWebRoot)\*" -Recurse -Force -ErrorAction SilentlyContinue
        } else {
            New-Item -ItemType Directory -Path $cfg.AdminWebRoot -Force | Out-Null
        }
        Copy-Item "$($cfg.AdminDist)\*" $cfg.AdminWebRoot -Recurse -Force
        Log "✓ Admin dist 已部署到 WebRoot"
    } finally {
        Pop-Location
    }
}

# ─────────────────────────────────────────────
# 健康验证汇总
# ─────────────────────────────────────────────
Step "健康验证"

$checks = @(
    @{ Name="后端 /api/health";         Url="$($cfg.BackendUrl)/api/health" }
    @{ Name="H5 检测任务列表接口";      Url="$($cfg.BackendUrl)/api/VehicleInspect/GetInspectTaskList?Page=%7B%22Index%22%3A1%2C%22Size%22%3A1%7D" }
    @{ Name="H5 检测报告接口（匿名）";  Url="$($cfg.BackendUrl)/api/InspectReport/GetReportData?token=healthcheck-probe" }
)

$allPassed = $true
foreach ($chk in $checks) {
    try {
        $r = Invoke-WebRequest -Uri $chk.Url -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        $status = $r.StatusCode
    } catch {
        $status = $_.Exception.Response.StatusCode.value__ ?? "ERR"
    }
    # 200/400/401/404 均视为接口存在（服务正常），500+ 才是问题
    if ([int]$status -lt 500) {
        Log "✓ $($chk.Name)  →  HTTP $status"
    } else {
        Log "✗ $($chk.Name)  →  HTTP $status" "ERROR"
        $allPassed = $false
    }
}

if ($allPassed) {
    Log ""
    Log "🎉 部署完成！所有健康检查通过。" "INFO"
    Log "   后端地址：$($cfg.BackendUrl)"
    Log "   日志文件：$LogFile"
} else {
    Log "部署结束，但部分健康检查未通过，请检查日志：$LogFile" "WARN"
    exit 1
}
