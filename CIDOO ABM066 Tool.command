#!/bin/bash
# ===================================================
# CIDOO ABM066 LCD Tool Launcher for macOS
# Double-click this file to launch the Web UI
# ===================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================="
echo " Starting CIDOO ABM066 LCD Tool..."
echo " Web UI will open in your browser automatically."
echo " (Keep this window open while using the tool;"
echo "  press Ctrl+C to stop the server)"
echo "=================================================="

# Start python backend server (auto-opens default browser)
python3 server.py
