#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../frontend"
npm install
echo "Public: http://82.156.67.222:5173/"
echo "Note: Vite's Network URL may show the private interface address."
npm run dev -- --host 0.0.0.0
