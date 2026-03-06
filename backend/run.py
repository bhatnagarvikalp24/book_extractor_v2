"""
Desktop entry point for ISBN Scanner.
Starts the FastAPI/uvicorn server and opens the browser automatically.

Works in both:
  - Console mode (terminal visible — local dev / Windows)
  - Windowed mode (no terminal — macOS .app bundle)
"""
import logging
import os
import sys
import threading
import webbrowser

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"


# ── Logging setup ─────────────────────────────────────────────────────────────
# In windowed mode (no terminal) we write to ~/Library/Logs/ISBNScanner/
# so crashes can be diagnosed. On Windows logs go to %APPDATA%/ISBNScanner/.

def _log_dir() -> str:
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Logs/ISBNScanner")
    return os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ISBNScanner", "Logs")

_log_path = os.path.join(_log_dir(), "isbn_scanner.log")
os.makedirs(_log_dir(), exist_ok=True)
logging.basicConfig(
    filename=_log_path,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _open_browser():
    import time
    time.sleep(1.8)
    webbrowser.open(URL)


def _find_frontend_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "frontend_out")  # type: ignore[attr-defined]
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(backend_dir, "..", "frontend", "out")


def _show_error(msg: str) -> None:
    """Show a native error dialog — works even with no terminal."""
    logging.error(msg)
    if sys.platform == "darwin":
        import subprocess
        subprocess.run([
            "osascript", "-e",
            f'display dialog "ISBN Scanner could not start:\\n\\n{msg}" '
            f'buttons {{"OK"}} with icon stop with title "ISBN Scanner"',
        ])
    elif sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, msg, "ISBN Scanner — Error", 0x10)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    if getattr(sys, "frozen", False):
        sys.path.insert(0, sys._MEIPASS)  # type: ignore[attr-defined]

    try:
        from app.main import app as fastapi_app
        from fastapi.staticfiles import StaticFiles

        frontend_dir = _find_frontend_dir()
        existing_paths = {getattr(r, "path", "") for r in fastapi_app.routes}
        if os.path.isdir(frontend_dir) and "/" not in existing_paths:
            fastapi_app.mount(
                "/", StaticFiles(directory=frontend_dir, html=True), name="frontend"
            )

        logging.info(f"Starting ISBN Scanner at {URL}")
        threading.Thread(target=_open_browser, daemon=True).start()
        uvicorn.run(fastapi_app, host=HOST, port=PORT, log_level="warning")

    except OSError as e:
        if "address already in use" in str(e).lower():
            # Server already running — just open the browser
            webbrowser.open(URL)
        else:
            _show_error(str(e))
    except Exception as e:
        _show_error(str(e))
