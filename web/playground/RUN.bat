@echo off
REM Double-click this file to open the Raly playground.
cd /d "%~dp0"
echo Starting the Raly playground at http://localhost:8000
echo Close this window when you are done.
start "" http://localhost:8000
python -m http.server 8000
