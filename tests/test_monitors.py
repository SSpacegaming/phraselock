"""Tests for monitor selection (pure logic, no Windows or display needed)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import monitors

LEFT = {"device": r"\\.\DISPLAY2", "x": -1920, "y": 0, "w": 1920, "h": 1080, "primary": False}
MAIN = {"device": r"\\.\DISPLAY1", "x": 0, "y": 0, "w": 2560, "h": 1440, "primary": True}
RIGHT = {"device": r"\\.\DISPLAY3", "x": 2560, "y": 0, "w": 1920, "h": 1080, "primary": False}
LAYOUT = [LEFT, MAIN, RIGHT]


class ResolveMonitorTests(unittest.TestCase):
    def test_default_config_uses_primary(self):
        self.assertEqual(config.DEFAULT_CONFIG["lock_screens"], ["primary"])
        self.assertIs(monitors.resolve_monitor("primary", LAYOUT), MAIN)

    def test_empty_or_missing_choice_is_primary(self):
        self.assertIs(monitors.resolve_monitor("", LAYOUT), MAIN)
        self.assertIs(monitors.resolve_monitor(None, LAYOUT), MAIN)

    def test_selects_monitor_by_device_name(self):
        self.assertIs(monitors.resolve_monitor(RIGHT["device"], LAYOUT), RIGHT)
        self.assertIs(monitors.resolve_monitor(LEFT["device"], LAYOUT), LEFT)

    def test_unplugged_monitor_falls_back_to_primary(self):
        self.assertIs(monitors.resolve_monitor(RIGHT["device"], [LEFT, MAIN]), MAIN)

    def test_no_primary_flag_falls_back_to_first(self):
        only = dict(LEFT)
        self.assertIs(monitors.resolve_monitor("primary", [only]), only)

    def test_no_monitor_info_returns_none(self):
        self.assertIsNone(monitors.resolve_monitor("primary", []))

    def test_signature_changes_when_layout_changes(self):
        self.assertNotEqual(monitors.monitors_signature(LAYOUT),
                            monitors.monitors_signature([LEFT, MAIN]))
        self.assertEqual(monitors.monitors_signature(LAYOUT),
                         monitors.monitors_signature(list(LAYOUT)))

    def test_choices_from_cfg_new_old_and_missing_keys(self):
        self.assertEqual(monitors.choices_from_cfg({"lock_screens": ["a", "b"]}), ["a", "b"])
        self.assertEqual(monitors.choices_from_cfg({"lock_screen": "x"}), ["x"])  # legacy key
        self.assertEqual(monitors.choices_from_cfg({}), ["primary"])
        self.assertEqual(monitors.choices_from_cfg({"lock_screens": []}), ["primary"])
        self.assertEqual(monitors.choices_from_cfg({"lock_screens": "all"}), ["all"])

    def test_lock_monitors_primary_only(self):
        panel, covers = monitors.resolve_lock_monitors(["primary"], LAYOUT)
        self.assertIs(panel, MAIN)
        self.assertEqual(covers, [])

    def test_lock_monitors_all(self):
        panel, covers = monitors.resolve_lock_monitors(["all"], LAYOUT)
        self.assertIs(panel, MAIN)
        self.assertEqual(covers, [LEFT, RIGHT])

    def test_lock_monitors_two_without_primary_puts_panel_on_leftmost(self):
        panel, covers = monitors.resolve_lock_monitors([RIGHT["device"], LEFT["device"]], LAYOUT)
        self.assertIs(panel, LEFT)
        self.assertEqual(covers, [RIGHT])

    def test_lock_monitors_primary_plus_other(self):
        panel, covers = monitors.resolve_lock_monitors(["primary", RIGHT["device"]], LAYOUT)
        self.assertIs(panel, MAIN)
        self.assertEqual(covers, [RIGHT])

    def test_lock_monitors_no_duplicates(self):
        panel, covers = monitors.resolve_lock_monitors(["primary", MAIN["device"]], LAYOUT)
        self.assertIs(panel, MAIN)
        self.assertEqual(covers, [])

    def test_lock_monitors_skips_unplugged_and_falls_back(self):
        panel, covers = monitors.resolve_lock_monitors([RIGHT["device"]], [LEFT, MAIN])
        self.assertIs(panel, MAIN)
        self.assertEqual(covers, [])
        panel, covers = monitors.resolve_lock_monitors([RIGHT["device"], LEFT["device"]], [LEFT, MAIN])
        self.assertIs(panel, LEFT)
        self.assertEqual(covers, [])

    def test_lock_monitors_no_info(self):
        self.assertEqual(monitors.resolve_lock_monitors(["all"], []), (None, []))

    def test_label(self):
        self.assertEqual(monitors.monitor_label(MAIN, 2), "Screen 2 - 2560x1440 (primary)")
        self.assertEqual(monitors.monitor_label(RIGHT, 3), "Screen 3 - 1920x1080")

    def test_list_monitors_without_pywin32_is_empty(self):
        # On non-Windows machines win32api is missing: must not raise.
        self.assertIsInstance(monitors.list_monitors(), list)


if __name__ == "__main__":
    unittest.main()
