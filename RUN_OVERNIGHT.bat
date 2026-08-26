@echo off
title Ralytable - overnight run
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
echo.
echo   Ralytable overnight run.
echo   Stop early and keep results: create experiments\06_discrete_core\STOP
echo.
python -u experiments\06_discrete_core\run.py
echo.
echo   Finished. Results: experiments\06_discrete_core\results.jsonl
pause
