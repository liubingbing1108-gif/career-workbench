#!/bin/zsh
cd "$(dirname "$0")"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python scripts/start_workbench.py || exit $?
else
  python3 scripts/start_workbench.py || exit $?
fi
open http://127.0.0.1:8768/
