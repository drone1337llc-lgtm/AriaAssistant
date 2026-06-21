@echo off
echo.
echo Syncing server files to AI PC (192.168.68.88)...
echo.
powershell -ExecutionPolicy Bypass -File "%~dp0sync_to_aipc.ps1"
echo.
pause
