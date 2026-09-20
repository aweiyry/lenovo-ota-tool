@echo off
chcp 65001 >nul
setlocal

echo ============================================
echo  Lenovo OTA Tool - 打包脚本
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3.10+
    pause & exit /b 1
)

python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo [1/3] 安装 PyInstaller ...
    python -m pip install pyinstaller || (echo 安装失败 & pause & exit /b 1)
) else (
    echo [1/3] PyInstaller 已安装
)

set PDG=tools\payload-dumper-go.exe
if not exist "%PDG%" (
    echo [2/4] 未找到内置引擎，尝试自动下载 payload-dumper-go ...
    if not exist tools mkdir tools
    powershell -NoProfile -Command ^
      "$ProgressPreference='SilentlyContinue';" ^
      "$u='https://github.com/ssut/payload-dumper-go/releases/download/2.0.2/payload-dumper-go_2.0.2_windows_amd64_avx2.tar.gz';" ^
      "try{ Invoke-WebRequest -Uri $u -OutFile 'tools\pdg.tar.gz' -TimeoutSec 120;" ^
      "  tar -xzf tools\pdg.tar.gz -C tools; " ^
      "  if(Test-Path tools\pdg.exe){ Move-Item tools\pdg.exe tools\payload-dumper-go.exe -Force };" ^
      "  Remove-Item tools\pdg.tar.gz -Force -ErrorAction SilentlyContinue }" ^
      "catch { Write-Host '自动下载失败，请手动下载（见 tools\README.md）' }"
)
if exist "%PDG%" (
    echo [2/4] 找到内置引擎: %PDG%
    set ADD_DATA=--add-data "%PDG%;."
) else (
    echo [警告] 未能获取 %PDG%
    echo        打包出的 EXE 将不带内置提取引擎，需把 payload-dumper-go.exe
    echo        放到 EXE 同目录才能提取分区。获取方式见 tools\README.md
    set ADD_DATA=
)

echo [3/4] 开始打包 ...
python -m PyInstaller --onefile --console --name LenovoOtaTool %ADD_DATA% --clean lenovo_ota_tool.py
if errorlevel 1 (
    echo [错误] 打包失败
    pause & exit /b 1
)

echo.
echo ============================================
echo  完成！产物: dist\LenovoOtaTool.exe
echo  用法:
echo    双击运行  =^> 图形界面
echo    dist\LenovoOtaTool.exe --help  =^> 命令行用法
echo ============================================
pause
