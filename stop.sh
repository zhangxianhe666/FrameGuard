#!/usr/bin/env bash
# 帧防 FrameGuard · 停止后台服务（macOS / Linux）
# 用法：bash stop.sh [--port 7891]
# Windows 请使用：stop.bat

cd "$(dirname "$0")" || exit 1

if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -n "$FRAMEGUARD_PYTHON" ]; then
  PY="$FRAMEGUARD_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi

exec "$PY" serve.py stop "$@"
