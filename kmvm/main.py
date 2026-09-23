"""
Entry Point for Khmer Music Video Maker Desktop Application
Initializes Qt 6 application and launches the main window with Live Auto-Reflect.
"""

import os
import sys

# Ensure project root in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PySide6.QtWidgets import QApplication
from kmvm.app_window import KhmerMusicVideoMakerWindow
from kmvm.reloader import StateManager, InAppFileWatcher, run_supervisor


def main_app():
    """Run the actual Qt 6 GUI application."""
    app = QApplication(sys.argv)
    app.setApplicationName("Khmer Music Video Maker")
    app.setOrganizationName("KhmerAI")

    window = KhmerMusicVideoMakerWindow()
    window.show()
    window.raise_()
    window.activateWindow()

    # Restore previous session state / geometry if reloading
    restored = StateManager.restore_state(window)
    if not restored:
        print("[KMVM] ✓ Window launched fresh", flush=True)

    # In-app file watcher as an extra safeguard for standalone launches
    is_child = "--child" in sys.argv or os.environ.get("KMVM_CHILD") == "1"
    if not is_child and "--no-reload" not in sys.argv:
        watcher = InAppFileWatcher(parent=window)

        def _on_code_change(path):
            rel = os.path.relpath(path, BASE_DIR)
            print(f"[KMVM In-App Auto-Reflect] 🔄 Detected update in {rel}! Reloading...", flush=True)
            window.reload_application()

        watcher.file_changed.connect(_on_code_change)
        watcher.start()

    print("[KMVM] ✓ Auto-Reflect active: code updates will automatically reload without manual restart", flush=True)
    sys.exit(app.exec())


def main():
    # If explicitly running child or --no-reload, run app directly
    if "--child" in sys.argv or os.environ.get("KMVM_CHILD") == "1" or "--no-reload" in sys.argv:
        main_app()
    else:
        # Default: Run supervisor with live auto-reload
        try:
            run_supervisor()
        except KeyboardInterrupt:
            print("\n[KMVM] Stopped by user.", flush=True)


if __name__ == "__main__":
    main()
