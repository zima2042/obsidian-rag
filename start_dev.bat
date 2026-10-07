@echo off
chcp 65001 >nul
title Obsidian RAG 服务（后台）
:: 开发模式启动 Obsidian 知识库服务（浏览器访问 http://127.0.0.1:8777）
cd /d "%~dp0"

:: 释放端口
taskkill /F /IM obsidian_rag.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8777.*LISTENING"') do taskkill /F /PID %%a >nul 2>&1

:: 启动服务（隐藏窗口，后台运行）
start "" /b ".venv\Scripts\python.exe" -m uvicorn server:app --host 0.0.0.0 --port 8777

:: 等待就绪后打开浏览器
timeout /t 4 /nobreak >nul
start "" "http://127.0.0.1:8777"
exit