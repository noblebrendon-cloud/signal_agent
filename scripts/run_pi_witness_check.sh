#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="${SIGNAL_AGENT_REPO_ROOT:-$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)}"
PYTHON_BIN="${SIGNAL_AGENT_PYTHON:-$REPO_ROOT/.venv/bin/python}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="${SIGNAL_AGENT_PYTHON:-python3}"
fi

cd "$REPO_ROOT"
export PYTHONDONTWRITEBYTECODE=1

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RECEIPT_DIR="$REPO_ROOT/data/state/pi_witness_receipts"
RECEIPT_PATH="$RECEIPT_DIR/$TIMESTAMP.json"

BRANCH="$(git branch --show-current 2>/dev/null || true)"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || true)"
DIRTY_COUNT="$(git status --short 2>/dev/null | wc -l | tr -d ' ')"

echo "pi_witness_repo_root=$REPO_ROOT"
echo "pi_witness_branch=$BRANCH"
echo "pi_witness_commit=$COMMIT"
echo "pi_witness_dirty_count=$DIRTY_COUNT"
echo "pi_witness_python=$PYTHON_BIN"

TEST_COMMAND="$PYTHON_BIN -B -m pytest -p no:cacheprovider tests/test_daily_witness_check.py -q"
if [[ -f "$REPO_ROOT/tests/test_daily_witness_check.py" ]]; then
  set +e
  "$PYTHON_BIN" -B -m pytest -p no:cacheprovider tests/test_daily_witness_check.py -q
  EXIT_CODE=$?
  set -e
  CHECK_KIND="focused_daily_witness_test"
else
  set +e
  "$PYTHON_BIN" --version
  python_exit=$?
  git status --short
  git_exit=$?
  set -e
  if [[ "$python_exit" -eq 0 && "$git_exit" -eq 0 ]]; then
    EXIT_CODE=0
  else
    EXIT_CODE=1
  fi
  CHECK_KIND="fallback_environment_check"
  TEST_COMMAND="$PYTHON_BIN --version && git status --short"
fi

mkdir -p "$RECEIPT_DIR"
cat > "$RECEIPT_PATH" <<EOF
{
  "timestamp_utc": "$TIMESTAMP",
  "repo_root": "$REPO_ROOT",
  "branch": "$BRANCH",
  "commit": "$COMMIT",
  "dirty_count": $DIRTY_COUNT,
  "check_kind": "$CHECK_KIND",
  "command": "$TEST_COMMAND",
  "exit_code": $EXIT_CODE,
  "authority": {
    "network_actions": [],
    "git_writes": [],
    "production_mutations": [],
    "receipt_root": "data/state/pi_witness_receipts"
  }
}
EOF

echo "pi_witness_exit_code=$EXIT_CODE"
echo "pi_witness_receipt=$RECEIPT_PATH"
exit "$EXIT_CODE"
