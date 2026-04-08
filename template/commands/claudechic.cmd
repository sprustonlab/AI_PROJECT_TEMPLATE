@echo off
REM Launch claudechic via pixi
cd /d "%PROJECT_ROOT%" 2>nul || cd /d "%~dp0\.."
pixi run claudechic %*
