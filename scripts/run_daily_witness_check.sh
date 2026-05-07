#!/usr/bin/env sh
set -u

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_ROOT=${SIGNAL_AGENT_REPO_ROOT:-$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)}
PYTHON_BIN=${SIGNAL_AGENT_PYTHON:-"$REPO_ROOT/.venv/bin/python"}

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN=${SIGNAL_AGENT_PYTHON:-python3}
fi

export PYTHONDONTWRITEBYTECODE=1

echo "daily_witness_repo_root=$REPO_ROOT"
echo "daily_witness_python=$PYTHON_BIN"
"$PYTHON_BIN" -B -m signal_agent.health.daily_check --repo-root "$REPO_ROOT"
status=$?
echo "daily_witness_exit_code=$status"
echo "daily_witness_reports=data/state/witness/reports/"
exit "$status"

