"""Run the local dashboard on loopback and open a browser after health is ready."""

from __future__ import annotations

import argparse
import json
import threading
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOOPBACK = "127.0.0.1"


def parse_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Port must be an integer from 1024 to 65535.") from exc
    if not 1024 <= port <= 65535:
        raise argparse.ArgumentTypeError("Port must be from 1024 to 65535.")
    return port


def ensure_port_available(port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            probe.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            probe.bind((LOOPBACK, port))
        except OSError as exc:
            raise RuntimeError(
                f"Port {port} is already in use or unavailable. Close the existing dashboard "
                "with Ctrl+C in its console, or set STATS_PORT to an unused port. "
                "No browser has been opened."
            ) from exc


def stop_server(process: subprocess.Popen[bytes]) -> bool:
    if process.poll() is not None:
        return True
    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)
        process.wait(timeout=8)
        return True
    except (OSError, subprocess.TimeoutExpired):
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-browser", action="store_true", help="Start without opening a browser.")
    parser.add_argument("--port", type=parse_port, default=os.environ.get("STATS_PORT", "8501"))
    parser.add_argument("--managed", action="store_true", help="Private INTERLINKED stdin/stdout lifecycle protocol.")
    args = parser.parse_args()
    if args.managed:
        return managed_main(args)
    if os.environ.get("STATS_MODE", "local").strip().lower() != "local":
        print("This launcher is for local mode only. See docs/HOSTING.md for hosted requirements.", file=sys.stderr)
        return 1
    expected_python = PROJECT_ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    # sys.prefix identifies the active environment even when python is a symlink on Linux.
    if Path(sys.prefix).resolve() != (PROJECT_ROOT / ".venv").resolve():
        print(f"Use the project environment: {expected_python}\nRun setup_windows.bat first.", file=sys.stderr)
        return 1
    if not (PROJECT_ROOT / "app.py").is_file():
        print("app.py is missing. Restore the complete application before launching.", file=sys.stderr)
        return 1
    try:
        ensure_port_available(args.port)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    environment = os.environ.copy()
    environment.update({"STATS_MODE": "local", "PYTHONUTF8": "1"})
    command = [
        sys.executable, "-m", "streamlit", "run", str(PROJECT_ROOT / "app.py"),
        "--server.address", LOOPBACK,
        "--server.port", str(args.port),
        "--browser.serverAddress", LOOPBACK,
        "--browser.serverPort", str(args.port),
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false",
        "--server.fileWatcherType", "none",
    ]
    creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    url = f"http://{LOOPBACK}:{args.port}"
    process: subprocess.Popen[bytes] | None = None
    try:
        print(f"Starting The Stats at {url}", flush=True)
        print("Keep this console open. Press Ctrl+C here to stop the dashboard.", flush=True)
        process = subprocess.Popen(command, cwd=PROJECT_ROOT, env=environment, creationflags=creation_flags)
        # Local health requests must not go through a configured web proxy.
        opener = build_opener(ProxyHandler({}))
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            exit_code = process.poll()
            if exit_code is not None:
                print(f"Streamlit exited before becoming ready (exit {exit_code}).", file=sys.stderr)
                return exit_code or 1
            try:
                with opener.open(url + "/_stcore/health", timeout=1) as response:
                    ready = response.status == 200 and response.read(64).strip() == b"ok"
                if ready:
                    # Check again after readiness so an early failed child cannot open another service.
                    if process.poll() is not None:
                        raise RuntimeError("Streamlit stopped while starting.")
                    print(f"Dashboard ready: {url}", flush=True)
                    if not args.no_browser and not webbrowser.open(url):
                        print(f"The browser did not open automatically. Open {url} manually.", flush=True)
                    break
            except (URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(0.2)
        else:
            raise RuntimeError("Streamlit did not become ready within 60 seconds. Check the error above.")
        return process.wait()
    except KeyboardInterrupt:
        print("\nStopping The Stats...", flush=True)
        return 0
    except (OSError, RuntimeError) as exc:
        print(f"LAUNCH ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        if process is not None:
            stop_server(process)



def managed_main(args) -> int:
    """Only fixed lifecycle messages use stdout; Streamlit output uses stderr."""
    def emit(kind, **values):
        print(json.dumps(dict(protocol="stats-managed-v1", type=kind, **values)), flush=True)

    stopping = threading.Event()
    def controls():
        try:
            for line in sys.stdin:
                if len(line) > 4096 or json.loads(line) != {"action": "stop"}:
                    raise ValueError("Invalid managed stop message")
                stopping.set()
                return
        except (ValueError, OSError):
            pass
        finally:
            # Losing the private parent pipe also requests a graceful stop.
            stopping.set()

    process = None
    clean = False
    code = 1
    try:
        if os.environ.get("STATS_MODE", "local").strip().lower() != "local":
            raise RuntimeError("Managed launch requires local mode.")
        data = os.environ.get("STATS_DATA_DIR", "")
        if not data or not Path(data).is_absolute() or data.startswith(("\\\\", "//")) or not (Path(data)/"stats.sqlite3").is_file():
            raise RuntimeError("Managed launch requires an existing explicit local Stats library.")
        if Path(sys.prefix).resolve() != (PROJECT_ROOT/".venv").resolve():
            raise RuntimeError("Use the reviewed project environment.")
        ensure_port_available(args.port)
        from interlinked_preflight import validate_registered_library
        validate_registered_library(data)
        environment = os.environ.copy()
        environment.update(STATS_MODE="local", PYTHONUTF8="1")
        command = [sys.executable, "-m", "streamlit", "run", str(PROJECT_ROOT/"app.py"),
                   "--server.address", LOOPBACK, "--server.port", str(args.port),
                   "--browser.serverAddress", LOOPBACK, "--browser.serverPort", str(args.port),
                   "--server.headless", "true", "--browser.gatherUsageStats", "false",
                   "--server.fileWatcherType", "none"]
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        process = subprocess.Popen(command, cwd=PROJECT_ROOT, env=environment,
                                   stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr,
                                   creationflags=flags)
        threading.Thread(target=controls, name="stats-managed-control", daemon=True).start()
        opener = build_opener(ProxyHandler({}))
        url = f"http://{LOOPBACK}:{args.port}"
        deadline = time.monotonic()+60
        ready = False
        while process.poll() is None and not stopping.wait(.2):
            if not ready:
                try:
                    with opener.open(url+"/_stcore/health", timeout=1) as response:
                        healthy = response.status == 200 and response.read(64).strip() == b"ok"
                    if healthy and process.poll() is None:
                        emit("ready", url=url)
                        ready = True
                except (URLError, TimeoutError, ConnectionError):
                    pass
                if not ready and time.monotonic() >= deadline:
                    raise RuntimeError("Stats did not become ready within 60 seconds.")
        if stopping.is_set():
            clean = stop_server(process)
            code = 0 if clean else 1
        else:
            code = process.returncode or 1
            raise RuntimeError(f"Streamlit stopped unexpectedly (exit {process.returncode}).")
    except Exception as exc:
        emit("error", message=str(exc))
    finally:
        if process is not None and process.poll() is None:
            stop_server(process)
        emit("exit", clean=clean, code=code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
