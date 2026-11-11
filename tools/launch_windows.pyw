"""Launch the local Champions Meta Lab backend and Windows desktop app."""

import ctypes
import json
import os
import socket
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = BACKEND / ".venv" / "Scripts" / "python.exe"
APP = ROOT / "app" / "build" / "windows" / "x64" / "runner" / "Release" / "champions_meta_lab.exe"
HOST, PORT = "127.0.0.1", 8000
LOG = BACKEND / "data" / "windows-launch.log"


def backend_ready():
    try:
        with urlopen(f"http://{HOST}:{PORT}/openapi.json", timeout=1) as response:
            schema = json.load(response)
        return (schema.get("info", {}).get("title") == "Champions Meta Lab"
                and {"/api/parties/simulated", "/api/battle/scout", "/api/battle/{battle_id}/replace", "/api/team/build"}
                <= schema.get("paths", {}).keys())
    except (OSError, ValueError):
        return False


def start_backend():
    if backend_ready():
        return
    try:
        connection = socket.create_connection((HOST, PORT), timeout=1)
    except (ConnectionRefusedError, TimeoutError):
        pass
    else:
        connection.close()
        raise RuntimeError(f"{PORT}번 포트에서 실행 중인 서버를 확인해 주세요.")

    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("ab") as output:
        process = subprocess.Popen(
            [str(PYTHON), "-B", "-m", "uvicorn", "app.main:app", "--host", HOST, "--port", str(PORT)],
            cwd=BACKEND,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if backend_ready():
            return
        if process.poll() is not None:
            break
        time.sleep(0.2)
    raise RuntimeError(f"로컬 서버를 시작하지 못했습니다.\n{LOG}")


def main():
    if not APP.is_file():
        raise RuntimeError(f"Windows 릴리스 빌드를 찾을 수 없습니다.\n{APP}")
    start_backend()
    os.startfile(str(APP), cwd=str(APP.parent))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        ctypes.windll.user32.MessageBoxW(None, str(error), "Champions Meta Lab", 0x10)
