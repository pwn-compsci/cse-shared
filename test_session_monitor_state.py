from datetime import datetime, timedelta, timezone
import importlib.util
import logging
from pathlib import Path
import unittest
from unittest.mock import call, mock_open, patch


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
            "stopped_url": "https://cse240.com/api/exam_session_stopped?reason=launcher_heartbeat_stale",
        }

    def test_practice_exam_skips_all_session_checks(self):
        for flag in ("practice_exam", "is_practice_exam"):
            with (
                self.subTest(flag=flag),
                patch("builtins.open", mock_open(read_data='{"%s": true}' % flag)),
                patch.object(self.monitor, "mark_session_active") as mark_active,
                patch.object(self.monitor, "check_and_restore_clevel_work_dir") as restore,
                patch.object(self.monitor, "get_exam_admin_type") as admin_type,
                patch.object(self.monitor, "active_exam_session_monitor_enabled", return_value=True) as enabled,
                patch.object(self.monitor, "monitor_active_exam_session") as active_monitor,
                patch.object(self.monitor, "check_exam_attendance") as attendance,
            ):
                self.monitor.main()
                mark_active.assert_called_once()
                restore.assert_called_once()
                admin_type.assert_not_called()
                enabled.assert_not_called()
                active_monitor.assert_not_called()
                attendance.assert_not_called()

    def test_regular_exam_still_checks_session_policy(self):
        with (
            patch("builtins.open", mock_open(read_data='{"practice_exam": false}')),
            patch.object(self.monitor, "get_exam_admin_type", return_value="Proctoring"),
            patch.object(self.monitor, "active_exam_session_monitor_enabled", return_value=True),
            patch.object(self.monitor, "monitor_active_exam_session") as active_monitor,
            patch.object(self.monitor, "mark_session_active") as mark_active,
        ):
            self.monitor.main()
            active_monitor.assert_called_once()
            mark_active.assert_not_called()

    def test_cse545_broadcast_uses_challenge_wording(self):
        config = mock_open(read_data='{"course_code": "cse545"}')
        with patch("builtins.open", config), patch.object(self.monitor.glob, "glob", return_value=["/dev/pts/1"]):
            self.monitor.broadcast_message("You cannot get the flag from the tester.")
        config().write.assert_called_once_with("You cannot get the flag from the challenge.")

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
        self.assertEqual(statuses[-1][2]["redirect_url"], self.stale["stopped_url"])

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
