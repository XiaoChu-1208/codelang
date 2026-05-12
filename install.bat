@echo off
REM codelang 一键安装：
REM   - 把 bin/ 加进用户 PATH（命令行能用 codelang / dongwang）
REM   - 桌面生成带图标的快捷方式
REM 跑完装好就行，闭幕不需要管理员权限。

cd /d "%~dp0"
py tools\install_shortcuts.py
echo.
pause
