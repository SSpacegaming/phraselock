"""Tests for the background image list and random pick (no Windows needed)."""
import os
import random
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import media


class BackgroundSourcesTests(unittest.TestCase):
    def test_legacy_single_image_is_used_when_list_is_missing(self):
        self.assertEqual(media.background_sources({"background_image": "a.png"}), ["a.png"])
        self.assertEqual(media.background_sources({"background_images": None, "background_image": "a.png"}), ["a.png"])

    def test_list_takes_precedence_over_legacy_key(self):
        cfg = {"background_images": ["b.png", "c.png"], "background_image": "a.png"}
        self.assertEqual(media.background_sources(cfg), ["b.png", "c.png"])

    def test_empty_list_means_no_image(self):
        self.assertEqual(media.background_sources({"background_images": [], "background_image": "a.png"}), [])

    def test_nothing_configured(self):
        self.assertEqual(media.background_sources({}), [])
        self.assertEqual(media.background_sources({"background_image": ""}), [])

    def test_blanks_and_duplicates_are_dropped_and_values_stripped(self):
        cfg = {"background_images": [" a.png ", "", None, "a.png", "b.png"]}
        self.assertEqual(media.background_sources(cfg), ["a.png", "b.png"])

    def test_a_plain_string_is_accepted(self):
        self.assertEqual(media.background_sources({"background_images": "a.png"}), ["a.png"])


class ChooseBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.ok = lambda p: True

    def run_choose(self, sources, previous=None, seed=0, exists=None, resolve=None):
        return media.choose_background(
            sources, previous=previous, rng=random.Random(seed),
            resolve=resolve or (lambda v: v), exists=exists or self.ok)

    def test_single_image(self):
        self.assertEqual(self.run_choose(["a.png"]), ("a.png", "a.png"))

    def test_single_image_may_repeat(self):
        self.assertEqual(self.run_choose(["a.png"], previous="a.png"), ("a.png", "a.png"))

    def test_never_repeats_previous_when_another_is_usable(self):
        for seed in range(50):
            source, _ = self.run_choose(["a.png", "b.png", "c.png"], previous="b.png", seed=seed)
            self.assertNotEqual(source, "b.png")

    def test_every_image_can_be_picked(self):
        seen = {self.run_choose(["a.png", "b.png", "c.png"], seed=s)[0] for s in range(60)}
        self.assertEqual(seen, {"a.png", "b.png", "c.png"})

    def test_skips_unusable_images(self):
        exists = lambda p: p == "good.png"
        for seed in range(20):
            self.assertEqual(self.run_choose(["bad1.png", "good.png", "bad2.png"], seed=seed, exists=exists),
                             ("good.png", "good.png"))

    def test_falls_back_to_previous_when_it_is_the_only_usable_one(self):
        exists = lambda p: p == "b.png"
        self.assertEqual(self.run_choose(["a.png", "b.png"], previous="b.png", exists=exists), ("b.png", "b.png"))

    def test_none_usable_returns_empty(self):
        self.assertEqual(self.run_choose(["a.png", "b.png"], exists=lambda p: False), ("", ""))

    def test_no_sources(self):
        self.assertEqual(self.run_choose([]), ("", ""))

    def test_remote_sources_are_only_resolved_when_tried(self):
        calls = []

        def resolve(v):
            calls.append(v)
            return v

        self.run_choose(["a.png", "b.png", "c.png"], resolve=resolve)
        self.assertEqual(len(calls), 1)

    def test_resolver_failure_moves_on_to_the_next_image(self):
        resolve = lambda v: "" if v == "http://x/bad.png" else v
        for seed in range(20):
            self.assertEqual(self.run_choose(["http://x/bad.png", "ok.png"], seed=seed, resolve=resolve)[0], "ok.png")


class ChooseBackgroundsTests(unittest.TestCase):
    def run_choose(self, sources, count, previous=None, seed=0, exists=None, resolve=None):
        return media.choose_backgrounds(
            sources, count, previous=previous, rng=random.Random(seed),
            resolve=resolve or (lambda v: v), exists=exists or (lambda p: True))

    def test_distinct_images_when_there_are_enough(self):
        for seed in range(30):
            picks = self.run_choose(["a", "b", "c", "d"], 3, seed=seed)
            self.assertEqual(len(picks), 3)
            self.assertEqual(len({src for src, _ in picks}), 3)

    def test_images_are_reused_when_there_are_too_few(self):
        picks = self.run_choose(["a", "b"], 4)
        self.assertEqual(len(picks), 4)
        self.assertEqual({src for src, _ in picks}, {"a", "b"})

    def test_single_image_is_used_on_every_screen(self):
        self.assertEqual(self.run_choose(["a"], 3), [("a", "a")] * 3)

    def test_first_entry_avoids_previous_when_possible(self):
        for seed in range(40):
            picks = self.run_choose(["a", "b", "c"], 2, previous="a", seed=seed)
            self.assertNotEqual(picks[0][0], "a")

    def test_previous_is_used_only_when_needed_to_fill_screens(self):
        picks = self.run_choose(["a", "b"], 2, previous="a")
        self.assertEqual({src for src, _ in picks}, {"a", "b"})
        self.assertEqual(picks[0][0], "b")

    def test_unusable_images_are_skipped(self):
        exists = lambda p: p in ("x", "y")
        for seed in range(20):
            picks = self.run_choose(["bad", "x", "worse", "y"], 2, seed=seed, exists=exists)
            self.assertEqual({src for src, _ in picks}, {"x", "y"})

    def test_nothing_usable(self):
        self.assertEqual(self.run_choose(["a", "b"], 3, exists=lambda p: False), [("", "")] * 3)

    def test_count_is_at_least_one(self):
        self.assertEqual(len(self.run_choose(["a"], 0)), 1)


class PickBackgroundsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.files = []
        for name in ("one.png", "two.png", "three.png"):
            path = os.path.join(self.tmp.name, name)
            open(path, "wb").close()
            self.files.append(path)
        media._LAST_BACKGROUND["source"] = None

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_images(self):
        self.assertEqual(media.pick_backgrounds({"background_images": []}, 3), ["", "", ""])

    def test_same_picture_on_all_screens_by_default(self):
        cfg = {"background_images": self.files}
        picks = media.pick_backgrounds(cfg, 3)
        self.assertEqual(len(picks), 3)
        self.assertEqual(len(set(picks)), 1)

    def test_different_pictures_per_screen_when_enabled(self):
        cfg = {"background_images": self.files, "background_per_screen": True}
        for _ in range(20):
            picks = media.pick_backgrounds(cfg, 3)
            self.assertEqual(len(set(picks)), 3)

    def test_per_screen_with_one_screen_is_a_plain_pick(self):
        cfg = {"background_images": self.files, "background_per_screen": True}
        self.assertEqual(len(media.pick_backgrounds(cfg, 1)), 1)


class PickBackgroundImageTests(unittest.TestCase):
    def test_no_images_gives_empty_path(self):
        self.assertEqual(media.pick_background_image({"background_images": []}), "")


if __name__ == "__main__":
    unittest.main()
