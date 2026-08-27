#!/bin/bash
set -euo pipefail

EXT_ID="${1:-}"
if [ -z "$EXT_ID" ]; then
  echo "Usage: ./install.sh <EXTENSION_ID>"
  echo "  chrome://extensions 에서 'Bot Notification Cleaner' 로드 후 표시되는 ID를 넣으세요."
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
HOST_PATH="$HERE/host/notif-host.py"

command -v gh >/dev/null || echo "⚠️  gh 미설치 — 'brew install gh' 필요"

chmod +x "$HOST_PATH"

DEST="$HOME/Library/Application Support/Google/Chrome/NativeMessagingHosts"
mkdir -p "$DEST"
cat > "$DEST/com.forky.notifcleaner.json" <<JSON
{
  "name": "com.forky.notifcleaner",
  "description": "Bot Notification Cleaner native host",
  "path": "$HOST_PATH",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://$EXT_ID/"]
}
JSON

echo "✓ native messaging host 설치 → $DEST/com.forky.notifcleaner.json"
echo "✓ host: $HOST_PATH"
echo
echo "=== 남은 단계 ==="
echo "1. 토큰 확인: gh api /notifications --jq 'length'"
echo "   403 이면: gh auth refresh -h github.com -s notifications"
echo "2. chrome://extensions 에서 확장 reload"
