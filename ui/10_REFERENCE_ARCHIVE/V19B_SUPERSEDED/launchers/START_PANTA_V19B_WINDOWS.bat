@echo off
cd /d %~dp0\..
start "PANTA V19.B Server" python mock_api\server.py --port 4191
timeout /t 2 > nul
start http://127.0.0.1:4191/?mode=mock^&case=PROJECT-KEYSTONE^&actor=partner
