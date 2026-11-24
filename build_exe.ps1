<#
.SYNOPSIS
    Bambu Smart Tuner 一键打包（PowerShell 版，等价于 build_exe.bat）

.EXAMPLE
    .\build_exe.ps1
    .\build_exe.ps1 -Clean          # 先删 build/dist 再打包（默认就删）
    .\build_exe.ps1 -SkipDeps       # 依赖已装好，跳过 pip
    .\build_exe.ps1 -Mirror tuna    # 用清华镜像装依赖
#>
[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$SkipDeps,
    [ValidateSet('default', 'tuna', 'aliyun')]
    [string]$Mirror = 'default'
)

$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
Set-Location $PSScriptRoot

function Step($n, $text) { Write-Host "[$n/5] $text" -ForegroundColor Cyan }

# 原生命令的 stderr 在 PowerShell 里会被当成错误记录（配合 $ErrorActionPreference='Stop'
# 会直接抛 NativeCommandError）。这里统一用 cmd 重定向到日志文件，既不误判也能留完整日志。
function Invoke-Native($file, [string[]]$cmdArgs, [string]$logName) {
    $log = Join-Path $PSScriptRoot $logName
    $quoted = @('"' + $file + '"') + @($cmdArgs | ForEach-Object {
        if ($_ -match '\s') { '"' + $_ + '"' } else { $_ }
    })
    $cmdline = ($quoted -join ' ') + ' > "' + $log + '" 2>&1'
    cmd /c $cmdline
    $code = $LASTEXITCODE
    if ($code -ne 0) {
        Write-Host "---- $logName 末尾 ----" -ForegroundColor Red
        Get-Content $log -Tail 30 | ForEach-Object { Write-Host $_ -ForegroundColor Red }
        throw "命令失败：$file $($cmdArgs -join ' ')（退出码 $code）"
    }
    return $log
}

Step 1 '检查 Python'
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { throw '没有找到 python，请安装 Python 3.9+ 并加入 PATH。' }
$pyver = & python -c "import sys;print(sys.version.split()[0])"
Write-Host "    Python $pyver"

Step 2 '检查/安装依赖'
if (-not $SkipDeps) {
    $mirrorArg = @()
    if ($Mirror -eq 'tuna') { $mirrorArg = @('-i', 'https://pypi.tuna.tsinghua.edu.cn/simple') }
    if ($Mirror -eq 'aliyun') { $mirrorArg = @('-i', 'https://mirrors.aliyun.com/pypi/simple') }
    Invoke-Native 'python' (@('-m', 'pip', 'install', '-r', 'requirements.txt') + $mirrorArg) 'build_pip.log' | Out-Null
    Write-Host '    依赖已就绪'
} else {
    Write-Host '    已跳过'
}
& python -c "import PySide6, PyInstaller; print('    PySide6', PySide6.__version__); print('    PyInstaller', PyInstaller.__version__)"

Step 3 '生成图标'
Invoke-Native 'python' @('tools\make_icon.py') 'build_icon.log' | Out-Null

Step 4 '清理旧构建'
foreach ($d in @('build', 'dist')) {
    if (Test-Path $d) { Remove-Item $d -Recurse -Force }
}
Write-Host '    已清理'

Step 5 '打包'
$log = Invoke-Native 'python' @('-m', 'PyInstaller', 'BambuSmartTuner.spec', '--noconfirm') 'build_pyinstaller.log'
Write-Host ("    日志：{0}" -f $log)

New-Item -ItemType Directory -Force -Path 'dist\rules' | Out-Null
Copy-Item 'rules\BambuRules.json' 'dist\rules\BambuRules.json' -Force
if (Test-Path 'README.md') { Copy-Item 'README.md' 'dist\README.md' -Force }
# Studio 定位表：EXE 优先读同目录 data\studio_ui.json，方便自己就地改
if (Test-Path 'data\studio_ui.json') {
    New-Item -ItemType Directory -Force -Path 'dist\data' | Out-Null
    Copy-Item 'data\studio_ui.json' 'dist\data\studio_ui.json' -Force
}
# 收款码：放到 dist\assets\donate.png，换图不用重打包（EXE 同目录优先）
if (Test-Path 'assets\donate.png') {
    New-Item -ItemType Directory -Force -Path 'dist\assets' | Out-Null
    Copy-Item 'assets\donate.png' 'dist\assets\donate.png' -Force
}

$exe = Get-Item 'dist\BambuSmartTuner.exe'
Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ("  打包完成：{0}" -f $exe.FullName) -ForegroundColor Green
Write-Host ("  体积：{0:N1} MB" -f ($exe.Length / 1MB)) -ForegroundColor Green
Write-Host '  规则库：dist\rules\BambuRules.json（直接编辑这份）' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
