@echo off
setlocal
cd /d "%~dp0"
echo ============================================
echo  Kazi Sasa - Safe Source Deployment
echo ============================================
echo.
echo This deploys the new source code and workflow WITHOUT force-pushing
echo the bundled offline feed over the current live feed.
echo.
echo Press any key to continue, or close this window to cancel.
pause >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0deploy.ps1"
if errorlevel 1 goto :error
echo.
echo Deployment completed. The Actions page has been opened if the workflow
echo could not be triggered automatically.
pause
exit /b 0
:error
echo.
echo Deployment failed. Copy the complete output above for review.
pause
exit /b 1
