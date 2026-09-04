#!/usr/bin/env bash
# Install backend + ml dependencies into the currently active virtual environment.
# Run scripts/setup_venv.sh and activate the venv first.
set -e
cd "$(dirname "$0")/.."

pip install -r backend/requirements.txt -r ml/requirements.txt
