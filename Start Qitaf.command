#!/bin/zsh
# Double-click to start Qitaf. Keep this window open while you use it; close it to stop Qitaf.
cd "$(dirname "$0")" || exit 1
echo "Qitaf is running at http://localhost:8795"
echo "Keep this window open while you use it. Close it to stop."
(sleep 3; open http://localhost:8795) &
.venv/bin/python -X utf8 server.py >> qitaf.log 2>&1
echo "Qitaf stopped. If you did not close it, ask Claude to read qitaf.log."
