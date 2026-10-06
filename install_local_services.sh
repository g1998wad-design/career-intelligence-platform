#!/bin/zsh
# Install/reload the Mac's two-hour pipeline, private review page, and selected
# job preparation worker as per-user LaunchAgents.
set -euo pipefail

BASE_DIR=/Users/gurkiratsingh/JS_BASICS
AGENT_DIR="$HOME/Library/LaunchAgents"
mkdir -p "$AGENT_DIR"
chmod +x "$BASE_DIR/run_pipeline.sh" "$BASE_DIR/run_local_service.sh"

# Add private review credentials without printing them to the terminal/log.
python3 - "$BASE_DIR/.env" <<'PY'
import os
import re
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text() if path.exists() else ""
for key, value in (
    ("REVIEW_USERNAME", "jobs"),
    ("REVIEW_PASSWORD", secrets.token_urlsafe(36)),
):
    if not re.search(rf"(?m)^{re.escape(key)}=", text):
        text += ("" if not text or text.endswith("\n") else "\n") + f"{key}={value}\n"
path.write_text(text)
os.chmod(path, 0o600)
PY

cat > "$AGENT_DIR/com.jsbasics.jobpipeline.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.jsbasics.jobpipeline</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$BASE_DIR/run_pipeline.sh</string></array>
  <key>StartInterval</key><integer>7200</integer>
  <key>StandardOutPath</key><string>$BASE_DIR/pipeline_launchd.log</string>
  <key>StandardErrorPath</key><string>$BASE_DIR/pipeline_launchd.log</string>
</dict>
</plist>
PLIST

for service in review selected-worker application-worker; do
  case "$service" in
    review) label=com.jsbasics.jobreview ;;
    selected-worker) label=com.jsbasics.selectedworker ;;
    application-worker) label=com.jsbasics.applicationworker ;;
  esac
  cat > "$AGENT_DIR/$label.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$label</string>
  <key>ProgramArguments</key><array><string>/bin/zsh</string><string>$BASE_DIR/run_local_service.sh</string><string>$service</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>WorkingDirectory</key><string>$BASE_DIR</string>
  <key>StandardOutPath</key><string>$BASE_DIR/${service}.log</string>
  <key>StandardErrorPath</key><string>$BASE_DIR/${service}.log</string>
</dict>
</plist>
PLIST
done

cat > "$AGENT_DIR/com.jsbasics.keepawake.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.jsbasics.keepawake</string>
  <key>ProgramArguments</key><array><string>/usr/bin/caffeinate</string><string>-s</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
PLIST

uid=$(id -u)
for label in com.jsbasics.jobpipeline com.jsbasics.jobreview com.jsbasics.selectedworker com.jsbasics.applicationworker com.jsbasics.keepawake; do
  launchctl bootout "gui/$uid/$label" >/dev/null 2>&1 || true
  launchctl bootstrap "gui/$uid" "$AGENT_DIR/$label.plist"
done

echo "Installed the two-hour pipeline, private review page, selection worker, and application worker."
echo "The review page is listening on this Mac at http://127.0.0.1:8765."
echo "Review credentials are stored in the ignored, permission-restricted .env file."
echo "Use Tailscale Serve to reach the page from your phone outside this Mac's network."
