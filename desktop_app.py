"""
VIDA Desktop Application Launcher
Launches the FastAPI backend and opens VIDA as a dedicated native PC desktop window
with custom window geometry and no browser URL bar/tabs.
"""

import os
import sys
import time
import socket
import subprocess
import threading
import webbrowser

def find_free_port(default_port=8000):
    """Finds an available local port."""
    for port in range(default_port, default_port + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
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

def open_desktop_window(app_url: str):
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

    user_data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".app_profile")

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

def run_server(port):
    """Runs uvicorn FastAPI server with auto-reload."""
    import uvicorn
    # reload=True automatically restarts the backend when Python files are updated!
    uvicorn.run("backend.app:app", host="127.0.0.1", port=port, log_level="info", reload=True)

def main():
    # Automatically switch to project virtualenv if running under another Python
    base_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(base_dir, "venv", "Scripts", "python.exe")
    if os.path.exists(venv_python) and os.path.abspath(sys.executable).lower() != os.path.abspath(venv_python).lower():
        print(f"[*] Switching to project environment: {venv_python}")
        import subprocess
        sys.exit(subprocess.call([venv_python] + sys.argv))

    port = find_free_port(8000)
    app_url = f"http://127.0.0.1:{port}"

    print("=" * 65)
    print(f"   VIDA — Visual Intelligent Dynamic Audio-Video Studio")
    print(f"   Desktop App URL: {app_url}")
    print("=" * 65)

    def wait_and_open():
        if wait_for_server(port):
            open_desktop_window(app_url)
        else:
            print("Warning: Server took longer than expected to start.")
            open_desktop_window(app_url)

    # Spawn a background thread to open the UI once the server boots
    browser_thread = threading.Thread(target=wait_and_open, daemon=True)
    browser_thread.start()

    # Run Uvicorn in the MAIN thread so signal handlers (reload=True) work!
    import uvicorn
    try:
        uvicorn.run("backend.app:app", host="127.0.0.1", port=port, log_level="info", reload=True)
    except KeyboardInterrupt:
        print("\nStopping VIDA Desktop App...")

if __name__ == "__main__":
    main()
