#!/bin/bash
set -u

APP_DIR=/usr/src/app
STATE_DIR=${STATE_DIR:-$APP_DIR/metadata}
DOWNLOAD_DIR=${DOWNLOAD_DIR:-/downfolder}
PUID=${PUID:-0}
PGID=${PGID:-0}
UMASK=${UMASK:-022}
YTDLP_AUTO_UPDATE=${YTDLP_AUTO_UPDATE:-true}
NLPTUTTI_AUTO_UPDATE=${NLPTUTTI_AUTO_UPDATE:-true}
SCHEDULER_PID=""
SERVER_PID=""

case "$PUID" in
  *[!0-9]*|'')
    echo "PUID and PGID must be numeric" >&2
    exit 1
    ;;
esac
case "$PGID" in
  *[!0-9]*|'')
    echo "PUID and PGID must be numeric" >&2
    exit 1
    ;;
esac

mkdir -p "$DOWNLOAD_DIR/.incomplete" "$STATE_DIR"

if grep -q '{{' "$APP_DIR/Auth.json"; then
  subber "$APP_DIR/Auth.json"
fi

if [ "$(id -u)" = "0" ]; then
  chown "$PUID:$PGID" "$DOWNLOAD_DIR" "$DOWNLOAD_DIR/.incomplete" "$STATE_DIR"
  if [ -f "$STATE_DIR/download_history.json" ]; then
    chown "$PUID:$PGID" "$STATE_DIR/download_history.json"
  fi
  if [ -f "$STATE_DIR/app_state.json" ]; then
    chown "$PUID:$PGID" "$STATE_DIR/app_state.json"
  fi
fi

umask "$UMASK"

if [ "$NLPTUTTI_AUTO_UPDATE" = "true" ] || [ "$NLPTUTTI_AUTO_UPDATE" = "1" ]; then
  python -u "$APP_DIR/upd_schedule.py" --nlptutti-once || echo "Startup nlptutti install/update failed; Subtitle QA will be unavailable"
fi

if [ "$YTDLP_AUTO_UPDATE" = "true" ] || [ "$YTDLP_AUTO_UPDATE" = "1" ]; then
  python -u "$APP_DIR/upd_schedule.py" --once || echo "Startup yt-dlp update failed; continuing with the installed version"
  python -u "$APP_DIR/upd_schedule.py" >> /var/log/ytdlp-updater.log 2>&1 &
  SCHEDULER_PID=$!
fi

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
  fi
  if [ -n "$SCHEDULER_PID" ]; then
    kill "$SCHEDULER_PID" 2>/dev/null || true
  fi
}
trap cleanup INT TERM EXIT

if [ "$(id -u)" = "0" ] && { [ "$PUID" != "0" ] || [ "$PGID" != "0" ]; }; then
  HOME=/tmp gosu "$PUID:$PGID" python -u "$APP_DIR/youtube-dl-server.py" &
else
  python -u "$APP_DIR/youtube-dl-server.py" &
fi
SERVER_PID=$!
wait "$SERVER_PID"
SERVER_STATUS=$?
SERVER_PID=""
exit "$SERVER_STATUS"
