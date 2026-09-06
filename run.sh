#!/bin/bash
set -eu

APP_DIR=${APP_DIR:-/usr/src/app}
exec python -u "$APP_DIR/runtime.py" "$@"
