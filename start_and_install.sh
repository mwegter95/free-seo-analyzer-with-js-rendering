#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# SEO Analyzer — install deps + start local dev static server
#
# Analysis is handled by mw-backend. Make sure it's running first:
#   cd ../mw-backend && ./start.sh
# ─────────────────────────────────────────────────────────────────
set -e

cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate

# Install deps (minimal — just Flask for static serving)
echo "Installing Python dependencies..."
pip install -q -r requirements.txt

echo ""
echo "  → SEO Analyzer static server  →  http://localhost:5015"
echo "  → Analysis backend required   →  http://localhost:5050"
echo ""
python server.py
