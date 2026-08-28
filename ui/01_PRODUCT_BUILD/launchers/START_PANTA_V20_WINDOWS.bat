@echo off
cd /d %~dp0\..
start "PANTA V20 Server" python mock_api\server.py --host 127.0.0.1 --port 4191
timeout /t 2 >nul
start "" "http://localhost:4191/?mode=mock^&case=PROJECT-TETHYS^&actor=partner^&api=http://localhost:4191/api/v20#case=PROJECT-TETHYS^&view=deal-command"
