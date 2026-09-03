#!/usr/bin/env bash
set -euo pipefail
npm ci
npm run check:all
echo "Ready. Start the synthetic product lab with: npm run lab"
