#!/bin/zsh
# Gets the latest Qitaf. Your presets, word fixes, videos and lessons are kept.
cd "$(dirname "$0")" || exit 1
git pull
.venv/bin/pip install -r requirements.txt
npm install
.venv/bin/python -X utf8 check.py
