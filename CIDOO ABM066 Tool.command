#!/bin/bash
# ===================================================
# CIDOO ABM066 LCD Tool Launcher for macOS
# Double-click this file to launch the Web UI
# ===================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

echo "=================================================="
echo " Starting CIDOO ABM066 LCD Tool..."
echo " Opening browser at http://127.0.0.1:5000"
echo " (Press Ctrl+C in this window to stop the server)"
echo "=================================================="

# Wait 1 second and open default browser
(sleep 1 && open "http://127.0.0.1:5000") &

# Start python backend server
python3 server.py
