from __future__ import annotations

import os
import time
from typing import Callable, Dict, List, Set
from PyQt5.QtCore import QThread, pyqtSignal

from .constants import (
    DEFAULT_AUTO_COMPRESS_MONITOR,
    MONITOR_IDLE_SECONDS_REQUIRED,
    MONITOR_POLL_INTERVAL_SECONDS,
)
from .system import detect_game_activity


class AutoCompressMonitor(QThread):
    """
    Lightweight background monitor that watches game launcher installations
    (Steam, Epic Games, GOG, etc.) for newly registered or completed game downloads
    and automatically schedules LZX compression when the device is idle.
    """
    log = pyqtSignal(str)
    new_game_detected = pyqtSignal(str, str)  # name, path
    auto_compress_triggered = pyqtSignal(str, str)  # name, path

    def __init__(
        self,
        get_watched_paths_fn: Callable[[], List[str]],
        get_existing_games_fn: Callable[[], List[Dict]],
        trigger_compress_fn: Callable[[Dict], bool],
        is_busy_fn: Callable[[], bool],
        poll_interval: int = MONITOR_POLL_INTERVAL_SECONDS,
        idle_seconds_required: int = MONITOR_IDLE_SECONDS_REQUIRED,
    ):
        super().__init__()
        self.get_watched_paths_fn = get_watched_paths_fn
        self.get_existing_games_fn = get_existing_games_fn
        self.trigger_compress_fn = trigger_compress_fn
        self.is_busy_fn = is_busy_fn
        self.poll_interval = poll_interval
        self.idle_seconds_required = idle_seconds_required

        self.running = True
        self.enabled = DEFAULT_AUTO_COMPRESS_MONITOR
        self.known_folders: Set[str] = set()
        self.pending_auto_compress: List[Dict] = []
        self._initial_scan_done = False

    def set_enabled(self, enabled: bool):
        self.enabled = bool(enabled)
        if self.enabled:
            self.log.emit("Auto-Compress Background Monitor enabled.")
        else:
            self.log.emit("Auto-Compress Background Monitor paused.")

    def stop(self):
        self.running = False
        self.wait(2000)

    def _scan_known_folders(self) -> Set[str]:
        current_folders = set()
        try:
            for game in self.get_existing_games_fn():
                path = game.get("path", "")
                if path and os.path.exists(path):
                    current_folders.add(os.path.normpath(path).lower())
        except Exception:
            pass

        try:
            for root_path in self.get_watched_paths_fn():
                if not root_path or not os.path.isdir(root_path):
                    continue
                with os.scandir(root_path) as entries:
                    for entry in entries:
                        if entry.is_dir(follow_symlinks=False):
                            current_folders.add(os.path.normpath(entry.path).lower())
        except Exception:
            pass

        return current_folders

    def run(self):
        # Initial baseline scan
        self.known_folders = self._scan_known_folders()
        self._initial_scan_done = True

        while self.running:
            try:
                time.sleep(self.poll_interval)
                if not self.running or not self.enabled:
                    continue

                # Check for new directories
                current_folders = self._scan_known_folders()
                new_folders = current_folders - self.known_folders

                if new_folders:
                    for folder in new_folders:
                        folder_name = os.path.basename(folder)
                        self.log.emit(f"Auto-Monitor: New game directory detected: {folder_name}")
                        self.new_game_detected.emit(folder_name, folder)
                        self.pending_auto_compress.append({
                            "name": folder_name,
                            "path": folder,
                            "detected_time": time.time(),
                        })
                    self.known_folders = current_folders

                # If we have pending auto-compression candidates
                if self.pending_auto_compress:
                    if self.is_busy_fn():
                        continue

                    # Check device idle status
                    game_active, game_name, idle_seconds, _ = detect_game_activity()
                    if game_active:
                        continue

                    if idle_seconds >= self.idle_seconds_required or os.name != "nt":
                        # Pick the oldest pending candidate whose folder size has stabilized
                        candidate = self.pending_auto_compress.pop(0)
                        folder_path = candidate.get("path", "")
                        if os.path.isdir(folder_path):
                            self.log.emit(
                                f"Auto-Monitor: Device is idle ({int(idle_seconds)}s). "
                                f"Triggering background LZX auto-compression for '{candidate.get('name')}'."
                            )
                            self.auto_compress_triggered.emit(candidate.get("name"), folder_path)
                            self.trigger_compress_fn(candidate)

            except Exception as exc:
                self.log.emit(f"Auto-Monitor error: {exc}")
