#!/bin/bash
cd "$(dirname "$0")/.."
PORT=${PANTA_PORT:-4191}
echo "Opening PANTA V20 Mock Connected at http://localhost:$PORT/?mode=mock&case=PROJECT-TETHYS&actor=partner"
python3 mock_api/server.py --host 127.0.0.1 --port "$PORT" &
PID=$!
sleep 1
open "http://localhost:$PORT/?mode=mock&case=PROJECT-TETHYS&actor=partner&api=http://localhost:$PORT/api/v20#case=PROJECT-TETHYS&view=deal-command"
wait $PID
