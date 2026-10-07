#!/bin/bash
# 守护包装脚本：cron script 字段只认"脚本路径 + bash 前缀"，
# 不能直接写 powershell.exe 命令行（会被当成路径 → Script not found）。
# 本脚本负责调用 health_check.ps1 并透传退出码。
cd "$(cd "$(dirname "$0")" && pwd)"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$(cd "$(dirname "$0")" && pwd)"/health_check.ps1"
exit $?