@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   AI 原生 Enterprise Architect - 一键启动
echo ============================================================
echo.

:: ---------- 解析 Python ----------
set "PYTHON_CMD=python"
where python >nul 2>nul
if %errorlevel% neq 0 (
    if exist "D:\python\python.exe" (
        set "PYTHON_CMD=D:\python\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
        set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    ) else if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
        set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    ) else (
        echo [错误] 未检测到 Python。请先安装 Python 3.x：
        echo         https://www.python.org/downloads/
        echo.
        pause
        exit /b 1
    )
)

where node >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 未检测到 Node.js。请先安装 Node.js：
    echo         https://nodejs.org/
    echo.
    pause
    exit /b 1
)

echo [OK] Python: %PYTHON_CMD%
%PYTHON_CMD% --version
echo [OK] Node:
node --version
echo.

:: ---------- 安装后端依赖（仅首次） ----------
if not exist "backend\.deps_installed" (
    echo [1/3] 首次运行：安装后端 Python 依赖，请稍候...
    cd /d "%~dp0backend"
    %PYTHON_CMD% -m pip install -r ..\requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if %errorlevel% neq 0 (
        echo.
        echo [错误] 后端依赖安装失败，请检查网络后重试。
        cd /d "%~dp0"
        pause
        exit /b 1
    )
    cd /d "%~dp0"
    echo installed > "backend\.deps_installed"
    echo [OK] 后端依赖安装完成。
) else (
    echo [1/3] 后端依赖已安装，跳过。
)
echo.

:: ---------- 安装前端依赖（仅首次） ----------
if not exist "node_modules" (
    echo [2/3] 首次运行：安装前端依赖，请稍候...
    call npm install
    if %errorlevel% neq 0 (
        echo [错误] 前端依赖安装失败，请检查网络后重试。
        pause
        exit /b 1
    )
    echo [OK] 前端依赖安装完成。
) else (
    echo [2/3] 前端依赖已安装，跳过。
)
echo.

:: ---------- 启动服务 ----------
echo [3/3] 正在启动服务...
echo.
echo   后端服务 : http://localhost:8080
echo   前端页面 : http://localhost:5173
echo.
echo   提示：服务会分别在两个新窗口中运行。
echo   请勿关闭这两个黑色命令行窗口，关闭即停止服务。
echo   本窗口稍后会自动关闭。
echo.

start "EA-Backend (8080)" /D "%~dp0backend" cmd /k "%PYTHON_CMD% app.py"
start "EA-Frontend (5173)" /D "%~dp0" cmd /k "npm run dev"

timeout /t 4 /nobreak >nul
start "" http://localhost:5173

exit /b 0
