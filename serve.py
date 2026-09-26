#!/usr/bin/env python3
"""帧防 FrameGuard · 跨平台服务管理器（Windows / Linux / macOS 通用）

用法：
    python serve.py start      # 后台启动（脱离终端，关闭终端也不受影响）
    python serve.py stop       # 停止
    python serve.py restart    # 重启
    python serve.py status     # 查看状态
    python serve.py start --port 8080

前台运行（Docker / systemd 场景）：
    python app.py
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(APP_DIR, "cache")
PID_FILE = os.path.join(CACHE_DIR, "server.pid")
LOG_FILE = os.path.join(CACHE_DIR, "server.log")
APP_ENTRY = os.path.join(APP_DIR, "app.py")
ENV_FILE = os.path.join(APP_DIR, ".env")

IS_WINDOWS = os.name == "nt"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 7891
START_TIMEOUT = 40

# 这些变量可能来自临时终端 / 自动化会话。进程继承后若代理失效，
# 所有模型请求都会报 APIConnectionError —— 启动前统一清掉，
# 改由界面「网络代理」或 .env 显式控制。
PROXY_VARS = (
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "all_proxy",
)


def load_env_file(path: str = ENV_FILE) -> None:
    """读取项目根目录的 .env（不覆盖已存在的环境变量）。

    本脚本要在「依赖尚未安装」时也能运行，因此不引入 python-dotenv，
    这里自带一个极简实现，与 core/config.py 中的解析规则保持一致。
    这样 .env 里配置的 FRAMEGUARD_HOST / FRAMEGUARD_PORT 才能真正生效。
    """
    if not os.path.isfile(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


load_env_file()


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------
def _base_url(host: str, port: int) -> str:
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    return f"http://{probe_host}:{port}/"


def port_in_use(port: int, host: str = DEFAULT_HOST) -> bool:
    """是否有服务正在监听该端口（用 TCP 连接探测，跨平台通用）。"""
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.7)
        return sock.connect_ex((probe_host, port)) == 0


def find_free_port(preferred: int, host: str = DEFAULT_HOST) -> int:
    """优先使用指定端口；被占用时向后顺延，最后兜底让系统分配。"""
    probe_host = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    for candidate in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((probe_host, candidate))
                return candidate
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((probe_host, 0))
        return int(sock.getsockname()[1])


def read_pid() -> int | None:
    try:
        with open(PID_FILE, "r", encoding="utf-8") as fh:
            return int((fh.read() or "").strip())
    except (OSError, ValueError):
        return None


def write_pid(pid: int) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(PID_FILE, "w", encoding="utf-8") as fh:
        fh.write(str(pid))


def clear_pid() -> None:
    try:
        os.remove(PID_FILE)
    except OSError:
        pass


def process_alive(pid: int) -> bool:
    """进程是否存活（跨平台）。"""
    if pid <= 0:
        return False
    if IS_WINDOWS:
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=10,
            ).stdout
            return str(pid) in out
        except Exception:                                   # noqa: BLE001
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def http_ready(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(_base_url(host, port), timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def build_env(host: str, port: int) -> dict:
    env = dict(os.environ)
    env["FRAMEGUARD_HOST"] = host
    env["FRAMEGUARD_PORT"] = str(port)
    env["PYTHONUNBUFFERED"] = "1"          # 否则日志会被块缓冲，排查时看不到输出
    for key in PROXY_VARS:
        env.pop(key, None)
    return env


def kill_process(pid: int) -> bool:
    if IS_WINDOWS:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                           capture_output=True, timeout=15)
            return True
        except Exception:                                   # noqa: BLE001
            return False
    import signal

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.kill(pid, sig)
        except OSError:
            return True
        for _ in range(10):
            time.sleep(0.2)
            if not process_alive(pid):
                return True
    return not process_alive(pid)


# --------------------------------------------------------------------------
# 启动
# --------------------------------------------------------------------------
def spawn_detached(host: str, port: int) -> int:
    """以「脱离当前终端/会话」的方式启动服务，返回子进程 PID。

    - POSIX：双 fork + setsid，进程彻底脱离会话与进程组
    - Windows：DETACHED_PROCESS + CREATE_NEW_PROCESS_GROUP，不依附父进程控制台
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    env = build_env(host, port)

    if IS_WINDOWS:
        flags = 0
        flags |= getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        flags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        flags |= getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        log = open(LOG_FILE, "ab", buffering=0)
        proc = subprocess.Popen(
            [sys.executable, APP_ENTRY],
            stdout=log, stderr=log, stdin=subprocess.DEVNULL,
            cwd=APP_DIR, env=env, creationflags=flags,
        )
        return proc.pid

    if not hasattr(os, "fork"):                             # 兜底：非 fork 平台
        log = open(LOG_FILE, "ab", buffering=0)
        proc = subprocess.Popen(
            [sys.executable, APP_ENTRY],
            stdout=log, stderr=log, stdin=subprocess.DEVNULL, cwd=APP_DIR, env=env,
        )
        return proc.pid

    pid = os.fork()
    if pid > 0:                                             # 父进程
        os.waitpid(pid, 0)
        return read_pid() or 0

    os.setsid()                                             # 第一层子进程：新会话首进程
    if os.fork() > 0:
        os._exit(0)                                         # 第一层退出，孙进程被 init 接管

    log = open(LOG_FILE, "ab", buffering=0)
    devnull = open(os.devnull, "rb")
    child = subprocess.Popen(
        [sys.executable, APP_ENTRY],
        stdout=log, stderr=log, stdin=devnull,
        cwd=APP_DIR, env=env, start_new_session=True,
    )
    write_pid(child.pid)
    os._exit(0)


