"""
Desktop entry point for ISBN Scanner.
Starts the FastAPI/uvicorn server and opens the browser automatically.
"""
import os
import sys
import threading
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


def _open_browser():
    import time
    time.sleep(1.8)  # wait for uvicorn to be ready
    webbrowser.open(URL)


def _find_frontend_dir() -> str:
    if getattr(sys, "frozen", False):
        # PyInstaller one-dir: _MEIPASS is the _internal/ folder
        return os.path.join(sys._MEIPASS, "frontend_out")  # type: ignore[attr-defined]
    # Running from source: run.py is in backend/
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(backend_dir, "..", "frontend", "out")


if __name__ == "__main__":
    import uvicorn

    # Ensure app module is importable when running as frozen executable
    if getattr(sys, "frozen", False):
        sys.path.insert(0, sys._MEIPASS)  # type: ignore[attr-defined]

    # Import app and mount static frontend here (avoids PYZ stale-cache issues)
    from app.main import app as fastapi_app
    from fastapi.staticfiles import StaticFiles

    frontend_dir = _find_frontend_dir()
    # Only mount if not already mounted (app.main may have registered it already)
    existing_mounts = {r.path if hasattr(r, "path") else "" for r in fastapi_app.routes}
    if os.path.isdir(frontend_dir) and "/" not in existing_mounts:
        fastapi_app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
        print(f"Frontend mounted from: {frontend_dir}", flush=True)

    print(f"Starting ISBN Scanner at {URL}", flush=True)
    print("Browser will open automatically. Press Ctrl+C to quit.\n", flush=True)

    threading.Thread(target=_open_browser, daemon=True).start()
    uvicorn.run(fastapi_app, host=HOST, port=PORT, log_level="warning")
