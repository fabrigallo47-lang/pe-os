#!/bin/bash
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
PORT=${PANTA_PORT:-4191}
echo "Opening PANTA V20 Connected at http://localhost:$PORT/ui/index.html?mode=connected"
.venv/bin/uvicorn app.server:app --host 127.0.0.1 --port "$PORT" &
PID=$!
sleep 1
open "http://localhost:$PORT/ui/index.html?mode=connected#view=sources"
wait $PID
