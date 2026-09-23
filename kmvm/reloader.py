"""
KMVM Live Auto-Reflect & State Persistence Engine
Monitors source files for changes and automatically reloads the desktop app.
Also provides state saving/restoring (window geometry, active screen, loaded track).
"""

import json
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QThread, Signal

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(PROJECT_ROOT, ".kmvm_state.json")

# Directories and extensions to watch for code updates
WATCH_DIRS = ["kmvm", "backend"]
WATCH_EXTENSIONS = {".py", ".qss", ".json", ".html", ".css", ".js"}
IGNORE_DIRS = {".git", "__pycache__", "venv", ".venv", "node_modules", "uploads", "output", "scratch"}


# ==============================================================================
# File Watcher
# ==============================================================================

def get_watched_files() -> List[str]:
    """Collect all source files in watched directories."""
    files = []
    for d in WATCH_DIRS:
        full_dir = os.path.join(PROJECT_ROOT, d)
        if not os.path.isdir(full_dir):
            continue
        for root, dirs, fnames in os.walk(full_dir):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
            for f in fnames:
                ext = os.path.splitext(f)[1].lower()
                if ext in WATCH_EXTENSIONS:
                    files.append(os.path.join(root, f))
    return files


def get_file_mtimes() -> Dict[str, float]:
    """Get mapping of file path -> last modified timestamp."""
    mtimes = {}
    for path in get_watched_files():
        try:
            mtimes[path] = os.path.getmtime(path)
        except (OSError, PermissionError):
            pass
    return mtimes


class InAppFileWatcher(QThread):
    """
    Background thread running inside the Qt app that monitors source files.
    Emits `file_changed(str)` signal when an update is saved.
    """
    file_changed = Signal(str)

    def __init__(self, parent=None, poll_interval_sec: float = 0.8):
        super().__init__(parent)
        self.poll_interval_sec = poll_interval_sec
        self._running = True
        self._mtimes = get_file_mtimes()

    def stop(self):
        self._running = False

    def run(self):
        while self._running:
            time.sleep(self.poll_interval_sec)
            if not self._running:
                break
            try:
                current_files = get_watched_files()
                for path in current_files:
                    try:
                        mtime = os.path.getmtime(path)
                    except (OSError, PermissionError):
                        continue

                    old_mtime = self._mtimes.get(path)
                    if old_mtime is not None and mtime > old_mtime + 0.1:
                        self._mtimes[path] = mtime
                        # Give editor 200ms to finish writing before notifying
                        time.sleep(0.2)
                        self.file_changed.emit(path)
                        return

                    self._mtimes[path] = mtime
            except Exception:
                pass


# ==============================================================================
# State Manager (Preserves UI state & geometry across reloads)
# ==============================================================================

class StateManager:
    """Saves and restores window geometry and session state across reloads."""

    @staticmethod
    def save_state(window) -> None:
        """Save current window state to .kmvm_state.json before reloading."""
        try:
            state = {
                "geometry": {
                    "x": window.x(),
                    "y": window.y(),
                    "width": window.width(),
                    "height": window.height(),
                    "maximized": window.isMaximized(),
                },
                "page_index": window.stack.currentIndex() if hasattr(window, "stack") else 0,
                "audio_path": getattr(window, "audio_path", None),
                "song_title": getattr(window, "song_title", ""),
                "artist_name": getattr(window, "artist_name", ""),
                "selected_style": getattr(window, "selected_style", "Khmer Cinematic"),
                "aspect_ratio": getattr(window, "aspect_ratio", "16:9"),
                "quality_level": getattr(window, "quality_level", "Cinematic"),
                "current_time": getattr(window, "current_time", 0.0),
                "best_part": getattr(window, "best_part", None),
                "timestamp": time.time(),
            }
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            print("[KMVM Auto-Reflect] 💾 Saved session state for smooth reload.", flush=True)
        except Exception as e:
            print(f"[KMVM Auto-Reflect] ⚠️ Could not save state: {e}", flush=True)

    @staticmethod
    def restore_state(window) -> bool:
        """Restore window state from .kmvm_state.json if available."""
        if not os.path.exists(STATE_FILE):
            return False
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Check expiry (ignore if older than 5 minutes)
            if time.time() - state.get("timestamp", 0) > 300:
                os.remove(STATE_FILE)
                return False

            # Restore geometry
            geom = state.get("geometry", {})
            if geom:
                if geom.get("maximized", False):
                    window.showMaximized()
                else:
                    window.setGeometry(geom.get("x", 100), geom.get("y", 100),
                                       geom.get("width", 1500), geom.get("height", 940))

            # Restore metadata
            if state.get("audio_path"):
                window.audio_path = state["audio_path"]
                if hasattr(window, "_load_audio_player") and os.path.exists(window.audio_path):
                    window._load_audio_player(window.audio_path)
            if state.get("song_title"):
                window.song_title = state["song_title"]
            if state.get("artist_name"):
                window.artist_name = state["artist_name"]
            if state.get("selected_style"):
                window.selected_style = state["selected_style"]
            if state.get("aspect_ratio"):
                window.aspect_ratio = state["aspect_ratio"]
            if state.get("quality_level"):
                window.quality_level = state["quality_level"]
            if state.get("best_part"):
                window.best_part = state["best_part"]
                if hasattr(window, "sum_lbl_best_part"):
                    bp = window.best_part
                    window.sum_lbl_best_part.setText(
                        f"⭐ Best Part (Viral Hook): {bp['name']} "
                        f"[{bp.get('timestamp_str', '')}] (Score: {bp.get('score', 0)}%)"
                    )

            # Restore page index
            page_idx = state.get("page_index", 0)
            if hasattr(window, "stack") and 0 <= page_idx < window.stack.count():
                cur_t = state.get("current_time", 0.0)
                if page_idx == 2:
                    if hasattr(window, "preview_canvas"):
                        window.preview_canvas.song_title = window.song_title
                        window.preview_canvas.artist_name = window.artist_name
                        window.preview_canvas.aspect_ratio = window.aspect_ratio
                        window.preview_canvas.current_time = cur_t
                    if hasattr(window, "_load_audio_player") and window.audio_path:
                        window._load_audio_player(window.audio_path)
                    if hasattr(window, "_seek_to_time"):
                        window._seek_to_time(cur_t)
                window.stack.setCurrentIndex(page_idx)

            print("[KMVM Auto-Reflect] ✨ Restored previous window geometry & session!", flush=True)
            # Remove state file so subsequent fresh launches start clean
            os.remove(STATE_FILE)
            return True
        except Exception as e:
            print(f"[KMVM Auto-Reflect] ⚠️ Could not restore state: {e}", flush=True)
            try:
                os.remove(STATE_FILE)
            except Exception:
                pass
            return False


