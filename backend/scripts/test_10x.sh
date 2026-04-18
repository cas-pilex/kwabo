#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
for i in $(seq 1 10); do
  echo "=== run $i/10 ==="
  PYTHONPATH=src python -m pytest tests/test_regression.py --regression -x --tb=short
done
echo "All 10 runs green."
