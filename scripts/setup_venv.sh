#!/usr/bin/env bash
# Create the single top-level virtual environment for both ml/ and backend/.
set -e
cd "$(dirname "$0")/.."

python -m venv .venv

echo "Virtual environment created at .venv"
echo "Activate it with:"
echo "  source .venv/Scripts/activate   # Windows (Git Bash)"
echo "  .venv\\Scripts\\activate          # Windows (PowerShell / cmd)"
echo "  source .venv/bin/activate       # macOS / Linux"
