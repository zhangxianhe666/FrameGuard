#!/usr/bin/env bash
# 帧防 FrameGuard · macOS 打包：dist/FrameGuard.app → .dmg
#
# 用法：bash packaging/macos/build_dmg.sh <版本号> <App路径> <输出目录> [架构标签]
set -euo pipefail

VERSION="${1:?需要版本号}"
APP_PATH="${2:?需要 .app 路径}"
OUT_DIR="${3:?需要输出目录}"
ARCH_LABEL="${4:-$(uname -m)}"

if [ ! -d "$APP_PATH" ]; then
  echo "❌ 找不到 $APP_PATH" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

STAGE="$(mktemp -d)/dmg"
mkdir -p "$STAGE"
cp -R "$APP_PATH" "$STAGE/FrameGuard.app"
ln -s /Applications "$STAGE/Applications"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SCRIPT_DIR/README-FIRST.txt" "$STAGE/Read me first.txt"

# PyInstaller 在 Apple Silicon 上已做 ad-hoc 签名；这里再整体补签一次，
# 失败不影响出包（未签名时用户首次打开需右键 → 打开）。
codesign --force --deep --sign - "$STAGE/FrameGuard.app" 2>/dev/null \
  && echo "✅ 已完成 ad-hoc 签名" \
  || echo "⚠️  ad-hoc 签名失败，未签名应用首次打开需右键 → 打开"

DMG_NAME="FrameGuard-${VERSION}-macos-${ARCH_LABEL}.dmg"
rm -f "$OUT_DIR/$DMG_NAME"

hdiutil create \
  -volname "FrameGuard ${VERSION}" \
  -srcfolder "$STAGE" \
  -ov -format UDZO \
  "$OUT_DIR/$DMG_NAME" >/dev/null

rm -rf "$(dirname "$STAGE")"
echo "✅ $OUT_DIR/$DMG_NAME"