def preflight() -> bool:
    """检查当前解释器是否装好了运行依赖，避免启动后才抛一堆 traceback。"""
    missing = []
    for module, package in (("gradio", "gradio"), ("openai", "openai"),
                            ("httpx", "httpx"), ("cv2", "opencv-python-headless"),
                            ("PIL", "pillow")):
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    if not missing:
        return True
    print("❌ 当前 Python 环境缺少依赖：" + "、".join(missing))
    print(f"   使用的解释器：{sys.executable}")
    print()
    print("请先安装依赖（在项目目录下执行）：")
    if IS_WINDOWS:
        print("   python -m venv .venv")
        print("   .venv\\Scripts\\pip install -r requirements.txt")
    else:
        print("   python3 -m venv .venv")
        print("   .venv/bin/pip install -r requirements.txt")
    print()
    print("若已用其他虚拟环境，请把该环境的 python 路径告诉本脚本，例如：")
    print("   FRAMEGUARD_PYTHON=/path/to/venv/bin/python python serve.py start")
    return False


def cmd_start(args: argparse.Namespace) -> int:
    host, wanted = args.host, args.port

    existing = read_pid()
    if existing and process_alive(existing):
        if http_ready(host, wanted):
            print(f"✅ 服务已在运行：{_base_url(host, wanted)}   (PID={existing})")
            return 0
        print(f"⚠️  发现僵尸进程 PID={existing}（进程在但端口无响应），正在清理后重启……")
        kill_process(existing)
        clear_pid()

    if not preflight():
        return 1

    if port_in_use(wanted, host):
        free = find_free_port(wanted + 1, host)
        print(f"⚠️  端口 {wanted} 已被其他程序占用，自动改用 {free}")
        wanted = free

    print(f"正在后台启动（{host}:{wanted}）……")
    pid = spawn_detached(host, wanted)
    if pid:
        write_pid(pid)

    deadline = time.time() + START_TIMEOUT
    while time.time() < deadline:
        time.sleep(1)
        if http_ready(host, wanted):
            print(f"✅ 已启动：{_base_url(host, wanted)}   (PID={read_pid()})")
            print(f"   日志：{LOG_FILE}")
            print("   停止：python serve.py stop")
            return 0

    print(f"⚠️  {START_TIMEOUT} 秒内未就绪，日志尾部：")
    try:
        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as fh:
            print("".join(fh.readlines()[-25:]))
    except OSError:
        print("(未能读取日志)")
    return 1


def cmd_stop(args: argparse.Namespace) -> int:
    stopped = False

    pid = read_pid()
    if pid and process_alive(pid):
        if kill_process(pid):
            print(f"已停止 PID={pid}")
            stopped = True
        else:
            print(f"⚠️  无法结束 PID={pid}，请手动处理")
    clear_pid()

    # 兜底：pidfile 丢失时按端口清理
    if not stopped and port_in_use(args.port, args.host):
        if IS_WINDOWS:
            try:
                out = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                                     capture_output=True, text=True, timeout=15).stdout
                for line in out.splitlines():
                    parts = line.split()
                    if len(parts) >= 5 and parts[1].endswith(f":{args.port}") and parts[3] == "LISTENING":
                        kill_process(int(parts[4]))
                        print(f"已清理占用端口 {args.port} 的进程 PID={parts[4]}")
                        stopped = True
            except Exception:                               # noqa: BLE001
                pass
        else:
            try:
                out = subprocess.run(["lsof", "-nP", f"-tiTCP:{args.port}", "-sTCP:LISTEN"],
                                     capture_output=True, text=True, timeout=15).stdout
                for line in out.split():
                    if line.strip().isdigit():
                        kill_process(int(line))
                        print(f"已清理占用端口 {args.port} 的进程 PID={line}")
                        stopped = True
            except Exception:                               # noqa: BLE001
                pass

    if not stopped:
        print("没有正在运行的服务。")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    pid = read_pid()
    alive = bool(pid and process_alive(pid))
    ready = http_ready(args.host, args.port)
    print(f"服务地址 : {_base_url(args.host, args.port)}")
    print(f"进程     : {'运行中 PID=' + str(pid) if alive else '未运行'}")
    print(f"HTTP     : {'可访问 ✅' if ready else '不可访问 ❌'}")
    print(f"日志     : {LOG_FILE}")
    return 0 if ready else 1


def cmd_restart(args: argparse.Namespace) -> int:
    cmd_stop(args)
    time.sleep(1.5)
    return cmd_start(args)


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="serve.py",
        description="帧防 FrameGuard 服务管理器（跨平台）",
    )
    parser.add_argument("command", choices=["start", "stop", "restart", "status"],
                        help="要执行的操作")
    parser.add_argument("--host", default=os.environ.get("FRAMEGUARD_HOST", DEFAULT_HOST),
                        help=f"监听地址，默认 {DEFAULT_HOST}")
    parser.add_argument("--port", type=int,
                        default=int(os.environ.get("FRAMEGUARD_PORT", DEFAULT_PORT)),
                        help=f"监听端口，默认 {DEFAULT_PORT}")
    args = parser.parse_args(argv)

    handlers = {
        "start": cmd_start,
        "stop": cmd_stop,
        "restart": cmd_restart,
        "status": cmd_status,
    }
    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
