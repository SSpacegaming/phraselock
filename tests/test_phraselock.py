"""Unit tests for the pure logic: schedule, text normalisation, streaks, stats and phrase picking."""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import tempfile
import unittest
from datetime import date, datetime
from unittest import mock

import config
import phrases
import stats


class WpmAccuracyTests(unittest.TestCase):
    def test_wpm_basic(self):
        # 50 chars in 30s = 10 words in 0.5 min = 20 WPM
        self.assertEqual(stats.compute_wpm(50, 30), 20.0)

    def test_wpm_zero_inputs(self):
        self.assertEqual(stats.compute_wpm(0, 30), 0.0)
        self.assertEqual(stats.compute_wpm(50, 0), 0.0)
        self.assertEqual(stats.compute_wpm(-1, 30), 0.0)
        self.assertEqual(stats.compute_wpm("junk", 30), 0.0)

    def test_accuracy_basic(self):
        self.assertEqual(stats.compute_accuracy(3, 4), 75.0)
        self.assertEqual(stats.compute_accuracy(0, 4), 0.0)
        self.assertEqual(stats.compute_accuracy(4, 4), 100.0)

    def test_accuracy_zero_rounds(self):
        self.assertEqual(stats.compute_accuracy(0, 0), 0.0)


class RecordStatTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "stats.json")
        self.patch = mock.patch.object(stats, "STATS_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def test_new_fields_written(self):
        stats.record_stat(3, 20.0, first_try=True, emergency=False,
                          chars_typed=150, correct_rounds=3)
        with open(self.path) as f:
            data = json.load(f)
        entry = data[-1]
        self.assertEqual(entry["wpm"], 90.0)   # (150/5)/(20/60) = 90
        self.assertEqual(entry["accuracy"], 100.0)

    def test_old_callers_still_work(self):
        stats.record_stat(3, 20.0)   # no new kwargs
        with open(self.path) as f:
            data = json.load(f)
        self.assertNotIn("wpm", data[-1])
        self.assertNotIn("accuracy", data[-1])


class WeeklySeriesTests(unittest.TestCase):
    def test_empty_returns_seven_buckets(self):
        today = date(2024, 3, 10)   # Sunday
        series = stats.weekly_series([], days=7, today=today)
        self.assertEqual(len(series), 7)
        self.assertEqual(series[-1]["date"], "2024-03-10")
        self.assertEqual(series[0]["date"], "2024-03-04")
        self.assertTrue(all(b["total"] == 0 for b in series))

    def test_counts_and_averages(self):
        today = date(2024, 3, 10)
        runs = [
            {"timestamp": "2024-03-08T12:00:00", "first_try": True,  "emergency": False, "wpm": 30, "accuracy": 100},
            {"timestamp": "2024-03-08T18:00:00", "first_try": False, "emergency": False, "wpm": 50, "accuracy": 80},
            {"timestamp": "2024-03-10T09:00:00", "first_try": True,  "emergency": False, "wpm": 40, "accuracy": 90},
            {"timestamp": "2024-03-05T09:00:00", "first_try": True,  "emergency": True,  "wpm": 25, "accuracy": 50},
            {"timestamp": "2024-02-01T09:00:00", "first_try": True,  "emergency": False},  # outside window
        ]
        series = stats.weekly_series(runs, days=7, today=today)
        by_date = {b["date"]: b for b in series}

        self.assertEqual(by_date["2024-03-08"]["total"], 2)
        self.assertEqual(by_date["2024-03-08"]["first_try"], 1)
        self.assertAlmostEqual(by_date["2024-03-08"]["wpm"], 40.0, places=1)
        self.assertAlmostEqual(by_date["2024-03-08"]["accuracy"], 90.0, places=1)

        # Emergency unlock still counts toward total but not first_try.
        self.assertEqual(by_date["2024-03-05"]["total"], 1)
        self.assertEqual(by_date["2024-03-05"]["first_try"], 0)

        # Old entry outside window is ignored.
        self.assertEqual(sum(b["total"] for b in series), 4)


class PhrasePickingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "phrase_state.json")
        self.patch = mock.patch.object(phrases, "PHRASE_STATE_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _items(self):
        return [
            {"text": "A", "category": "x", "difficulty": "easy"},
            {"text": "B", "category": "x", "difficulty": "normal"},
            {"text": "C", "category": "x", "difficulty": "hard"},
            {"text": "D", "category": "x", "difficulty": "extreme"},
        ]

    def test_single_phrase_library_is_exempt(self):
        items = [{"text": "solo", "category": "x", "difficulty": "normal"}]
        for _ in range(20):
            self.assertEqual(phrases.pick_phrase(items), "solo")

    def test_avoids_previous_within_session(self):
        for _ in range(50):
            got = phrases.pick_phrase(self._items(), previous="A")
            self.assertNotEqual(got, "A")

    def test_avoids_last_session_on_first_pick(self):
        phrases.remember_last_phrase("C")
        for _ in range(50):
            got = phrases.pick_phrase(self._items(), previous=None)
            self.assertNotEqual(got, "C")

    def test_falls_back_when_only_one_candidate_left(self):
        items = [{"text": "A", "category": "x", "difficulty": "normal"},
                 {"text": "B", "category": "x", "difficulty": "normal"}]
        phrases.remember_last_phrase("A")
        # previous=B and last_session=A → only candidate allowed is A? No,
        # the constraint 'avoid last session' yields [B], then 'avoid previous'
        # yields [] so we fall back to items. Must not raise.
        got = phrases.pick_phrase(items, previous="B")
        self.assertIn(got, {"A", "B"})

    def test_weighting_favours_hard(self):
        items = self._items()
        picks = [phrases.pick_phrase(items, cfg={"difficulty_weighting": True})
                 for _ in range(2000)]
        # hard has weight 3, extreme 4, normal 2, easy 1 — hard+extreme >= easy.
        hard_like = sum(1 for p in picks if p in ("C", "D"))
        easy = picks.count("A")
        self.assertGreater(hard_like, easy * 2)

    def test_no_weighting_is_roughly_uniform(self):
        items = self._items()
        picks = [phrases.pick_phrase(items, cfg={"difficulty_weighting": False})
                 for _ in range(4000)]
        for text in "ABCD":
            share = picks.count(text) / len(picks)
            self.assertGreater(share, 0.15)
            self.assertLess(share, 0.35)


class WithinScheduleTests(unittest.TestCase):
    # 2024-03-04 is a Monday, 03-05 Tuesday, 03-10 Sunday, 03-11 Monday.
    MON, TUE, SUN, NEXT_MON = 4, 5, 10, 11

    @staticmethod
    def at(day, hour, minute=0):
        return datetime(2024, 3, day, hour, minute)

    @staticmethod
    def cfg(**overrides):
        base = {"schedule_enabled": True, "schedule_days": list(range(7)),
                "schedule_start": "09:00", "schedule_end": "17:00"}
        base.update(overrides)
        return base

    def test_disabled_schedule_is_always_active(self):
        cfg = self.cfg(schedule_enabled=False, schedule_days=[])
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.MON, 3)))

    def test_daytime_window(self):
        cfg = self.cfg()
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.MON, 12)))
        self.assertFalse(config.within_schedule(cfg, now=self.at(self.MON, 8, 59)))
        self.assertFalse(config.within_schedule(cfg, now=self.at(self.MON, 17, 1)))

    def test_window_edges_are_inclusive(self):
        cfg = self.cfg()
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.MON, 9)))
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.MON, 17)))

    def test_day_filter(self):
        cfg = self.cfg(schedule_days=[0])  # Monday only
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.MON, 12)))
        self.assertFalse(config.within_schedule(cfg, now=self.at(self.TUE, 12)))

    def test_empty_day_list_means_every_day(self):
        cfg = self.cfg(schedule_days=[])
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.SUN, 12)))

    def test_overnight_window_before_midnight_uses_today(self):
        cfg = self.cfg(schedule_start="22:00", schedule_end="06:00", schedule_days=[0])
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.MON, 23)))
        self.assertFalse(config.within_schedule(cfg, now=self.at(self.TUE, 23)))

    def test_overnight_window_after_midnight_uses_previous_day(self):
        cfg = self.cfg(schedule_start="22:00", schedule_end="06:00", schedule_days=[0])
        # Tuesday 01:00 belongs to Monday's window; Monday 01:00 to Sunday's.
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.TUE, 1)))
        self.assertFalse(config.within_schedule(cfg, now=self.at(self.MON, 1)))

    def test_overnight_window_wraps_the_week(self):
        cfg = self.cfg(schedule_start="22:00", schedule_end="06:00", schedule_days=[6])
        # Sunday night runs into Monday morning.
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.NEXT_MON, 1)))

    def test_overnight_window_is_inactive_during_the_day(self):
        cfg = self.cfg(schedule_start="22:00", schedule_end="06:00")
        self.assertFalse(config.within_schedule(cfg, now=self.at(self.MON, 12)))

    def test_invalid_times_fail_open(self):
        cfg = self.cfg(schedule_start="nope")
        self.assertTrue(config.within_schedule(cfg, now=self.at(self.MON, 3)))


