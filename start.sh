#!/usr/bin/env bash
# 帧防 FrameGuard · 后台启动（macOS / Linux）
# 用法：bash start.sh [--port 7891]
# Windows 请使用：start.bat

cd "$(dirname "$0")" || exit 1

# 优先使用项目内的虚拟环境，其次用系统 python
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -n "$FRAMEGUARD_PYTHON" ]; then
  PY="$FRAMEGUARD_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi

exec "$PY" serve.py start "$@"
