#!/bin/bash
set -e

cd "$(dirname "$0")"
source venv/bin/activate

echo ""
echo "Starting SEO Analyzer on http://localhost:5015"
echo ""
python server.py
