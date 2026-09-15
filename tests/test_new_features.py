import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock

# Ensure repo root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock PyQt5 and requests if not installed in current environment
try:
    import PyQt5
except ImportError:
    pyqt5_mock = MagicMock()
    sys.modules["PyQt5"] = pyqt5_mock
    sys.modules["PyQt5.QtCore"] = pyqt5_mock
    sys.modules["PyQt5.QtGui"] = pyqt5_mock
    sys.modules["PyQt5.QtWidgets"] = pyqt5_mock
    # Give QThread a real base class for subclassing
    class MockQThread:
        def __init__(self, *args, **kwargs): pass
        def start(self): pass
        def stop(self): pass
        def wait(self, *args): pass
    pyqt5_mock.QThread = MockQThread
    pyqt5_mock.pyqtSignal = lambda *args, **kwargs: MagicMock()

try:
    import requests
except ImportError:
    sys.modules["requests"] = MagicMock()

try:
    import platformdirs
except ImportError:
    sys.modules["platformdirs"] = MagicMock()

try:
    import structlog
except ImportError:
    sys.modules["structlog"] = MagicMock()


from source.xzen_engine.compressibility import (
    analyze_directory_compressibility,
    calculate_savings_preview,
)
from source.xzen_engine.constants import PRECOMPRESSED_MEDIA_EXTENSIONS
from source.xzen_engine.workers import CompactWorker
from source.xzen_engine.auto_monitor import AutoCompressMonitor
from source.xzen_engine.background_controller import BackgroundRunController


class TestCompressibilityIndicators(unittest.TestCase):
    def test_green_loose_assets(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create loose textures, text files, raw audio
            for i in range(10):
                with open(os.path.join(temp_dir, f"texture_{i}.dds"), "wb") as f:
                    f.write(b"0" * 1024 * 100)  # 100 KB
                with open(os.path.join(temp_dir, f"script_{i}.json"), "w") as f:
                    f.write('{"key": "value"}' * 500)
                with open(os.path.join(temp_dir, f"audio_{i}.wav"), "wb") as f:
                    f.write(b"\x00" * 1024 * 50)

            result = analyze_directory_compressibility(temp_dir)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["traffic_light"], "green")
            self.assertIn("High Savings", result["rating_text"])
            self.assertGreater(result["estimated_savings_ratio"], 0.20)

            game = {"name": "Loose Game", "path": temp_dir, "size": 1024 * 1024 * 100}
            light, badge, preview = calculate_savings_preview(game, result)
            self.assertEqual(light, "green")
            self.assertIn("Saves ~", preview)

    def test_red_packed_archives(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create packed archives (.pak, .vpk, .zip)
            for i in range(5):
                with open(os.path.join(temp_dir, f"data_{i}.pak"), "wb") as f:
                    f.write(b"P" * 1024 * 500)  # 500 KB
                with open(os.path.join(temp_dir, f"archive_{i}.zip"), "wb") as f:
                    f.write(b"Z" * 1024 * 500)

            result = analyze_directory_compressibility(temp_dir)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["traffic_light"], "red")
            self.assertIn("Low Yield", result["rating_text"])


