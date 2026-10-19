"""Tests for the pause (disable for X minutes) logic and the hotkey text parser."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import hotkeys


class PauseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "pause.json")
        patcher = mock.patch.object(config, "log", lambda *_a, **_k: None)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_not_paused_when_there_is_no_pause_file(self):
        self.assertEqual(config.pause_remaining_seconds(now=1000, path=self.path), 0)

    def test_pause_counts_down_and_ends(self):
        config.start_pause(5, now=1000, path=self.path)
        self.assertEqual(config.pause_remaining_seconds(now=1000, path=self.path), 300)
        self.assertEqual(config.pause_remaining_seconds(now=1299, path=self.path), 1)
        self.assertEqual(config.pause_remaining_seconds(now=1300, path=self.path), 0)
        self.assertEqual(config.pause_remaining_seconds(now=5000, path=self.path), 0)

    def test_pause_survives_a_restart_because_it_is_stored_as_a_timestamp(self):
        until = config.start_pause(10, now=2000, path=self.path)
        self.assertEqual(until, 2600)
        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), {"until": 2600})

    def test_minutes_are_kept_in_range(self):
        config.start_pause(0, now=0, path=self.path)
        self.assertEqual(config.pause_remaining_seconds(now=0, path=self.path), 60)
        config.start_pause(-5, now=0, path=self.path)
        self.assertEqual(config.pause_remaining_seconds(now=0, path=self.path), 60)
        config.start_pause(10 ** 6, now=0, path=self.path)
        self.assertEqual(config.pause_remaining_seconds(now=0, path=self.path),
                         config.MAX_PAUSE_MINUTES * 60)
        config.start_pause("junk", now=0, path=self.path)
        self.assertEqual(config.pause_remaining_seconds(now=0, path=self.path), 15 * 60)

    def test_a_pause_in_the_far_future_is_capped(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump({"until": 10 ** 12}, f)
        self.assertEqual(config.pause_remaining_seconds(now=0, path=self.path),
                         config.MAX_PAUSE_MINUTES * 60)

    def test_broken_pause_files_mean_not_paused(self):
        for content in ("", "not json", "[]", '{"until": "soon"}', '{"other": 1}'):
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(content)
            self.assertEqual(config.pause_remaining_seconds(now=0, path=self.path), 0, content)

    def test_end_pause_resumes_and_is_safe_to_repeat(self):
        config.start_pause(30, now=0, path=self.path)
        config.end_pause(path=self.path)
        self.assertEqual(config.pause_remaining_seconds(now=1, path=self.path), 0)
        config.end_pause(path=self.path)          # nothing to remove: no error

    def test_toggle_pauses_then_resumes(self):
        self.assertTrue(config.toggle_pause(15, now=100, path=self.path))
        self.assertEqual(config.pause_remaining_seconds(now=100, path=self.path), 900)
        self.assertFalse(config.toggle_pause(15, now=200, path=self.path))
        self.assertEqual(config.pause_remaining_seconds(now=200, path=self.path), 0)

    def test_toggle_after_the_pause_ran_out_pauses_again(self):
        config.start_pause(1, now=0, path=self.path)
        self.assertTrue(config.toggle_pause(15, now=500, path=self.path))

    def test_pause_is_not_stored_in_the_normal_config(self):
        self.assertNotEqual(os.path.basename(config.PAUSE_PATH), os.path.basename(config.CONFIG_PATH))
        self.assertEqual(os.path.dirname(config.PAUSE_PATH), os.path.dirname(config.CONFIG_PATH))

    def test_defaults_have_the_hotkey_off(self):
        self.assertEqual(config.DEFAULT_CONFIG["pause_hotkey"], "")
        self.assertEqual(config.DEFAULT_CONFIG["pause_minutes"], 15)


class HotkeyTests(unittest.TestCase):
    def test_common_combinations(self):
        self.assertEqual(hotkeys.parse_hotkey("Ctrl+Alt+P"), (hotkeys.MOD_CONTROL | hotkeys.MOD_ALT, ord("P")))
        self.assertEqual(hotkeys.parse_hotkey("Win+Space"), (hotkeys.MOD_WIN, 0x20))
        self.assertEqual(hotkeys.parse_hotkey("Ctrl+Shift+F12"), (hotkeys.MOD_CONTROL | hotkeys.MOD_SHIFT, 0x7B))
        self.assertEqual(hotkeys.parse_hotkey("Alt+7"), (hotkeys.MOD_ALT, ord("7")))

    def test_case_spaces_and_alias_names_are_accepted(self):
        self.assertEqual(hotkeys.parse_hotkey(" ctrl + ALT + p "), hotkeys.parse_hotkey("Ctrl+Alt+P"))
        self.assertEqual(hotkeys.parse_hotkey("Control+Windows+x"), (hotkeys.MOD_CONTROL | hotkeys.MOD_WIN, ord("X")))

    def test_function_keys_cover_f1_to_f24(self):
        self.assertEqual(hotkeys.parse_hotkey("Ctrl+F1")[1], 0x70)
        self.assertEqual(hotkeys.parse_hotkey("Ctrl+F24")[1], 0x87)
        self.assertIsNone(hotkeys.parse_hotkey("Ctrl+F25"))
        self.assertIsNone(hotkeys.parse_hotkey("Ctrl+F0"))

    def test_unusable_hotkeys_are_rejected(self):
        for bad in ("", None, "P", "Ctrl", "Ctrl+", "Shift+P", "Ctrl+Alt", "Ctrl+A+B",
                    "Ctrl+Banana", "Ctrl++", "Alt+Alt"):
            self.assertIsNone(hotkeys.parse_hotkey(bad), bad)

    def test_normalize_gives_one_canonical_spelling(self):
        self.assertEqual(hotkeys.normalize_hotkey(" ctrl + alt + p "), "Ctrl+Alt+P")
        self.assertEqual(hotkeys.normalize_hotkey("shift+ctrl+f5"), "Ctrl+Shift+F5")
        self.assertEqual(hotkeys.normalize_hotkey("win+space"), "Win+Space")
        self.assertEqual(hotkeys.normalize_hotkey("alt+pagedown"), "Alt+PageDown")
        self.assertEqual(hotkeys.normalize_hotkey("Ctrl+9"), "Ctrl+9")
        self.assertEqual(hotkeys.normalize_hotkey("nonsense"), "")

    def test_normalized_text_parses_to_the_same_hotkey(self):
        for text in ("ctrl+alt+p", "Win+shift+F10", "alt+insert", "CTRL+ALT+END"):
            self.assertEqual(hotkeys.parse_hotkey(hotkeys.normalize_hotkey(text)),
                             hotkeys.parse_hotkey(text), text)


if __name__ == "__main__":
    unittest.main()
