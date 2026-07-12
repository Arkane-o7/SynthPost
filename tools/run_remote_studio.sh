#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

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

if command -v uv >/dev/null 2>&1; then
  PYTHON_CMD=(uv run --python 3.11 --with-requirements requirements.txt python)
else
  PYTHON_CMD=("${PYTHON_BIN:-python3}")
fi

tailscaled_pid=""
TAILSCALE_CMD=("$TAILSCALE_BIN")
STATE_DIR="${HOME}/.synthpost"
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
worker_pid=""
cleanup() {
  "${TAILSCALE_CMD[@]}" serve --https=443 off >/dev/null 2>&1 || true
  [[ -n "$worker_pid" ]] && kill "$worker_pid" >/dev/null 2>&1 || true
  [[ -n "$api_pid" ]] && kill "$api_pid" >/dev/null 2>&1 || true
  [[ -n "$tailscaled_pid" ]] && kill "$tailscaled_pid" >/dev/null 2>&1 || true
  wait "$worker_pid" "$api_pid" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

"${PYTHON_CMD[@]}" -m uvicorn pipeline.api.main:app --host 127.0.0.1 --port 8765 &
api_pid=$!
"${PYTHON_CMD[@]}" -m pipeline.jobs.worker &
worker_pid=$!

for _ in {1..40}; do
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

wait "$api_pid" "$worker_pid"
