@echo off
cd /d %~dp0\..\..\..
start "PANTA V20 Server" .venv\Scripts\uvicorn.exe app.server:app --host 127.0.0.1 --port 4191
timeout /t 2 >nul
start "" "http://localhost:4191/ui/index.html?mode=connected#view=sources"
