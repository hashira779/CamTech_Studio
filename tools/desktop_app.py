"""
VIDA Desktop Application Launcher
Launches the FastAPI backend and opens VIDA as a dedicated native PC desktop window
with custom window geometry and no browser URL bar/tabs.
"""

import os
import sys

os.environ["PYTHONUNBUFFERED"] = "1"
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
if os.path.exists(os.path.expanduser("~/.cache/huggingface/hub")):
    os.environ["HF_HUB_OFFLINE"] = "1"

import time
import socket
import subprocess
import threading
import webbrowser

def get_base_dir():
    file_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(file_dir) if os.path.basename(file_dir).lower() == "tools" else file_dir

def is_port_in_use(port: int) -> bool:
    """Checks if a port is in use or already bound."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return False
    except OSError:
        return True

def find_free_port(default_port: int = 8000) -> int:
    """Dynamically finds the next available port starting from default_port (8000, 8001, 8002...)."""
    for port in range(default_port, default_port + 100):
        if not is_port_in_use(port):
            return port
    return default_port

def wait_for_server(port, timeout=10.0):
    """Waits until the FastAPI server is responding."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.5)
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    return True
        except Exception:
            pass
        time.sleep(0.2)
    return False

def open_desktop_window(app_url: str, port: int = 8000):
    """
    Opens the URL in standalone PC Desktop App mode using Microsoft Edge or Google Chrome,
    which provides a native application frame without browser chrome (URL bar, tabs, etc).
    Falls back to system default browser if app mode is not found.
    """
    # Candidates for Windows App Mode
    browser_candidates = [
        # Microsoft Edge (Installed on every Windows 10/11 system)
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        # Google Chrome
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]

    edge_or_chrome = None
    for path in browser_candidates:
        if os.path.exists(path):
            edge_or_chrome = path
            break

    user_data_dir = os.path.join(get_base_dir(), f".app_profile_{port}")

    if edge_or_chrome:
        cmd = [
            edge_or_chrome,
            f"--app={app_url}",
            "--window-size=1480,940",
            f"--user-data-dir={user_data_dir}",
            "--disable-extensions",
            "--disable-plugins"
        ]
        try:
            subprocess.Popen(cmd)
            print(f"Launched VIDA Desktop Native Window via {os.path.basename(edge_or_chrome)}")
            return
        except Exception as e:
            print(f"App mode launch error: {e}")

    # Fallback to standard browser tab
    print(f"Opening in default browser: {app_url}")
    webbrowser.open(app_url)

def main():
    base_dir = get_base_dir()
    os.chdir(base_dir)
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)

    # Automatically switch to project virtualenv if running under another Python
    venv_python = os.path.join(base_dir, "venv", "Scripts", "python.exe")
    if os.path.exists(venv_python) and os.path.abspath(sys.executable).lower() != os.path.abspath(venv_python).lower():
        print(f"[*] Switching to project environment: {venv_python}")
        import subprocess
        sys.exit(subprocess.call([venv_python] + sys.argv))

    # Dynamically find next available port (e.g. 8000, 8001, 8002...)
    port = find_free_port(8000)
    app_url = f"http://127.0.0.1:{port}"

    print("=" * 65)
    print("   VIDA — Visual Intelligent Dynamic Audio-Video Studio")
    print(f"   [⚡] Dynamic Service Port: {port} | Desktop URL: {app_url}")
    print("=" * 65)

    def wait_and_open():
        if wait_for_server(port):
            open_desktop_window(app_url, port)
        else:
            print("Warning: Server took longer than expected to start.")
            open_desktop_window(app_url, port)

    # Spawn a background thread to open the UI once the server boots
    browser_thread = threading.Thread(target=wait_and_open, daemon=True)
    browser_thread.start()

    # Run Uvicorn in the MAIN thread so signal handlers (reload=True) work!
    import uvicorn
    reload_dirs = [
        os.path.join(base_dir, "backend"),
        os.path.join(base_dir, "kmvm"),
        os.path.join(base_dir, "frontend"),
    ]
    try:
        uvicorn.run("backend.app:app", host="127.0.0.1", port=port, log_level="info", reload=True, reload_dirs=reload_dirs, access_log=True)
    except KeyboardInterrupt:
        print(f"\nStopping VIDA Desktop App on port {port}...")
    finally:
        print(f"[*] VIDA Server on port {port} stopped cleanly.")

if __name__ == "__main__":
    main()
