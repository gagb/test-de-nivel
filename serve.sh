#!/usr/bin/env bash
# Serve the placement test to a class over a free Cloudflare quick tunnel.
#
# Usage:
#   TEACHER_PASSWORD=yourpassword ./serve.sh
#
# It (1) regenerates the student page, (2) starts the Flask app on
# 127.0.0.1:5000, and (3) opens a public https://…trycloudflare.com URL that
# tunnels to it. Share that URL with students. The teacher console is at
# <that URL>/teacher.  Press Ctrl-C to stop everything.

set -euo pipefail
cd "$(dirname "$0")"

# cloudflared is installed per-user (no sudo needed); make sure it's found.
export PATH="$HOME/.local/bin:$PATH"

PORT="${PORT:-5000}"
: "${TEACHER_PASSWORD:=changeme}"
export TEACHER_PASSWORD PORT

if [ "$TEACHER_PASSWORD" = "changeme" ]; then
  echo "WARNING: using default teacher password 'changeme'."
  echo "         Restart with:  TEACHER_PASSWORD=yourpassword ./serve.sh"
  echo
fi

# --- checks ---------------------------------------------------------------
python3 -c "import flask" 2>/dev/null || {
  echo "Flask is not installed. Run:  pip3 install --user -r requirements.txt"
  exit 1
}
if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared is not installed. Install it once (no sudo), then re-run:"
  echo
  echo "  curl -sSL -o /tmp/cloudflared.tgz \\"
  echo "    https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz"
  echo "  mkdir -p ~/.local/bin && tar -xzf /tmp/cloudflared.tgz -C ~/.local/bin"
  echo "  chmod +x ~/.local/bin/cloudflared"
  echo
  echo "  See DEPLOY.md > 'Serve over a Cloudflare tunnel' for details."
  exit 1
fi

# Refuse to start if something else already holds the port. Otherwise the
# tunnel would silently point at that other process (e.g. a stale server with
# a different password) instead of the app we are about to start.
if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "ERROR: port ${PORT} is already in use by:"
  lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN
  echo "Stop that process (kill <PID>) or run with a different port: PORT=5001 ./serve.sh"
  exit 1
fi

# --- build the student page ----------------------------------------------
python3 build.py

# --- start the app, tunnel, and clean up on exit --------------------------
echo "Starting the test server on http://127.0.0.1:${PORT} ..."
python3 app.py &
APP_PID=$!
trap 'echo; echo "Stopping..."; kill "$APP_PID" 2>/dev/null || true' EXIT INT TERM

# Wait until OUR app is actually listening; abort if it died (e.g. bind error).
for _ in $(seq 1 20); do
  if ! kill -0 "$APP_PID" 2>/dev/null; then
    echo "ERROR: the app exited before it started listening. See the messages above."
    exit 1
  fi
  if curl -s -o /dev/null "http://127.0.0.1:${PORT}/"; then
    break
  fi
  sleep 0.5
done
if ! curl -s -o /dev/null "http://127.0.0.1:${PORT}/"; then
  echo "ERROR: the app did not start listening on port ${PORT}."
  exit 1
fi

echo
echo "Opening public tunnel. Share the https://…trycloudflare.com URL below."
echo "Teacher console: add /teacher to that URL (password = TEACHER_PASSWORD)."
echo
cloudflared tunnel --url "http://127.0.0.1:${PORT}"
