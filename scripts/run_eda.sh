#!/usr/bin/env bash
# Launch Jupyter for exploratory data analysis.
set -e
cd "$(dirname "$0")/.."

jupyter notebook ml/notebooks
