import atexit
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT.parent / "AGTAAM-Backend"     # backend folder ka asal path
APP = "main:app"                                  # backend/main.py ka `app`
HOST, PORT = "127.0.0.1", 8765
BASE_URL = f"http://{HOST}:{PORT}"
API_PREFIX = "/api/v1"                            # config.py ke settings.api_prefix jaisa
LOG_FILE = ROOT / "backend.log"                   # backend ka output yahan likha jata hai

_proc: subprocess.Popen | None = None


def _healthy() -> bool:
    try:
        return httpx.get(BASE_URL + "/health", timeout=1).status_code == 200
    except httpx.HTTPError:
        return False


def launch_backend() -> None:
    """Start the backend in the background and return immediately."""
    global _proc
    if _proc is not None and _proc.poll() is None:
        return                                    # already starting / running
    if _healthy():
        return                                    # someone started it already
    log = open(LOG_FILE, "ab")
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    _proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", APP, "--host", HOST, "--port", str(PORT)],
        cwd=BACKEND_DIR, stdout=log, stderr=log, creationflags=flags)
    atexit.register(stop_backend)


def wait_until_ready(timeout: float = 40.0) -> None:
    """Block until /health answers. Starts the backend if it is not running."""
    if not _healthy():
        launch_backend()
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _healthy():
            return
        if _proc is not None and _proc.poll() is not None:
            raise RuntimeError(f"Backend stopped while starting. See {LOG_FILE}")
        time.sleep(0.3)
    raise RuntimeError(f"Backend did not start in {timeout:.0f}s. See {LOG_FILE}")


def stop_backend() -> None:
    global _proc
    if _proc is not None and _proc.poll() is None:
        _proc.terminate()
        try:
            _proc.wait(5)
        except subprocess.TimeoutExpired:
            _proc.kill()
    _proc = None