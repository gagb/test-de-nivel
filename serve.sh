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
  echo "cloudflared is not installed. Install it once, then re-run this script:"
  echo
  echo "  Intel Mac (this machine):"
  echo "    curl -L --output /usr/local/bin/cloudflared \\"
  echo "      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz"
  echo "    # (that URL serves a .tgz; see DEPLOY.md for the exact unpack step)"
  echo
  echo "  See DEPLOY.md > 'Serve over a Cloudflare tunnel' for details."
  exit 1
fi

# --- build the student page ----------------------------------------------
python3 build.py

# --- start the app, tunnel, and clean up on exit --------------------------
echo "Starting the test server on http://127.0.0.1:${PORT} ..."
python3 app.py &
APP_PID=$!
trap 'echo; echo "Stopping..."; kill "$APP_PID" 2>/dev/null || true' EXIT INT TERM

# give the server a moment to bind
sleep 2

echo
echo "Opening public tunnel. Share the https://…trycloudflare.com URL below."
echo "Teacher console: add /teacher to that URL (password = TEACHER_PASSWORD)."
echo
cloudflared tunnel --url "http://127.0.0.1:${PORT}"