class TestMediaExclusions(unittest.TestCase):
    def test_precompressed_media_filtering(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create a mix of compressible files and media files
            with open(os.path.join(temp_dir, "game.exe"), "wb") as f:
                f.write(b"E" * 1000)
            with open(os.path.join(temp_dir, "data.txt"), "wb") as f:
                f.write(b"T" * 1000)
            with open(os.path.join(temp_dir, "intro.mp4"), "wb") as f:
                f.write(b"M" * 5000)
            with open(os.path.join(temp_dir, "music.mp3"), "wb") as f:
                f.write(b"S" * 5000)

            # Test Compress mode (should bypass media extensions)
            worker = CompactWorker(
                target_path=temp_dir,
                action_label="Compressing",
                compression_algorithm="LZX",
            )
            files = worker.collect_files()
            collected_names = [os.path.basename(path) for path, _ in files]
            self.assertIn("game.exe", collected_names)
            self.assertIn("data.txt", collected_names)
            self.assertNotIn("intro.mp4", collected_names)
            self.assertNotIn("music.mp3", collected_names)


class MockHost:
    def __init__(self, games):
        self.games = games
        self.busy = False
        self.background_queue = []
        self.background_total = 0
        self.background_current_index = None
        self.background_status_text = ""
        self.background_compress_active = False
        self.background_compress_paused = False
        self.background_compress_cancel_requested = False
        self.app_settings = {"worker_mode": "auto", "worker_count": 4}
        self.logs = []

    def log(self, msg):
        self.logs.append(msg)

    def selected_compression_algorithm(self):
        return "LZX"

    def game_detection_paths(self):
        return []

    def set_buttons_enabled(self, enabled):
        pass

    def update_dashboard(self):
        pass

    def reset_background_progress_bars(self, *args):
        pass

    def manual_path_allowed(self, path):
        return True, ""

    def update_background_compact_active_files(self, *args):
        pass

    def update_background_compact_worker_usage(self, *args):
        pass

    def update_background_compact_pause_state(self, *args):
        pass

    def refresh_grid(self, *args, **kwargs):
        pass

    def update_background_controls(self, *args, **kwargs):
        pass

    def update_background_worker_usage(self, *args, **kwargs):
        pass

    def update_background_pause_state(self, *args, **kwargs):
        pass

    def update_background_active_files(self, *args, **kwargs):
        pass

    def update_background_compress_progress(self, *args, **kwargs):
        pass

    def on_background_compress_done(self, *args, **kwargs):
        pass

    def on_background_decompress_done(self, *args, **kwargs):
        pass

    def retain_worker_until_finished(self, worker):
        pass


class TestBatchQueueOperations(unittest.TestCase):
    def test_batch_compress_queue(self):
        games = [
            {"name": "Game A", "path": "/fake/a", "status": "Normal", "compressed_size": 0},
            {"name": "Game B", "path": "/fake/b", "status": "Compressed", "compressed_size": 1000},
            {"name": "Game C", "path": "/fake/c", "status": "Normal", "compressed_size": 0},
        ]
        host = MockHost(games)
        controller = BackgroundRunController(host)

        # Start batch for games 0 and 2
        controller.start_batch_compress_queue([0, 2])
        self.assertEqual(host.background_total, 2)
        self.assertEqual(len(host.background_queue), 1)  # 1 remaining because 1 is popped to start
        self.assertTrue(host.busy)


class TestAutoCompressMonitor(unittest.TestCase):
    def test_monitor_scan_known_folders(self):
        with tempfile.TemporaryDirectory() as watch_root:
            game_folder = os.path.join(watch_root, "AwesomeGame")
            os.makedirs(game_folder, exist_ok=True)

            existing_games = []
            triggered_candidates = []

            monitor = AutoCompressMonitor(
                get_watched_paths_fn=lambda: [watch_root],
                get_existing_games_fn=lambda: existing_games,
                trigger_compress_fn=lambda c: triggered_candidates.append(c),
                is_busy_fn=lambda: False,
                poll_interval=1,
            )

            known = monitor._scan_known_folders()
            self.assertIn(os.path.normpath(game_folder).lower(), known)

    def test_calculate_savings_preview_for_compressed(self):
        game = {
            "name": "Compressed Game",
            "path": "/fake/game",
            "size": 100 * 1024 * 1024 * 1024,
            "compressed_size": 60 * 1024 * 1024 * 1024,
            "status": "Compressed",
        }
        light, badge, preview = calculate_savings_preview(game)
        self.assertEqual(light, "green")
        self.assertEqual(badge, "Compressed")
        self.assertIn("Saved", preview)


if __name__ == "__main__":
    unittest.main()

