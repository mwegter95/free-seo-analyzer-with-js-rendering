#!/bin/bash
set -e

cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating Python virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate

# Install deps
echo "Installing Python dependencies..."
pip install -q -r requirements.txt

# Install Playwright browsers (chromium only)
if ! python -c "from playwright.sync_api import sync_playwright" 2>/dev/null || \
   [ ! -d "$HOME/Library/Caches/ms-playwright" ] && [ ! -d "$HOME/.cache/ms-playwright" ]; then
  echo "Installing Playwright Chromium browser..."
  playwright install chromium
fi

echo ""
echo "Starting SEO Analyzer on http://localhost:5015"
echo ""
python server.py
