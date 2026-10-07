# Obsidian RAG 服务守护脚本
# 每 1 分钟运行一次（由 Windows 计划任务调用）
# 检查端口 8777，挂了自动拉起服务，输出日志

$logDir = Join-Path $PSScriptRoot "logs"
if (!(Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$logFile = Join-Path $logDir "health_check.log"

$now = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

# 1) 检查端口 8777 是否有服务监听
$portListening = $false
try {
    $tcpClient = New-Object System.Net.Sockets.TcpClient
    $tcpClient.Connect("127.0.0.1", 8777)
    $tcpClient.Close()
    $portListening = $true
} catch {
    # 连接失败 = 服务没跑
    $portListening = $false
}

if ($portListening) {
    # 服务正常，只记一行日志
    Add-Content -Path $logFile -Value "[$now] 服务正常，端口 8777 监听中"
} else {
    # 服务挂了，拉起
    $logMsg = "[$now] 服务未运行，正在启动..."
    Add-Content -Path $logFile -Value $logMsg

    $scriptDir = $PSScriptRoot
    $pythonPath = Join-Path $scriptDir ".venv\Scripts\python.exe"
    $serverArgs = @("-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8777")

    # 先释放端口（防止残留进程）
    $connections = Get-NetTCPConnection -LocalPort 8777 -State Listen -ErrorAction SilentlyContinue
    if ($connections) {
        $connections | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    }

    # 启动服务（后台）
    Start-Process -FilePath $pythonPath -ArgumentList $serverArgs -WorkingDirectory $scriptDir -WindowStyle Hidden -PassThru | Out-Null

    # 等待 5 秒确认启动
    Start-Sleep -Seconds 5

    # 再检查一次
    $started = $false
    try {
        $tcpClient2 = New-Object System.Net.Sockets.TcpClient
        $tcpClient2.Connect("127.0.0.1", 8777)
        $tcpClient2.Close()
        $started = $true
    } catch { }

    if ($started) {
        Add-Content -Path $logFile -Value "[$now] ✓ 服务已成功重启"
    } else {
        Add-Content -Path $logFile -Value "[$now] ✗ 服务重启失败，请手动检查"
    }
}