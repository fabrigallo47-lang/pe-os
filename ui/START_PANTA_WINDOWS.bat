@echo off
cd /d %~dp0
python integration\mock_server.py --open
pause
