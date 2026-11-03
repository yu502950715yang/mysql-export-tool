$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

# 优先用项目 .venv 构建：Anaconda 里 numpy/MKL 会被 QFluentWidgets 的可选导入带进来，
# 单文件 exe 会从 ~60MB 膨胀到 270MB+。可用 $env:MYSQL_EXPORT_PYTHON 覆盖。
$python = $env:MYSQL_EXPORT_PYTHON
if (-not $python) {
    $venvPython = Join-Path $root '.venv/Scripts/python.exe'
    $python = if (Test-Path $venvPython) { $venvPython } else { 'python' }
}
Write-Host "构建 Python: $python"

if (-not (Test-Path 'build/app.ico')) {
    & $python build/make_icon.py
}
foreach ($path in @('build/_work', 'dist')) {
    if (Test-Path $path) { Remove-Item -Recurse -Force $path }
}

& $python -m PyInstaller build/mysql-export-tool.spec --clean --noconfirm `
    --workpath build/_work --distpath dist

$exe = Join-Path $root 'dist/MysqlExportTool.exe'
if (-not (Test-Path $exe)) { throw "构建失败：未生成 $exe" }

$log = Join-Path $root 'dist/selftest.log'
if (Test-Path $log) { Remove-Item $log -Force }
$process = Start-Process -FilePath $exe -ArgumentList '--selftest' `
    -WorkingDirectory (Join-Path $root 'dist') -Wait -PassThru
$content = if (Test-Path $log) { Get-Content $log -Raw } else { '' }
if ($content) { Write-Host $content }
if ($process.ExitCode -ne 0 -or $content -notmatch 'SELFTEST OK') {
    throw "exe 自检失败：exit=$($process.ExitCode) log=$log"
}

$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)
$hash = (Get-FileHash $exe -Algorithm SHA256).Hash
Write-Host ("构建成功：{0}（{1} MB）" -f $exe, $sizeMb)
Write-Host ("SHA256: {0}" -f $hash)
if ($sizeMb -gt 80) {
    Write-Warning ("exe 体积 {0} MB 超过目标 80 MB，检查 spec excludes" -f $sizeMb)
}
