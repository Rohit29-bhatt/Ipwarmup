#!/bin/bash
set -e

echo ""
echo "=========================================================="
echo "  IP Warmup Automation Tool — Mac / Linux Setup"
echo "=========================================================="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found. Install from https://python.org"
    exit 1
fi
echo "[OK] Python found: $(python3 --version)"

# Virtual environment
if [ ! -d "venv" ]; then
    echo "[..] Creating virtual environment..."
    python3 -m venv venv
fi
echo "[OK] Virtual environment ready."

# Activate
source venv/bin/activate

# Install deps
echo "[..] Installing Python dependencies..."
pip install -q -r requirements.txt

# Playwright browsers
echo "[..] Installing Playwright Chromium browser..."
python -m playwright install chromium

echo ""
echo "=========================================================="
echo "  Setup complete! Starting server..."
echo "  Open your browser at: http://localhost:5000"
echo "=========================================================="
echo ""

python app.py
