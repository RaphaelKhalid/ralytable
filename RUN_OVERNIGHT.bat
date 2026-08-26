@echo off
title Ralytable - overnight run
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo.
echo   Ralytable overnight run. Close this window or create the STOP file to end early.
echo.
python -u experiments\06_discrete_core\run.py
echo.
echo   Finished. Results are in experiments\06_discrete_core\results.jsonl
pause
