import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import backup  # noqa: E402
from config import DEFAULT_CONFIG  # noqa: E402


def write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


STAT = {
    "timestamp": "2026-10-19T09:30:00",
    "rounds": 2,
    "duration_seconds": 14.5,
    "first_try": True,
    "emergency": False,
    "wpm": 61.2,
    "accuracy": 100.0,
}
STREAK = {
    "current_streak": 4,
    "best_streak": 9,
    "last_qualifying_day": "2026-10-19",
    "goal_date": "2026-10-19",
    "goal_progress": 1,
    "xp": 250,
}


class BackupTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = self._tmp.name
        self.src = self._dirs(os.path.join(root, "old_pc"))
        self.dst = self._dirs(os.path.join(root, "new_pc"))
        self.file = os.path.join(root, "backup.json")

    @staticmethod
    def _dirs(folder):
        os.makedirs(folder)
        return {
            "config": os.path.join(folder, "config.json"),
            "stats": os.path.join(folder, "stats.json"),
            "streak": os.path.join(folder, "streak.json"),
        }

    def _paths(self, d):
        return dict(config_path=d["config"], stats_path=d["stats"], streak_path=d["streak"])

    def _export(self, config, include_password=True):
        return backup.export_backup(
            self.file, config, include_password,
            stats_path=self.src["stats"], streak_path=self.src["streak"],
        )

    def _import(self):
        return backup.apply_backup(backup.load_backup(self.file), **self._paths(self.dst))

    def _write_backup(self, **sections):
        data = {"format": backup.BACKUP_FORMAT, "version": 1}
        data.update(sections)
        write_json(self.file, data)

    # ------------------------------------------------------------------

    def test_round_trip_to_a_fresh_pc(self):
        write_json(self.src["stats"], [STAT])
        write_json(self.src["streak"], STREAK)
        config = {**DEFAULT_CONFIG, "theme": "Matrix", "phrases": ["a", "b"], "daily_goal": 3}
        self._export(config)

        self._import()

        saved = read_json(self.dst["config"])
        self.assertEqual(saved["theme"], "Matrix")
        self.assertEqual(saved["phrases"], ["a", "b"])
        self.assertEqual(saved["daily_goal"], 3)
        self.assertEqual(read_json(self.dst["stats"]), [STAT])
        self.assertEqual(read_json(self.dst["streak"]), STREAK)

    def test_export_drops_unknown_keys(self):
        self._export({**DEFAULT_CONFIG, "not_a_setting": 1})
        self.assertNotIn("not_a_setting", read_json(self.file)["config"])

    def test_export_can_leave_the_password_out(self):
        config = {**DEFAULT_CONFIG, "emergency_password_salt": "ab12",
                  "emergency_password_hash": "cd34"}
        self._export(config, include_password=False)
        exported = read_json(self.file)
        self.assertFalse(exported["includes_password"])
        for key in backup.PASSWORD_KEYS:
            self.assertNotIn(key, exported["config"])

    def test_export_with_password_carries_it_over(self):
        config = {**DEFAULT_CONFIG, "emergency_password_salt": "ab12",
                  "emergency_password_hash": "cd34",
                  "emergency_password_iterations": 1000}
        self._export(config)
        self._import()
        saved = read_json(self.dst["config"])
        self.assertEqual(saved["emergency_password_salt"], "ab12")
        self.assertEqual(saved["emergency_password_hash"], "cd34")
        self.assertEqual(saved["emergency_password_iterations"], 1000)

    def test_import_without_password_keeps_the_current_one(self):
        write_json(self.dst["config"], {"emergency_password_salt": "ab12",
                                        "emergency_password_hash": "cd34",
                                        "theme": "Cyber Red"})
        self._export({**DEFAULT_CONFIG, "theme": "Blackout"}, include_password=False)
        self._import()
        saved = read_json(self.dst["config"])
        self.assertEqual(saved["theme"], "Blackout")
        self.assertEqual(saved["emergency_password_hash"], "cd34")

    def test_import_keeps_backup_copies_of_replaced_files(self):
        write_json(self.dst["config"], {"theme": "Cyber Red"})
        write_json(self.dst["stats"], [STAT])
        self._export({**DEFAULT_CONFIG, "theme": "Matrix"})
        saved = self._import()
        self.assertEqual(len(saved), 2)  # streak.json did not exist yet
        for path in saved:
            self.assertTrue(path.endswith(".bak"))
            self.assertTrue(os.path.exists(path))
        old = [p for p in saved if "config.json" in p][0]
        self.assertEqual(read_json(old), {"theme": "Cyber Red"})

    def test_rejects_files_that_are_not_backups(self):
        for content in ("not json", "[]", '{"format": "something-else", "version": 1}'):
            with open(self.file, "w", encoding="utf-8") as f:
                f.write(content)
            with self.assertRaises(backup.BackupError):
                backup.load_backup(self.file)

    def test_rejects_missing_file_and_empty_backup(self):
        with self.assertRaises(backup.BackupError):
            backup.load_backup(os.path.join(self._tmp.name, "nope.json"))
        self._write_backup()
        with self.assertRaises(backup.BackupError):
            backup.load_backup(self.file)

    def test_rejects_newer_versions(self):
        write_json(self.file, {"format": backup.BACKUP_FORMAT, "version": 99, "config": {}})
        with self.assertRaises(backup.BackupError) as ctx:
            backup.load_backup(self.file)
        self.assertIn("newer version", str(ctx.exception))

    def test_accepts_a_utf8_bom(self):
        self._write_backup(config={"theme": "Matrix"})
        with open(self.file, "rb") as f:
            raw = f.read()
        with open(self.file, "wb") as f:
            f.write(b"\xef\xbb\xbf" + raw)
        self.assertEqual(backup.load_backup(self.file).config, {"theme": "Matrix"})

    def test_bad_settings_are_ignored_and_numbers_clamped(self):
        self._write_backup(config={
            "theme": "Matrix",
            "unknown": 1,
            "strict_mode": "yes",            # wrong type
            "daily_goal": True,              # bool is not an int
            "ui_scale": 9999,                # clamped
            "required_repeats": -5,          # clamped
            "schedule_start": "25:99",       # invalid time
            "schedule_days": [0, 9],         # invalid day
            "phrases": ["  ok  ", "", "fine"],
            "panel_color": "not-a-colour-at-all",
            "focus_block_apps": "chrome.exe",
        })
        result = backup.load_backup(self.file)
        cfg = result.config
        self.assertEqual(cfg["theme"], "Matrix")
        self.assertEqual(cfg["ui_scale"], 150)
        self.assertEqual(cfg["required_repeats"], 1)
        self.assertEqual(cfg["phrases"], ["ok", "fine"])
        for key in ("unknown", "strict_mode", "daily_goal", "schedule_start",
                    "schedule_days", "panel_color", "focus_block_apps"):
            self.assertNotIn(key, cfg)
        self.assertTrue(result.warnings)

    def test_incomplete_password_data_is_dropped(self):
        self._write_backup(config={"emergency_password_hash": "cd34",
                                   "emergency_password_salt": "",
                                   "theme": "Matrix"})
        cfg = backup.load_backup(self.file).config
        self.assertEqual(cfg, {"theme": "Matrix"})

    def test_non_hex_password_data_is_dropped(self):
        self._write_backup(config={"emergency_password_hash": "zzzz",
                                   "emergency_password_salt": "ab12"})
        with self.assertRaises(backup.BackupError):  # nothing usable left
            backup.load_backup(self.file)

    def test_missing_local_files_produce_a_warning(self):
        self._write_backup(config={"background_image": r"C:\definitely\missing.png",
                                   "success_sound": "https://example.com/a.wav"})
        warnings = backup.load_backup(self.file).warnings
        self.assertEqual(len(warnings), 1)
        self.assertIn("background_image", warnings[0])

    def test_unreadable_stats_are_skipped_and_the_list_is_capped(self):
        good = [{**STAT, "timestamp": f"2026-01-01T00:{i // 60:02d}:{i % 60:02d}"} for i in range(520)]
        bad = [{"timestamp": 5}, {"timestamp": "nonsense"}, "text",
               {**STAT, "duration_seconds": "fast"}]
        self._write_backup(stats=good + bad)
        stats = backup.load_backup(self.file).stats
        self.assertEqual(len(stats), backup.MAX_STATS_ENTRIES)
        self.assertEqual(stats[-1]["timestamp"], good[-1]["timestamp"])

    def test_bad_streak_values_are_ignored(self):
        self._write_backup(streak={"current_streak": "3", "best_streak": 5,
                                   "last_qualifying_day": "yesterday",
                                   "goal_date": "2026-10-19", "xp": -40})
        streak = backup.load_backup(self.file).streak
        self.assertEqual(streak, {"best_streak": 5, "goal_date": "2026-10-19", "xp": 0})

    def test_sections_missing_from_the_backup_leave_files_untouched(self):
        write_json(self.dst["stats"], [STAT])
        write_json(self.dst["streak"], STREAK)
        self._write_backup(config={"theme": "Matrix"})
        self._import()
        self.assertEqual(read_json(self.dst["stats"]), [STAT])
        self.assertEqual(read_json(self.dst["streak"]), STREAK)

    def test_describe_mentions_what_will_be_imported(self):
        write_json(self.src["stats"], [STAT])
        write_json(self.src["streak"], STREAK)
        self._export(DEFAULT_CONFIG)
        text = backup.describe(backup.load_backup(self.file))
        self.assertIn("Unlock records: 1", text)
        self.assertIn("XP 250", text)


if __name__ == "__main__":
    unittest.main()
