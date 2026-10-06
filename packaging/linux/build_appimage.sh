#!/usr/bin/env bash
# 帧防 FrameGuard · Linux 打包：dist/FrameGuard → .AppImage + .tar.gz
#
# 用法：bash packaging/linux/build_appimage.sh <版本号> <dist目录> <输出目录>
set -euo pipefail

VERSION="${1:?需要版本号}"
DIST_DIR="${2:?需要 dist 目录}"
OUT_DIR="${3:?需要输出目录}"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARCH="$(uname -m)"                       # x86_64 / aarch64
APPDIR="$DIST_DIR/FrameGuard.AppDir"

if [ ! -d "$DIST_DIR/FrameGuard" ]; then
  echo "❌ 找不到 $DIST_DIR/FrameGuard" >&2
  exit 1
fi

mkdir -p "$OUT_DIR"

# ---------------------------------------------------------------- AppDir 布局
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin" "$APPDIR/usr/share/icons/hicolor/512x512/apps"
cp -R "$DIST_DIR/FrameGuard" "$APPDIR/usr/bin/FrameGuard"

cp "$ROOT/packaging/linux/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp "$ROOT/packaging/linux/frameguard.desktop" "$APPDIR/frameguard.desktop"
cp "$ROOT/packaging/assets/frameguard_512.png" "$APPDIR/frameguard.png"
cp "$ROOT/packaging/assets/frameguard_512.png" \
   "$APPDIR/usr/share/icons/hicolor/512x512/apps/frameguard.png"

# ---------------------------------------------------------------- appimagetool
TOOL_DIR="$(mktemp -d)"
TOOL_URL="https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-${ARCH}.AppImage"
echo "下载 appimagetool（${ARCH}）……"
curl -fsSL --retry 3 -o "$TOOL_DIR/appimagetool" "$TOOL_URL"
chmod +x "$TOOL_DIR/appimagetool"

# 不用 FUSE 运行：先自解压，再调用解出来的 AppRun（CI 与容器里最稳）
( cd "$TOOL_DIR" && ./appimagetool --appimage-extract >/dev/null )

APPIMAGE="$OUT_DIR/FrameGuard-${VERSION}-linux-${ARCH}.AppImage"
rm -f "$APPIMAGE"
ARCH="$ARCH" "$TOOL_DIR/squashfs-root/AppRun" "$APPDIR" "$APPIMAGE"
chmod +x "$APPIMAGE"
echo "✅ $APPIMAGE"

# -------------------------------------------------- 备用分发：tar.gz（无 FUSE 环境）
TARBALL="$OUT_DIR/FrameGuard-${VERSION}-linux-${ARCH}.tar.gz"
tar -C "$DIST_DIR" -czf "$TARBALL" FrameGuard
echo "✅ $TARBALL"

rm -rf "$TOOL_DIR"
