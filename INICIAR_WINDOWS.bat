@echo off
setlocal
cd /d "%~dp0"
docker compose up -d --remove-orphans
if errorlevel 1 pause
