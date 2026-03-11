@echo off
chcp 65001 >nul
echo ========================================
echo   Text2xyq Windows 打包工具
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+
    pause
    exit /b 1
)

echo [1/3] 安装依赖...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo [2/3] 打包中...
pyinstaller --onefile --windowed --name Text2xyq --collect-data customtkinter --clean main.py

echo.
if exist dist\Text2xyq.exe (
    echo [3/3] 打包完成！
    echo 输出文件: dist\Text2xyq.exe
) else (
    echo [错误] 打包失败，请检查上方错误信息
)

echo.
pause
