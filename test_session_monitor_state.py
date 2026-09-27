from datetime import datetime, timedelta, timezone
import importlib.util
import logging
from pathlib import Path
import unittest
from unittest.mock import call, patch


MODULE_PATH = Path(__file__).parent / "common" / "session_monitor.py"


class StopMonitor(BaseException):
    pass


def load_session_monitor():
    spec = importlib.util.spec_from_file_location("session_monitor_under_test", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    with patch.object(logging, "FileHandler", return_value=logging.StreamHandler()):
        spec.loader.exec_module(module)
    return module


class SessionMonitorStateTests(unittest.TestCase):
    def setUp(self):
        self.monitor = load_session_monitor()
        self.start = datetime(2026, 9, 27, 18, 0, tzinfo=timezone.utc)
        self.allowed = {
            "allowed": True,
            "reason": "active_session_live",
            "pause_grace_seconds": 60,
            "container_grace_seconds": 120,
        }
        self.stale = {
            "allowed": False,
            "reason": "launcher_heartbeat_stale",
            "pause_grace_seconds": 60,
            "container_grace_seconds": 120,
        }

    def run_monitor(self, results, times):
        statuses = []

        def record_status(state, reason, message, **kwargs):
            statuses.append((state, reason, kwargs))

        def stop_monitor():
            raise StopMonitor("shutdown requested")

        patches = (
            patch.object(self.monitor, "get_container_exam_context", return_value={"pwn_college_id": "1"}),
            patch.object(self.monitor, "check_active_exam_session_status", side_effect=results),
            patch.object(self.monitor, "get_current_utc_time", side_effect=times),
            patch.object(self.monitor.os.path, "exists", return_value=True),
            patch.object(self.monitor.time, "sleep", return_value=None),
            patch.object(self.monitor, "write_exam_monitor_status", side_effect=record_status),
            patch.object(self.monitor, "mark_session_active"),
            patch.object(self.monitor, "mark_session_paused"),
            patch.object(self.monitor, "check_and_report_duplicate_vscode"),
            patch.object(self.monitor, "check_and_restore_clevel_work_dir", return_value=True),
            patch.object(self.monitor, "broadcast_message"),
            patch.object(self.monitor, "write_container_dead_marker"),
            patch.object(self.monitor, "kill_process_1", side_effect=stop_monitor),
        )
        entered = []
        try:
            for item in patches:
                entered.append(item.start())
            with self.assertRaisesRegex(StopMonitor, "shutdown requested"):
                self.monitor.monitor_active_exam_session()
        finally:
            for item in reversed(patches):
                item.stop()
        return statuses, entered

    def test_warning_keeps_tester_active_then_pauses_and_shuts_down(self):
        times = [self.start + timedelta(seconds=value) for value in (0, 30, 60, 90, 120, 150)]
        statuses, mocks = self.run_monitor(
            [self.allowed, self.stale, self.stale, self.stale, self.stale, self.stale],
            times,
        )

        states = [entry[0] for entry in statuses]
        self.assertEqual(states[:5], ["active", "warning", "warning", "blocked", "blocked"])
        self.assertEqual(states[-1], "blocked")
        mark_active = mocks[6]
        mark_paused = mocks[7]
        kill_process = mocks[12]
        self.assertGreaterEqual(mark_active.call_count, 3)
        mark_paused.assert_called_once()
        kill_process.assert_called_once()

        first_warning = next(entry for entry in statuses if entry[0] == "warning")
        self.assertEqual(first_warning[2]["pause_at"], self.start + timedelta(seconds=90))
        self.assertEqual(first_warning[2]["shutdown_at"], self.start + timedelta(seconds=150))

    def test_unload_immediately_pauses_then_recovery_restores_tester(self):
        times = [self.start + timedelta(seconds=value) for value in (0, 30)]
        statuses = []
        unload_blocked = {
            "allowed": False,
            "monitoring_warning": True,
            "reason": "launcher_page_unloaded",
            "interruption_age_seconds": 0,
            "pause_grace_seconds": 0,
            "container_grace_seconds": 480,
        }

        with (
            patch.object(self.monitor, "get_container_exam_context", return_value={"pwn_college_id": "1"}),
            patch.object(
                self.monitor,
                "check_active_exam_session_status",
                side_effect=[unload_blocked, self.allowed, KeyboardInterrupt()],
            ),
            patch.object(self.monitor, "get_current_utc_time", side_effect=times),
            patch.object(self.monitor.os.path, "exists", return_value=True),
            patch.object(self.monitor.time, "sleep", return_value=None) as sleep,
            patch.object(
                self.monitor,
                "write_exam_monitor_status",
                side_effect=lambda state, reason, message, **kwargs: statuses.append(state),
            ),
            patch.object(self.monitor, "mark_session_active") as mark_active,
            patch.object(self.monitor, "mark_session_paused") as mark_paused,
            patch.object(self.monitor, "check_and_report_duplicate_vscode"),
            patch.object(self.monitor, "check_and_restore_clevel_work_dir", return_value=True),
            patch.object(self.monitor, "broadcast_message"),
        ):
            self.monitor.monitor_active_exam_session()

        self.assertEqual(statuses, ["blocked", "active"])
        mark_paused.assert_called_once()
        mark_active.assert_called_once()
        self.assertEqual(
            sleep.call_args_list,
            [
                call(self.monitor.ACTIVE_EXAM_SESSION_ALERT_CHECK_INTERVAL),
                call(self.monitor.CHECK_INTERVAL),
            ],
        )


if __name__ == "__main__":
    unittest.main()
