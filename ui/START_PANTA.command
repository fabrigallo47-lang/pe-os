#!/bin/bash
set -e
cd "$(dirname "$0")"
python3 integration/mock_server.py --open
