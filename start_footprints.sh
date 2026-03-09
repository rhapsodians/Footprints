#!/bin/bash
# Institutional Footprints — startup script
cd "$(dirname "$0")"

# Activate the virtual environment
source venv/bin/activate

echo "======================================"
echo "  Institutional Footprints"
echo "======================================"
echo "  Open in browser: http://localhost:5000"
echo "  Press Ctrl+C to stop"
echo ""

# Start the application
venv/bin/python server.py

