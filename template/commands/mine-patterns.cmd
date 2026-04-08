@echo off
REM Run the pattern miner via Python
cd /d "%PROJECT_ROOT%" 2>nul || cd /d "%~dp0\.."
python scripts\mine_patterns.py %*
