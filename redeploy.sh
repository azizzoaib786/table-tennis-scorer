#!/bin/bash
# =============================================================================
# tabletennisscorer — Redeploy script (pull latest + restart)
# Usage: bash redeploy.sh
# Fast path for code updates — does NOT touch nginx, certbot, or systemd unit.
# Use deploy.sh for full first-time setup.
# =============================================================================
set -euo pipefail

APP_DIR="/home/ec2-user/tabletennisscorer"
SERVICE_NAME="tabletennisscorer"
REPO_URL="${REPO_URL:-git@github.com:azizzoaib786/tabletennisscorer.git}"

echo "▶ Pulling latest changes..."
current_url=$(git -C "$APP_DIR" remote get-url origin 2>/dev/null || echo "")
if [ "$current_url" != "$REPO_URL" ]; then
    echo "   ↻ Updating origin remote to $REPO_URL"
    git -C "$APP_DIR" remote set-url origin "$REPO_URL"
fi
git -C "$APP_DIR" fetch --all
git -C "$APP_DIR" reset --hard origin/HEAD

echo "▶ Installing any new dependencies..."
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

echo "▶ Restarting service..."
sudo systemctl restart "$SERVICE_NAME"
sudo systemctl status "$SERVICE_NAME" --no-pager --lines=5

echo "✅ Redeployed successfully."
