#!/bin/bash
# ─────────────────────────────────────────────────────────────────
# SEO Analyzer — Local dev static server (port 5015)
#
# This serves only the frontend. Analysis is handled by mw-backend.
# Make sure mw-backend is running first:
#   cd ../mw-backend && ./start.sh
# ─────────────────────────────────────────────────────────────────
set -e

cd "$(dirname "$0")"

if [ -d "venv/bin" ]; then
  source venv/bin/activate
fi

echo ""
echo "  → SEO Analyzer static server  →  http://localhost:5015"
echo "  → Analysis backend required   →  http://localhost:5050"
echo ""
python server.py
