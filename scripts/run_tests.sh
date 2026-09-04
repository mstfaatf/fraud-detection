#!/usr/bin/env bash
# Run backend test suite.
set -e
cd "$(dirname "$0")/.."

pytest backend/tests
