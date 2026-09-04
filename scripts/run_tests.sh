#!/usr/bin/env bash
# Run backend and ml test suites.
set -e
cd "$(dirname "$0")/.."

pytest backend/tests ml/tests