class NormalizeTests(unittest.TestCase):
    def test_strips_surrounding_whitespace(self):
        self.assertEqual(config._normalize("  hello \n", False), "hello")

    def test_inner_spaces_are_kept(self):
        self.assertEqual(config._normalize("a  b", True), "a  b")

    def test_case_sensitive_by_default(self):
        self.assertNotEqual(config._normalize("Hello", False), config._normalize("hello", False))

    def test_case_insensitive_folds_case(self):
        self.assertEqual(config._normalize("HeLLo", True), "hello")

    def test_case_insensitive_strips_accents(self):
        self.assertEqual(config._normalize("\u00c9l\u00e9phant \u00c7a", True), "elephant ca")

    def test_accents_are_kept_when_case_sensitive(self):
        self.assertEqual(config._normalize("\u00e9", False), "\u00e9")

    def test_composed_and_decomposed_accents_match_when_insensitive(self):
        self.assertEqual(config._normalize("e\u0301", True), config._normalize("\u00e9", True))


class StreakTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "streak.json")
        self.patch = mock.patch.object(stats, "STREAK_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _data(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)

    def test_no_file_means_no_streak(self):
        self.assertEqual(stats.get_streak(today="2024-03-04"), (0, 0))

    def test_first_qualifying_day_starts_at_one(self):
        self.assertEqual(stats.update_streak(True, today="2024-03-04"), 1)
        self.assertEqual(stats.get_streak(today="2024-03-04"), (1, 1))

    def test_consecutive_days_extend_the_streak(self):
        for expected, day in enumerate(("2024-03-04", "2024-03-05", "2024-03-06"), 1):
            self.assertEqual(stats.update_streak(True, today=day), expected)
        self.assertEqual(stats.get_streak(today="2024-03-06"), (3, 3))

    def test_same_day_counts_once(self):
        self.assertEqual(stats.update_streak(True, today="2024-03-04"), 1)
        self.assertEqual(stats.update_streak(True, today="2024-03-04"), 1)
        self.assertEqual(stats.get_streak(today="2024-03-04"), (1, 1))

    def test_gap_resets_the_streak_but_keeps_the_best(self):
        for day in ("2024-03-04", "2024-03-05", "2024-03-06"):
            stats.update_streak(True, today=day)
        self.assertEqual(stats.update_streak(True, today="2024-03-09"), 1)
        self.assertEqual(stats.get_streak(today="2024-03-09"), (1, 3))

    def test_a_day_with_a_typo_does_not_extend_the_streak(self):
        stats.update_streak(True, today="2024-03-04")
        self.assertEqual(stats.update_streak(False, today="2024-03-05"), 1)
        self.assertEqual(self._data()["last_qualifying_day"], "2024-03-04")
        # ...so by the 6th it counts as broken, while the best is remembered.
        self.assertEqual(stats.get_streak(today="2024-03-06"), (0, 1))

    def test_streak_survives_until_the_end_of_the_next_day(self):
        stats.update_streak(True, today="2024-03-04")
        self.assertEqual(stats.get_streak(today="2024-03-05"), (1, 1))
        self.assertEqual(stats.get_streak(today="2024-03-06"), (0, 1))

    def test_month_boundary_in_a_leap_year(self):
        for day in ("2024-02-28", "2024-02-29", "2024-03-01"):
            streak = stats.update_streak(True, today=day)
        self.assertEqual(streak, 3)

    def test_year_boundary(self):
        for day in ("2023-12-30", "2023-12-31", "2024-01-01"):
            streak = stats.update_streak(True, today=day)
        self.assertEqual(streak, 3)

    def test_corrupt_file_does_not_break_the_streak(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(stats.get_streak(today="2024-03-04"), (0, 0))
        self.assertEqual(stats.update_streak(True, today="2024-03-04"), 1)

    def test_valid_json_that_is_not_an_object_is_ignored(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write("[]")
        self.assertEqual(stats.get_streak(today="2024-03-04"), (0, 0))
        self.assertEqual(stats.update_streak(True, today="2024-03-04"), 1)

    def test_streak_and_xp_share_one_file_without_clobbering(self):
        stats.update_streak(True, today="2024-03-04")
        stats.add_progress(50, successful=True)
        data = self._data()
        self.assertEqual((data["current_streak"], data["xp"], data["goal_progress"]), (1, 50, 1))
        stats.update_streak(True, today="2024-03-05")
        data = self._data()
        self.assertEqual((data["current_streak"], data["xp"]), (2, 50))


class RecordStatAccuracyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "stats.json")
        self.patch = mock.patch.object(stats, "STATS_PATH", self.path)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _last(self):
        with open(self.path, encoding="utf-8") as f:
            return json.load(f)[-1]

    def test_accuracy_counts_every_submission(self):
        # 3 rounds needed, reset on typo: 2 right, 1 wrong, then 3 right
        # = 5 correct out of 6 submissions.
        stats.record_stat(3, 30.0, first_try=False, chars_typed=100,
                          correct_rounds=5, submissions=6)
        self.assertEqual(self._last()["accuracy"], 83.3)

    def test_accuracy_is_never_above_100(self):
        stats.record_stat(3, 30.0, chars_typed=100, correct_rounds=3, submissions=3)
        self.assertEqual(self._last()["accuracy"], 100.0)

    def test_emergency_unlock_records_no_speed_or_accuracy(self):
        stats.record_stat(1, 5.0, first_try=False, emergency=True,
                          chars_typed=0, correct_rounds=None, submissions=0)
        entry = self._last()
        self.assertNotIn("wpm", entry)
        self.assertNotIn("accuracy", entry)


class ConfigHelperTests(unittest.TestCase):
    def test_save_json_creates_parent_dir_and_leaves_no_temp_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "data.json")
            config.save_json(path, {"a": 1})
            with open(path, encoding="utf-8") as f:
                self.assertEqual(json.load(f), {"a": 1})
            self.assertFalse(os.path.exists(path + ".tmp"))

    def test_self_command_from_source_runs_phrase_lock_py(self):
        command, cwd = config.self_command("--lock")
        self.assertEqual(command, [sys.executable, config.ENTRY_SCRIPT, "--lock"])
        self.assertTrue(config.ENTRY_SCRIPT.endswith("phrase_lock.py"))
        self.assertEqual(cwd, os.path.dirname(config.ENTRY_SCRIPT))

    def test_self_command_when_frozen_runs_the_exe(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            command, cwd = config.self_command("--focus-session")
        self.assertEqual(command, [sys.executable, "--focus-session"])
        self.assertEqual(cwd, os.path.dirname(sys.executable))


if __name__ == "__main__":
    unittest.main()