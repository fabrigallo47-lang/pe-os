#!/bin/bash
set -e
cd "$(dirname "$0")/.."
PORT=4191
python3 mock_api/server.py --port "$PORT" &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT
sleep 1
open "http://127.0.0.1:$PORT/?mode=mock&case=PROJECT-KEYSTONE&actor=partner"
wait "$PID"
