# Champions Meta Lab 실행기
# - 백엔드(포트 8000)가 꺼져 있으면 숨김 창으로 켠다.
# - 켜져 있어도 백엔드 코드가 그 뒤에 바뀌었으면 다시 켠다 (새 기능이 바로 반영되도록).
# - 데스크톱 앱을 연다.
$root = Split-Path $PSScriptRoot -Parent
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
$exe = Join-Path $root 'app\build\windows\x64\runner\Release\champions_meta_lab.exe'
$logs = Join-Path $root 'backend\data'

function Test-Backend {
    try {
        Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/info' -TimeoutSec 2 | Out-Null
        return $true
    } catch {
        return $false
    }
}

$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    $process = Get-Process -Id $listener.OwningProcess -ErrorAction SilentlyContinue
    $command = (Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)").CommandLine
    $codeTime = (Get-ChildItem (Join-Path $root 'backend\app') -Filter *.py |
        Measure-Object -Property LastWriteTime -Maximum).Maximum
    # 가상환경 python.exe 는 시스템 파이썬을 띄우므로 경로 대신 실행 명령으로 이 앱의 백엔드인지 확인한다.
    $ours = $process -and $command -and ($command -like '*app.main:app*')
    if ($ours -and $process.StartTime -lt $codeTime) {
        Stop-Process -Id $process.Id -Force
        Start-Sleep -Milliseconds 800
    }
}

if (-not (Test-Backend)) {
    Start-Process -FilePath $python `
        -ArgumentList '-m', 'uvicorn', 'app.main:app', '--app-dir', 'backend', '--port', '8000' `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logs 'windows-launch.log') `
        -RedirectStandardError (Join-Path $logs 'windows-launch.err.log')
    $deadline = (Get-Date).AddSeconds(60)
    while (-not (Test-Backend) -and (Get-Date) -lt $deadline) {
        Start-Sleep -Milliseconds 500
    }
}

Start-Process -FilePath $exe -WorkingDirectory (Split-Path $exe)
