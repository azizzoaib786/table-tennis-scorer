#!/bin/bash
# =============================================================================
# table-tennis-scorer - sunset / restore (run ON the EC2 machine)
#
#   bash sunset.sh sunset     take the app offline (shows a "closed" page)
#   bash sunset.sh restore    bring it back exactly as it was
#   bash sunset.sh status     show current state
#
# What "sunset" does (nothing is deleted):
#   1. Exports all tt_* DynamoDB tables to JSON (+ best-effort AWS backups)
#   2. Saves the original nginx config for tt.fccsports.live
#   3. Switches nginx to a static "closed" page (HTTP 503)
#   4. Stops and disables the table-tennis-scorer service
# The other apps on this machine (i-quit-scorer, portfolio) are not touched.
#
# Options (env vars):  SKIP_DATA_BACKUP=1   skip step 1
# NOTE: redeploy.sh restarts the service, but nginx keeps showing the closed
#       page until you run "restore".
# =============================================================================
set -euo pipefail

SERVICE="table-tennis-scorer"
CONF="/etc/nginx/conf.d/table-tennis-scorer.conf"
BACKUP_ROOT="/home/ec2-user/tt-sunset-backup"
CONF_BACKUP="$BACKUP_ROOT/table-tennis-scorer.conf.orig"
CLOSED_DIR="/var/www/tt-closed"
DOMAIN="tt.fccsports.live"
APP_PORT=8002
REGION="${AWS_REGION:-eu-west-1}"
TABLES=(tt_matches tt_events tt_users tt_tournaments tt_settings tt_roster tt_registrations tt_practice_bookings)
MARKER="# TT-SUNSET-ACTIVE"

is_sunset() { grep -q "$MARKER" "$CONF" 2>/dev/null; }

http_code() {
    curl -sk -m 10 -o /dev/null -w "%{http_code}" --resolve "$DOMAIN:443:127.0.0.1" "https://$DOMAIN/" || true
}

reload_nginx() {
    sudo nginx -t
    sudo systemctl reload nginx
}

backup_data() {
    if [ "${SKIP_DATA_BACKUP:-0}" = "1" ]; then
        echo "   (skipping data backup: SKIP_DATA_BACKUP=1)"
        return
    fi
    command -v aws >/dev/null || { echo "ERROR: aws CLI not found. Re-run with SKIP_DATA_BACKUP=1 to skip."; exit 1; }
    local ts dir
    ts=$(date -u +%Y%m%dT%H%M%SZ)
    dir="$BACKUP_ROOT/data-$ts"
    mkdir -p "$dir"
    for t in "${TABLES[@]}"; do
        echo "   exporting $t"
        aws dynamodb scan --table-name "$t" --region "$REGION" --output json > "$dir/$t.json"
        aws dynamodb create-backup --table-name "$t" --backup-name "tt-sunset-$ts" \
            --region "$REGION" >/dev/null 2>&1 || echo "   (note: AWS on-demand backup of $t not created - JSON export is saved)"
    done
    echo "   data saved to $dir"
}

write_closed_page() {
    sudo mkdir -p "$CLOSED_DIR"
    sudo tee "$CLOSED_DIR/closed.html" >/dev/null <<'HTML'
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Tournament concluded</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#eef4ff;color:#0f2a55;text-align:center}
  .c{padding:2rem}
  h1{font-size:2rem;margin:.2em 0}
  p{color:#475f86;font-size:1.1rem}
</style>
</head>
<body><div class="c">
  <div style="font-size:3rem">&#127955;</div>
  <h1>Tournament concluded</h1>
  <p>This scoring site is now closed. Thank you for playing and following along!</p>
</div></body>
</html>
HTML
}

do_sunset() {
    if is_sunset; then
        echo "Already in sunset mode (nginx shows the closed page)."
    else
        echo "1/4 Backing up data..."
        mkdir -p "$BACKUP_ROOT"
        backup_data

        echo "2/4 Saving original nginx config..."
        cp "$CONF" "$CONF_BACKUP"
        echo "   saved to $CONF_BACKUP"

        echo "3/4 Switching nginx to the closed page..."
        write_closed_page
        python3 - "$CONF" /tmp/tt-sunset.conf <<'PY'
import re, sys
src, dst = sys.argv[1], sys.argv[2]
text = open(src).read()
new_block = (
    "    # TT-SUNSET-ACTIVE\n"
    "    error_page 503 /closed.html;\n"
    "    location = /closed.html { root /var/www/tt-closed; internal; }\n"
    "    location / { add_header Cache-Control \"no-store\" always; return 503; }\n"
)
out, n = re.subn(r"    location / \{.*?\n    \}\n", new_block, text, count=1, flags=re.S)
if n != 1:
    sys.exit("could not find 'location / { ... }' in nginx config")
open(dst, "w").write(out)
PY
        sudo cp /tmp/tt-sunset.conf "$CONF"
        if ! sudo nginx -t; then
            echo "ERROR: nginx config test failed - restoring original config."
            sudo cp "$CONF_BACKUP" "$CONF"
            exit 1
        fi
        sudo systemctl reload nginx
    fi

    echo "4/4 Stopping the app service..."
    sudo systemctl disable --now "$SERVICE"

    echo "Sunset complete. $DOMAIN now returns HTTP $(http_code) (expected 503)."
    echo "Restore any time with: bash sunset.sh restore"
}

do_restore() {
    [ -f "$CONF_BACKUP" ] || { echo "ERROR: $CONF_BACKUP not found - cannot restore nginx config."; exit 1; }

    echo "1/3 Starting the app service..."
    sudo systemctl enable --now "$SERVICE"
    for i in $(seq 1 30); do
        if curl -s -m 2 -o /dev/null "http://127.0.0.1:$APP_PORT/"; then break; fi
        sleep 1
        [ "$i" = 30 ] && { echo "ERROR: app did not come up on port $APP_PORT. Check: sudo journalctl -u $SERVICE -n 50"; exit 1; }
    done
    echo "   app is answering on port $APP_PORT"

    echo "2/3 Restoring the original nginx config..."
    sudo cp "$CONF" /tmp/tt-sunset.conf.current
    sudo cp "$CONF_BACKUP" "$CONF"
    if ! sudo nginx -t; then
        echo "ERROR: restored config failed nginx test - putting the closed page back."
        sudo cp /tmp/tt-sunset.conf.current "$CONF"
        exit 1
    fi
    sudo systemctl reload nginx

    echo "3/3 Checking the site..."
    echo "Restore complete. $DOMAIN now returns HTTP $(http_code) (expected 200 or 30x)."
}

do_status() {
    echo "service : $(systemctl is-active "$SERVICE" 2>/dev/null || true) / $(systemctl is-enabled "$SERVICE" 2>/dev/null || true)"
    if is_sunset; then echo "nginx   : SUNSET (closed page)"; else echo "nginx   : LIVE (proxying to app)"; fi
    echo "https   : HTTP $(http_code)"
    echo "backups : $(ls -1d "$BACKUP_ROOT"/data-* 2>/dev/null | tail -1 || true)"
}

case "${1:-}" in
    sunset)  do_sunset ;;
    restore) do_restore ;;
    status)  do_status ;;
    *) echo "Usage: bash sunset.sh {sunset|restore|status}"; exit 1 ;;
esac
