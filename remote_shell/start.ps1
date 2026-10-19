param([switch]$PrepareOnly,[string]$DataRoot=(Join-Path $env:LOCALAPPDATA 'KiraLive2DRemote'))
$ErrorActionPreference='Stop'
$clientRoot=$PSScriptRoot
$runtimeRoot=Join-Path $DataRoot 'runtime-31210'
$runtimePython=Join-Path $runtimeRoot 'python.exe'
$componentStamp=Join-Path $runtimeRoot 'ready.txt'
if (-not (Test-Path -LiteralPath $componentStamp) -or (Get-Content -LiteralPath $componentStamp -Raw).Trim() -ne 'remote-2') {
    Write-Host '首次使用，正在准备独立运行组件，请稍候…'
    New-Item -ItemType Directory -Path $runtimeRoot -Force | Out-Null
    if (-not (Test-Path -LiteralPath $runtimePython)) {
        $pythonArchive=Join-Path $runtimeRoot 'python.zip'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' -OutFile $pythonArchive
        Expand-Archive -LiteralPath $pythonArchive -DestinationPath $runtimeRoot -Force
    }
    $pathFile=Join-Path $runtimeRoot 'python312._pth'
    Set-Content -LiteralPath $pathFile -Encoding ASCII -Value @('python312.zip','.','Lib\site-packages','import site')
    $pipRunner=Join-Path $runtimeRoot 'pip.pyz'
    if (-not (Test-Path -LiteralPath $pipRunner)) { Invoke-WebRequest -UseBasicParsing -Uri 'https://bootstrap.pypa.io/pip/pip.pyz' -OutFile $pipRunner }
    & $runtimePython -X utf8 $pipRunner install --disable-pip-version-check --only-binary=:all: --target (Join-Path $runtimeRoot 'Lib\site-packages') 'live2d-py==1.0.0' 'PySide6-Essentials==6.10.2' 'PyOpenGL==3.1.10' 'websocket-client==1.8.0'
    if ($LASTEXITCODE -ne 0) { throw '组件准备失败，请检查网络后重新运行。' }
    Set-Content -LiteralPath $componentStamp -Value 'remote-2'
}
if ($PrepareOnly) { Write-Output 'REMOTE_RUNTIME_READY'; return }
$env:KIRA_REMOTE_DATA_DIR=$DataRoot
$logRoot=Join-Path $clientRoot 'logs'
New-Item -ItemType Directory -Path $logRoot -Force | Out-Null
$outputLog=Join-Path $logRoot 'client.log'
$errorLog=Join-Path $logRoot 'client-error.log'
Write-Host '正在启动独立壳，下面实时显示运行日志。此窗口会保留。'
Write-Host ('日志目录：'+$logRoot)
$shellProcess=Start-Process -FilePath $runtimePython -WindowStyle Normal -ArgumentList @('-X','utf8','-u',('"'+(Join-Path $clientRoot 'shell\remote_runner.py')+'"')) -WorkingDirectory $clientRoot -RedirectStandardOutput $outputLog -RedirectStandardError $errorLog -PassThru
$logReaders=@()
try {
    foreach ($logPath in @($outputLog,$errorLog)) {
        $logStream=[System.IO.File]::Open($logPath,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::ReadWrite)
        $logReaders+=New-Object System.IO.StreamReader($logStream,[System.Text.Encoding]::UTF8)
    }
    while (-not $shellProcess.HasExited) {
        foreach ($logReader in $logReaders) {
            $logText=$logReader.ReadToEnd()
            if ($logText.Length) { [Console]::Write($logText) }
        }
        Start-Sleep -Milliseconds 150
    }
    $shellProcess.WaitForExit()
    foreach ($logReader in $logReaders) {
        $logText=$logReader.ReadToEnd()
        if ($logText.Length) { [Console]::Write($logText) }
    }
} finally {
    foreach ($logReader in $logReaders) { $logReader.Dispose() }
}
$shellExitCode=$shellProcess.ExitCode
if ($shellExitCode -ne 0) {
    Write-Host ('独立壳异常退出，退出码：'+$shellExitCode) -ForegroundColor Red
}
exit $shellExitCode