# ==============================================================================
# Supervisor Process Runner
# ==============================================================================

def kill_process_tree(pid: int) -> None:
    """Cleanly kill a process and all its children on Windows."""
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False
            )
        except Exception:
            pass
    else:
        try:
            os.kill(pid, 9)
        except Exception:
            pass


def run_supervisor():
    """
    Supervisor process that runs the Qt application and watches for file changes.
    When a file in kmvm/ or backend/ changes, it automatically restarts the app.
    If the app crashes due to a syntax error, supervisor keeps watching and restarts
    as soon as the developer/AI fixes the error!
    """
    print("=" * 64, flush=True)
    print("  🚀 Khmer Music Video Maker — Live Auto-Reflect Mode", flush=True)
    print("  👁️  Watching: kmvm/ and backend/ for code updates", flush=True)
    print("  ⚡ Any file update will automatically reflect in the app!", flush=True)
    print("  ⌨️  Shortcuts: Press F5 or Ctrl+R inside app to reload anytime", flush=True)
    print("=" * 64, flush=True)

    child_env = os.environ.copy()
    child_env["KMVM_CHILD"] = "1"

    # Command to run child
    child_cmd = [sys.executable, "-m", "kmvm.main", "--child"] + [
        arg for arg in sys.argv[1:] if arg not in ("--watch", "--auto-reflect")
    ]

    mtimes = get_file_mtimes()

    while True:
        # Spawn child
        process = subprocess.Popen(child_cmd, cwd=PROJECT_ROOT, env=child_env)
        print(f"[KMVM Auto-Reflect] ▶️ App process started (PID: {process.pid})", flush=True)

        needs_restart = False
        changed_filename = ""

        # Poll loop
        while process.poll() is None:
            time.sleep(0.4)

            # Check files for modifications
            current_files = get_watched_files()
            for path in current_files:
                try:
                    mtime = os.path.getmtime(path)
                except (OSError, PermissionError):
                    continue

                old_mtime = mtimes.get(path)
                if old_mtime is not None and mtime > old_mtime + 0.1:
                    needs_restart = True
                    rel_path = os.path.relpath(path, PROJECT_ROOT)
                    changed_filename = rel_path
                    mtimes[path] = mtime
                    break

                mtimes[path] = mtime

            if needs_restart:
                print(f"\n[KMVM Auto-Reflect] 🔄 Detected update in: {changed_filename}", flush=True)
                print("[KMVM Auto-Reflect] ⚡ Auto-reloading application now...", flush=True)
                time.sleep(0.25)  # debounce file writes
                kill_process_tree(process.pid)
                try:
                    process.wait(timeout=2.0)
                except Exception:
                    pass
                # Update all mtimes so we don't double trigger
                mtimes = get_file_mtimes()
                break

        if needs_restart:
            # Loop around to restart child
            time.sleep(0.2)
            continue

        # Child exited on its own
        exit_code = process.returncode
        if exit_code == 42:
            # Special code: App requested reload (e.g. F5 key or Reload button)
            print("[KMVM Auto-Reflect] 🔄 Reload requested from within app (F5 / Ctrl+R)", flush=True)
            mtimes = get_file_mtimes()
            time.sleep(0.2)
            continue
        elif exit_code == 0:
            # User cleanly closed the window
            print("[KMVM Auto-Reflect] ✓ Application closed cleanly by user. Exiting supervisor.", flush=True)
            break
        else:
            # Crash or syntax error
            print(f"\n[KMVM Auto-Reflect] ⚠️ App exited with code {exit_code}.", flush=True)
            print("[KMVM Auto-Reflect] 👁️ Still watching for code updates...", flush=True)
            print("[KMVM Auto-Reflect] 💡 Fix code and save — app will auto-restart immediately!\n", flush=True)

            # Wait for file change before trying again
            while True:
                time.sleep(0.5)
                current_files = get_watched_files()
                updated = False
                for path in current_files:
                    try:
                        mtime = os.path.getmtime(path)
                    except (OSError, PermissionError):
                        continue
                    old_mtime = mtimes.get(path)
                    if old_mtime is not None and mtime > old_mtime + 0.1:
                        rel_path = os.path.relpath(path, PROJECT_ROOT)
                        print(f"[KMVM Auto-Reflect] 🔄 Code update detected in {rel_path}! Restarting...", flush=True)
                        mtimes = get_file_mtimes()
                        updated = True
                        time.sleep(0.3)
                        break
                    mtimes[path] = mtime
                if updated:
                    break
