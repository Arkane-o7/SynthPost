#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STATE_DIR="${HOME}/.synthpost"
INSTANCE_LOCK_DIR="${STATE_DIR}/remote-studio.lock"
mkdir -p "$STATE_DIR"
if ! mkdir "$INSTANCE_LOCK_DIR" 2>/dev/null; then
  existing_pid="$(cat "$INSTANCE_LOCK_DIR/pid" 2>/dev/null || true)"
  if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
    echo "SynthPost Remote Studio is already running (PID $existing_pid)." >&2
    echo "Stop that instance before starting another one." >&2
    exit 1
  fi
  rm -rf "$INSTANCE_LOCK_DIR"
  mkdir "$INSTANCE_LOCK_DIR"
fi
echo "$$" >"$INSTANCE_LOCK_DIR/pid"

if command -v tailscale >/dev/null 2>&1; then
  TAILSCALE_BIN="$(command -v tailscale)"
elif [[ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ]]; then
  TAILSCALE_BIN=/Applications/Tailscale.app/Contents/MacOS/Tailscale
else
  echo "Tailscale is not installed. Install it on this Mac and your phone, then sign both into the same tailnet." >&2
  echo "https://tailscale.com/download" >&2
  exit 1
fi

if command -v tailscaled >/dev/null 2>&1; then
  TAILSCALED_BIN="$(command -v tailscaled)"
elif [[ -x /opt/homebrew/opt/tailscale/bin/tailscaled ]]; then
  TAILSCALED_BIN=/opt/homebrew/opt/tailscale/bin/tailscaled
else
  TAILSCALED_BIN=""
fi

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  # Prefer the project interpreter so the PID recorded below belongs to the
  # actual API/supervisor process rather than to an `uv run` wrapper.
  PYTHON_CMD=("$ROOT_DIR/.venv/bin/python")
elif command -v uv >/dev/null 2>&1; then
  PYTHON_CMD=(uv run --python 3.11 --with-requirements requirements.txt python)
else
  PYTHON_CMD=("${PYTHON_BIN:-python3}")
fi

tailscaled_pid=""
TAILSCALE_CMD=("$TAILSCALE_BIN")
SOCKET_PATH="${STATE_DIR}/tailscaled.sock"
CUSTOM_STATUS=""
if [[ -S "$SOCKET_PATH" ]]; then
  CUSTOM_STATUS="$("$TAILSCALE_BIN" "--socket=$SOCKET_PATH" status 2>&1 || true)"
fi

if [[ -S /var/run/tailscaled.socket ]]; then
  TAILSCALE_CMD=("$TAILSCALE_BIN")
elif [[ -S "$SOCKET_PATH" && "$CUSTOM_STATUS" != *"failed to connect"* ]]; then
  TAILSCALE_CMD=("$TAILSCALE_BIN" "--socket=$SOCKET_PATH")
elif ! "$TAILSCALE_BIN" status >/dev/null 2>&1; then
  if [[ -z "$TAILSCALED_BIN" ]]; then
    echo "The Tailscale daemon is not running and tailscaled could not be found." >&2
    exit 1
  fi
  mkdir -p "$STATE_DIR"
  rm -f "$SOCKET_PATH"
  "$TAILSCALED_BIN" \
    --tun=userspace-networking \
    --statedir="$STATE_DIR" \
    --state="${STATE_DIR}/tailscale.state" \
    --socket="$SOCKET_PATH" \
    >"${STATE_DIR}/tailscaled.log" 2>&1 &
  tailscaled_pid=$!
  TAILSCALE_CMD=("$TAILSCALE_BIN" "--socket=$SOCKET_PATH")
  for _ in {1..40}; do
    [[ -S "$SOCKET_PATH" ]] && break
    sleep 0.25
  done
fi

if ! "${TAILSCALE_CMD[@]}" status >/dev/null 2>&1; then
  echo "Authenticate this SynthPost laptop with Tailscale to continue:"
  "${TAILSCALE_CMD[@]}" up
fi
npm --prefix web run build

api_pid=""
worker_supervisor_pid=""

collect_descendants() {
  local parent_pid="$1"
  local child_pid
  while IFS= read -r child_pid; do
    [[ -n "$child_pid" ]] || continue
    PROCESS_TREE_PIDS+=("$child_pid")
    collect_descendants "$child_pid"
  done < <(pgrep -P "$parent_pid" 2>/dev/null || true)
}

