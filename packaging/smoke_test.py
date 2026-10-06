#!/usr/bin/env python3
"""帧防 FrameGuard · 安装包冒烟测试。

在做完 PyInstaller 打包之后运行，确认冻结出来的程序**真的能起来并对外服务**。
这能挡住最常见的几类打包事故：

  * prompts / rules 等资源没打进去 → 界面规则框空白
  * Gradio 前端静态资源缺失 → 页面能返回但一片空白
  * 某个依赖被漏掉 → 启动即 ImportError

用法：
    python packaging/smoke_test.py [dist目录，默认 dist]

退出码 0 = 通过；非 0 = 失败（CI 会因此标红）。
"""

from __future__ import annotations

import glob
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Windows 上 Python 默认用本地代码页（cp1252/gbk）写 stdout，
# 直接 print 中文或 ✅ 会抛 UnicodeEncodeError，这里统一改成 UTF-8。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")     # type: ignore[union-attr]
    except Exception:                                               # noqa: BLE001
        pass

DIST = sys.argv[1] if len(sys.argv) > 1 else "dist"
IS_WIN = os.name == "nt"

REQUIRED_RESOURCES = [
    os.path.join("prompts", "workplace_safety.md"),
    os.path.join("rules", "default_rules.md"),
]


def fail(message: str) -> None:
    print(f"❌ {message}")
    raise SystemExit(1)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def find_executable() -> str:
    patterns = [
        os.path.join(DIST, "FrameGuard.app", "Contents", "MacOS", "FrameGuard"),
        os.path.join(DIST, "FrameGuard", "FrameGuard.exe"),
        os.path.join(DIST, "FrameGuard", "FrameGuard"),
    ]
    for pattern in patterns:
        if os.path.isfile(pattern):
            return os.path.abspath(pattern)
    found = sorted(glob.glob(os.path.join(DIST, "**", "FrameGuard*"), recursive=True))
    fail(f"在 {DIST} 下找不到可执行文件，实际内容：{found[:20]}")
    return ""   # 不可达，仅为类型检查


def check_resources() -> None:
    """资源文件必须随包分发，否则安装后规则/模板读不到。"""
    root = DIST
    for rel in REQUIRED_RESOURCES:
        hits = glob.glob(os.path.join(root, "**", rel), recursive=True)
        if not hits:
            fail(f"打包结果里缺少资源文件：{rel}")
        print(f"✅ 资源就位：{os.path.relpath(hits[0], root)}")


def wait_http(port: int, timeout: float = 180.0) -> str:
    url = f"http://127.0.0.1:{port}/"
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if resp.status == 200 and "<html" in body.lower():
                    return body
                last = f"HTTP {resp.status}，响应体 {len(body)} 字节"
        except (urllib.error.URLError, OSError, ValueError) as exc:
            last = str(exc)
        time.sleep(2)
    fail(f"{timeout:.0f} 秒内服务未就绪，最后状态：{last}")
    return ""   # 不可达


def main() -> int:
    if not os.path.isdir(DIST):
        fail(f"目录不存在：{DIST}（请先执行 pyinstaller packaging/frameguard.spec）")

    exe = find_executable()
    print(f"可执行文件：{exe}")
    check_resources()

    port = free_port()
    env = dict(os.environ)
    env.update({
        "FRAMEGUARD_HOST": "127.0.0.1",
        "FRAMEGUARD_PORT": str(port),
        "FRAMEGUARD_OPEN_BROWSER": "0",
        "FRAMEGUARD_HEADLESS": "1",          # 不要在 CI 里弹错误对话框
        "PYTHONUNBUFFERED": "1",
    })
    # 让数据目录落在临时位置，避免污染 runner 上的用户目录
    env["FRAMEGUARD_OUTPUT_DIR"] = os.path.abspath(os.path.join(DIST, "..", "_smoke", "outputs"))
    env["FRAMEGUARD_CACHE_DIR"] = os.path.abspath(os.path.join(DIST, "..", "_smoke", "cache"))
    os.makedirs(env["FRAMEGUARD_OUTPUT_DIR"], exist_ok=True)
    os.makedirs(env["FRAMEGUARD_CACHE_DIR"], exist_ok=True)

    print(f"启动服务（端口 {port}）……")
    log = open(os.path.join(env["FRAMEGUARD_CACHE_DIR"], "smoke.log"), "wb")
    proc = subprocess.Popen([exe], env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL)

    def dump_log() -> None:
        try:
            log.flush()
            with open(os.path.join(env["FRAMEGUARD_CACHE_DIR"], "smoke.log"),
                      "r", encoding="utf-8", errors="replace") as fh:
                tail = fh.read()[-4000:]
            if tail.strip():
                print("──── 子进程日志尾部 ────")
                print(tail)
                print("────────────────────────")
        except OSError:
            pass

    try:
        body = wait_http(port)
        print(f"✅ 服务可访问：HTTP 200，首页 {len(body)} 字节")

        # Gradio 的配置接口能返回 JSON，说明前端资源与后端路由都装好了
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/config", timeout=10) as resp:
                config = resp.read().decode("utf-8", errors="replace")
            if "components" not in config:
                fail("Gradio /config 返回内容异常，前端资源可能缺失")
            print(f"✅ Gradio 配置接口正常（{len(config)} 字节）")
        except (urllib.error.URLError, OSError) as exc:
            fail(f"Gradio /config 不可用：{exc}")

        # 顺带验证自带的停止命令可用（安装后用户靠它关闭服务）
        stop = subprocess.run([exe, "stop"], env=env, capture_output=True, timeout=60)
        print(f"`FrameGuard stop` 退出码：{stop.returncode}")
    except SystemExit:
        dump_log()
        raise
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
        log.close()

    print("🎉 冒烟测试通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
