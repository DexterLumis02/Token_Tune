#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
if [[ -x "./.venv/bin/python" ]]; then
  exec "./.venv/bin/python" -u "rfid_simple.py"
fi
exec "./venv_gui/bin/python" -u "rfid_simple.py"