terminate_process_tree() {
  local root_pid="$1"
  local pid
  local attempt
  [[ -n "$root_pid" ]] || return 0

  # `uv run` remains alive as a wrapper around Python. Record the complete
  # tree before signalling anything so its children cannot be orphaned when
  # the wrapper exits first.
  PROCESS_TREE_PIDS=("$root_pid")
  collect_descendants "$root_pid"
  for pid in "${PROCESS_TREE_PIDS[@]}"; do
    kill -TERM "$pid" >/dev/null 2>&1 || true
  done
  for attempt in {1..50}; do
    local any_running=0
    for pid in "${PROCESS_TREE_PIDS[@]}"; do
      if kill -0 "$pid" >/dev/null 2>&1; then
        any_running=1
        break
      fi
    done
    [[ "$any_running" -eq 0 ]] && return 0
    sleep 0.1
  done
  for pid in "${PROCESS_TREE_PIDS[@]}"; do
    kill -KILL "$pid" >/dev/null 2>&1 || true
  done
}

reap_orphan_workers() {
  local pid
  local parent_pid
  local command
  local attempt
  local -a orphan_pids=()

  # A terminal or automation host can be killed before Bash gets a chance to
  # run the EXIT trap. In that case the supervisor disappears but its
  # start_new_session workers are re-parented to launchd (PID 1) and continue
  # holding every configured slot. They cannot be supervised or shut down by
  # the new pool, so reclaim them before starting its replacement.
  while read -r pid parent_pid command; do
    if [[ "$parent_pid" == "1" && "$command" == *"-m pipeline.jobs.worker"* ]]; then
      orphan_pids+=("$pid")
    fi
  done < <(ps -axo pid=,ppid=,command=)

  [[ "${#orphan_pids[@]}" -gt 0 ]] || return 0
  echo "[workers] reclaiming ${#orphan_pids[@]} orphaned worker process(es)" >&2
  for pid in "${orphan_pids[@]}"; do
    kill -TERM "$pid" >/dev/null 2>&1 || true
  done
  for attempt in {1..50}; do
    local any_running=0
    for pid in "${orphan_pids[@]}"; do
      if kill -0 "$pid" >/dev/null 2>&1; then
        any_running=1
        break
      fi
    done
    [[ "$any_running" -eq 0 ]] && return 0
    sleep 0.1
  done
  for pid in "${orphan_pids[@]}"; do
    kill -KILL "$pid" >/dev/null 2>&1 || true
  done
}

cleanup() {
  "${TAILSCALE_CMD[@]}" serve --https=443 off >/dev/null 2>&1 || true
  terminate_process_tree "$worker_supervisor_pid"
  terminate_process_tree "$api_pid"
  [[ -n "$tailscaled_pid" ]] && kill "$tailscaled_pid" >/dev/null 2>&1 || true
  for pid in "$worker_supervisor_pid" "$api_pid"; do
    [[ -n "$pid" ]] && wait "$pid" >/dev/null 2>&1 || true
  done
  rm -rf "$INSTANCE_LOCK_DIR"
}
trap cleanup EXIT INT TERM

reap_orphan_workers

"${PYTHON_CMD[@]}" -m uvicorn pipeline.api.main:app --host 127.0.0.1 --port 8765 &
api_pid=$!
"${PYTHON_CMD[@]}" -m pipeline.jobs.supervisor &
worker_supervisor_pid=$!

# Charter migrations and event-cluster rebuilding can take longer than a cold
# FastAPI import on a mature inbox. Keep the launcher alive for up to a minute
# instead of killing a healthy API at the old ten-second boundary.
for _ in {1..240}; do
  if curl -fsS http://127.0.0.1:8765/api/health >/dev/null 2>&1; then
    break
  fi
  sleep 0.25
done
curl -fsS http://127.0.0.1:8765/api/health >/dev/null

"${TAILSCALE_CMD[@]}" serve --bg 8765
echo
echo "SynthPost Remote Studio is live inside your private tailnet:"
"${TAILSCALE_CMD[@]}" serve status
echo
echo "Open the HTTPS URL above on your phone. Press Ctrl+C to stop the Studio and remove remote access."

while kill -0 "$api_pid" >/dev/null 2>&1; do
  if ! kill -0 "$worker_supervisor_pid" >/dev/null 2>&1; then
    wait "$worker_supervisor_pid" >/dev/null 2>&1 || true
    echo "SynthPost worker supervisor stopped unexpectedly; stopping Remote Studio." >&2
    exit 1
  fi
  sleep 2
done
wait "$api_pid" >/dev/null 2>&1 || true
