#!/usr/bin/env bash
# 由 1024×1024 PNG 生成 macOS .icns（iconutil 仅 macOS 提供）
#
# 用法：bash packaging/macos/make_icns.sh packaging/assets/frameguard.png packaging/assets/frameguard.icns
set -euo pipefail

SRC="$1"
OUT="$2"

WORK="$(mktemp -d)"
ICONSET="$WORK/frameguard.iconset"
mkdir -p "$ICONSET"

# iconutil 只接受下列固定文件名，尺寸必须是 16/32/128/256/512 及其 @2x
for s in 16 32 128 256 512; do
  sips -z "$s" "$s" "$SRC" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  sips -z "$((s * 2))" "$((s * 2))" "$SRC" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done

iconutil -c icns "$ICONSET" -o "$OUT"
rm -rf "$WORK"
echo "✅ $OUT"
