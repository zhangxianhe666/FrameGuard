# -*- mode: python ; coding: utf-8 -*-
"""帧防 FrameGuard · PyInstaller 打包配置（macOS / Linux / Windows 通用）。

设计要点：
  1. Gradio 的前端资源、uvicorn 的动态导入后端都不是"普通 import"能被静态发现的，
     因此对相关包统一 collect_all / collect_submodules，避免运行时缺文件。
  2. collect_all 逐包 try/except：某个包在当前平台不存在时跳过，不让整次打包失败。
  3. datas 带上 prompts / rules / .env.example，安装后开箱即用；
     outputs / cache 不在包内，运行时落到用户数据目录（见 core/config.py）。
  4. macOS 额外产出 .app（BUNDLE），供后续打成 .dmg。
  5. 资源放在 onedir 的默认 _internal 目录下（macOS 的 .app 里对应 Contents/Resources），
     它就是运行时的 sys._MEIPASS，因此 core/config.py 里的 RESOURCE_DIR 能直接定位到
     prompts / rules，无需额外处理。

用法：
    pyinstaller --noconfirm --clean packaging/frameguard.spec
"""

import os
import sys

from PyInstaller.utils.hooks import collect_all, collect_submodules

# spec 由 PyInstaller exec 执行，没有 __file__；SPECPATH 是 spec 所在目录
ROOT = os.path.dirname(os.path.abspath(SPECPATH))
ASSETS = os.path.join(ROOT, "packaging", "assets")

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

VERSION = os.environ.get("FRAMEGUARD_VERSION", "1.0.0")

# --------------------------------------------------------------------------
# 依赖收集
# --------------------------------------------------------------------------
# 带数据文件 / 动态导入的包。列表按"实际安装的依赖集"编写，缺失项自动跳过。
PACKAGES = [
    # 界面与服务
    "gradio", "gradio_client", "safehttpx", "groovy", "hf_gradio",
    "uvicorn", "fastapi", "starlette", "anyio", "sniffio",
    "httpx", "httpcore", "httpx2", "httpcore2", "h11", "orjson",
    "multipart", "python_multipart", "sse_starlette",
    "pydantic", "pydantic_core", "typing_inspection",
    "jinja2", "markupsafe", "aiofiles",
    # 模型调用
    "openai", "jiter",
    # 数据处理与图像
    "cv2", "PIL", "numpy", "pandas", "pytz", "dateutil", "six",
    # 依赖树中的其余部分
    "huggingface_hub", "hf_xet", "fsspec", "filelock", "packaging",
    "typer", "rich", "markdown_it", "mdurl", "pygments", "click",
    "shellingham", "certifi", "truststore", "semantic_version",
    "tomlkit", "brotli", "tqdm", "yaml", "pydub", "audioop",
]

datas = [
    (os.path.join(ROOT, "prompts"), "prompts"),
    (os.path.join(ROOT, "rules"), "rules"),
    (os.path.join(ROOT, ".env.example"), "."),
    (os.path.join(ROOT, "README.md"), "."),
    (os.path.join(ROOT, "LICENSE"), "."),
]
binaries = []
hiddenimports = []

for _pkg in PACKAGES:
    try:
        _d, _b, _h = collect_all(_pkg)
        datas += _d
        binaries += _b
        hiddenimports += _h
    except Exception as _exc:                                # noqa: BLE001
        print(f"[spec] 跳过未安装的包 {_pkg}: {_exc}")

# 本项目自身模块（core 是包，app 是入口脚本）
try:
    hiddenimports += collect_submodules("core")
except Exception as _exc:                                    # noqa: BLE001
    print(f"[spec] core 子模块收集失败: {_exc}")

# --------------------------------------------------------------------------
# 图标
# --------------------------------------------------------------------------
icon = None
if IS_WIN:
    _candidate = os.path.join(ASSETS, "frameguard.ico")
elif IS_MAC:
    _candidate = os.path.join(ASSETS, "frameguard.icns")
else:
    _candidate = None
if _candidate and os.path.exists(_candidate):
    icon = _candidate
elif _candidate:
    print(f"[spec] 未找到图标 {_candidate}，改用默认图标（可先运行 packaging/build_assets.py）")

entitlements = None  # 签名与加固运行时统一在 packaging/macos/build_dmg.sh 里做，便于控制

# --------------------------------------------------------------------------
# 构建
# --------------------------------------------------------------------------
a = Analysis(
    [os.path.join(ROOT, "app.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 明确排除用不到的重型库，压小体积
        "matplotlib", "tkinter", "IPython", "notebook", "jupyter",
        "pytest", "setuptools", "distutils", "test", "unittest",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="FrameGuard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,              # GUI 应用：Windows 不弹黑窗，macOS 生成可双击的 .app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=entitlements,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="FrameGuard",
)

if IS_MAC:
    app = BUNDLE(
        coll,
        name="FrameGuard.app",
        icon=icon,
        bundle_identifier="com.zhangxianhe.frameguard",
        version=VERSION,
        info_plist={
            "CFBundleName": "FrameGuard",
            "CFBundleDisplayName": "FrameGuard",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "CFBundleGetInfoString": "帧防 FrameGuard · 视觉安全智能分析",
            "NSHumanReadableCopyright": "MIT License",
            "LSApplicationCategoryType": "public.app-category.utilities",
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
