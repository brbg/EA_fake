@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo   AI 原生 Enterprise Architect（Web 版）
echo   直接运行：只需要 Python，不需要 Node.js、不需要 npm install
echo   （前端已预先构建好，由后端一并提供）
echo ============================================================
echo.

:: ---------- 找 Python（逐个试，能用才算） ----------
set "PYTHON_CMD="
python --version >nul 2>nul && set "PYTHON_CMD=python"
if not defined PYTHON_CMD (py -3 --version >nul 2>nul && set "PYTHON_CMD=py -3")
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYTHON_CMD if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set "PYTHON_CMD=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PYTHON_CMD if exist "D:\python\python.exe" set "PYTHON_CMD=D:\python\python.exe"
if not defined PYTHON_CMD (
    echo [错误] 未检测到可用的 Python 3.x。
    echo        请到 https://www.python.org/downloads/ 安装，
    echo        安装时务必勾选 "Add python.exe to PATH"。
    echo.
    pause
    exit /b 1
)
echo [OK] Python:
%PYTHON_CMD% --version

:: ---------- 首次运行装后端依赖 ----------
if not exist "backend\.deps_installed" (
    echo.
    echo [1/2] 首次运行：安装后端依赖（需要联网，使用国内镜像，约 1 分钟）...
    %PYTHON_CMD% -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    if errorlevel 1 (
        echo.
        echo [错误] 依赖安装失败。请检查网络后重新双击本文件。
        pause
        exit /b 1
    )
    echo installed > "backend\.deps_installed"
    echo [OK] 依赖安装完成。
) else (
    echo [1/2] 后端依赖已安装，跳过。
)

:: ---------- 启动（前端已预先构建，由后端一并提供） ----------
echo.
echo [2/2] 启动服务： http://localhost:8080
echo       浏览器会自动打开；关闭本窗口即停止服务。
echo.
:: 等 4 秒再开浏览器，避免服务没起来就白屏。EA_NO_BROWSER=1 可跳过（自动化用）
if not defined EA_NO_BROWSER start "" /b cmd /c "ping -n 5 127.0.0.1 >nul & explorer http://localhost:8080"

cd /d "%~dp0backend"
%PYTHON_CMD% app.py
echo.
echo 服务已停止。
pause
