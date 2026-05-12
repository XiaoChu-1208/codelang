@echo off
REM codelang 卸载：
REM   - 从用户 PATH 移除 bin/（不影响其他工具）
REM   - 删除桌面 codelang.lnk
REM 项目代码本身不动，想彻底清掉自己删项目目录。
REM
REM 想同时清掉 ~/.codelang/ 配置目录，加 --purge-config 参数：
REM     py tools\uninstall_shortcuts.py --purge-config

cd /d "%~dp0"
py tools\uninstall_shortcuts.py
echo.
pause
