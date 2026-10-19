"""Tests for animated GIF backgrounds: decoding, memory limits and frame timing."""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image

import gifbg


def make_gif(path, colors, size=(8, 6), durations=100, **save_kwargs):
    frames = [Image.new("RGB", size, c) for c in colors]
    frames[0].save(path, save_all=True, append_images=frames[1:], loop=0,
                   duration=durations, **save_kwargs)


class FrameDelayTests(unittest.TestCase):
    def test_zero_and_tiny_delays_use_the_browser_default(self):
        self.assertEqual(gifbg.frame_delay_ms(0), gifbg.DEFAULT_DELAY_MS)
        self.assertEqual(gifbg.frame_delay_ms(10), gifbg.DEFAULT_DELAY_MS)
        self.assertEqual(gifbg.frame_delay_ms(None), gifbg.DEFAULT_DELAY_MS)
        self.assertEqual(gifbg.frame_delay_ms("abc"), gifbg.DEFAULT_DELAY_MS)

    def test_normal_delays_are_kept_and_never_below_the_minimum(self):
        self.assertEqual(gifbg.frame_delay_ms(120), 120)
        self.assertEqual(gifbg.frame_delay_ms(20), gifbg.MIN_DELAY_MS)


class LoadGifFramesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(gifbg, "log", lambda *_a, **_k: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        gifbg.clear_cache()
        self.addCleanup(gifbg.clear_cache)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def test_animated_gif_gives_rgb_frames_in_order(self):
        p = self.path("a.gif")
        make_gif(p, [(255, 0, 0), (0, 255, 0), (0, 0, 255)], durations=[100, 200, 300])
        g = gifbg.load_gif_frames(p)
        self.assertEqual(len(g), 3)
        self.assertEqual(g.delays, [100, 200, 300])
        for frame, expected in zip(g.frames, [(255, 0, 0), (0, 255, 0), (0, 0, 255)]):
            self.assertEqual(frame.mode, "RGB")
            self.assertEqual(frame.size, (8, 6))
            r, gr, b = frame.getpixel((3, 3))
            self.assertTrue(all(abs(a - e) < 8 for a, e in zip((r, gr, b), expected)))

    def test_single_frame_gif_is_not_animated(self):
        p = self.path("one.gif")
        Image.new("RGB", (8, 6), "red").save(p)
        self.assertIsNone(gifbg.load_gif_frames(p))

    def test_other_formats_missing_and_broken_files_are_not_animated(self):
        png = self.path("a.png")
        Image.new("RGB", (8, 6), "red").save(png)
        self.assertIsNone(gifbg.load_gif_frames(png))
        self.assertIsNone(gifbg.load_gif_frames(self.path("missing.gif")))
        broken = self.path("broken.gif")
        with open(broken, "wb") as f:
            f.write(b"GIF89a not really a gif")
        self.assertIsNone(gifbg.load_gif_frames(broken))

    def test_transparent_pixels_show_the_dark_backdrop(self):
        p = self.path("t.gif")
        frames = [Image.new("RGBA", (8, 6), (0, 0, 0, 0)) for _ in range(2)]
        frames[1].putpixel((7, 5), (255, 0, 0, 255))   # identical frames would be merged
        frames[0].save(p, save_all=True, append_images=frames[1:], duration=100,
                       loop=0, disposal=2, transparency=0)
        g = gifbg.load_gif_frames(p)
        self.assertIsNotNone(g)
        px = g.frames[0].getpixel((2, 2))
        self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(px, gifbg.BACKDROP)))

    def test_long_gifs_are_cut_at_max_frames(self):
        p = self.path("long.gif")
        make_gif(p, [(i * 20, 0, 0) for i in range(10)])
        g = gifbg.load_gif_frames(p, max_frames=4)
        self.assertEqual(len(g), 4)

    def test_memory_budget_shrinks_big_frames(self):
        p = self.path("big.gif")
        make_gif(p, [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)], size=(200, 100))
        budget = 200 * 100 * 3 * 4 // 2          # half of what 4 full frames need
        g = gifbg.load_gif_frames(p, max_bytes=budget)
        self.assertIsNotNone(g)
        self.assertLess(g.frames[0].size[0], 200)
        self.assertLessEqual(g.nbytes, budget)

    def test_budget_that_is_too_small_cuts_frames_instead_of_blurring(self):
        p = self.path("huge.gif")
        make_gif(p, [(i * 10, 0, 0) for i in range(8)], size=(100, 100))
        g = gifbg.load_gif_frames(p, max_bytes=100 * 100 * 3 * 3)   # room for 3 full frames
        self.assertLessEqual(len(g), 8)
        self.assertLessEqual(g.nbytes, 100 * 100 * 3 * 3)
        self.assertGreaterEqual(len(g), 2)


class GetGifFramesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(gifbg, "log", lambda *_a, **_k: None)
        patcher.start()
        self.addCleanup(patcher.stop)
        gifbg.clear_cache()
        self.addCleanup(gifbg.clear_cache)

    def test_same_file_is_decoded_once_and_shared(self):
        p = os.path.join(self.tmp.name, "a.gif")
        make_gif(p, [(255, 0, 0), (0, 255, 0)])
        first = gifbg.get_gif_frames(p)
        self.assertIs(gifbg.get_gif_frames(p), first)

    def test_non_gif_and_empty_paths_give_none(self):
        png = os.path.join(self.tmp.name, "a.png")
        Image.new("RGB", (8, 6), "red").save(png)
        self.assertIsNone(gifbg.get_gif_frames(png))
        self.assertIsNone(gifbg.get_gif_frames(""))
        self.assertIsNone(gifbg.get_gif_frames(None))
        self.assertIsNone(gifbg.get_gif_frames(os.path.join(self.tmp.name, "nope.gif")))

    def test_total_budget_falls_back_to_a_still_picture(self):
        p = os.path.join(self.tmp.name, "a.gif")
        make_gif(p, [(255, 0, 0), (0, 255, 0)])
        with mock.patch.object(gifbg, "TOTAL_DECODED_BYTES", 1024):
            self.assertIsNone(gifbg.get_gif_frames(p))


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class AnimatorTests(unittest.TestCase):
    def setUp(self):
        self.scheduled = []        # (ms, fn)
        self.cancelled = []
        self.shown = []
        self.clock = FakeClock()

    def schedule(self, ms, fn):
        handle = len(self.scheduled)
        self.scheduled.append((ms, fn))
        return handle

    def run_next(self):
        ms, fn = self.scheduled[-1]
        fn()

    def make(self, delays, show=None):
        return gifbg.Animator(delays, show or self.shown.append, self.schedule,
                              self.cancelled.append, clock=self.clock)

    def test_frames_advance_in_order_and_wrap_around(self):
        a = self.make([100, 200, 300])
        a.start()
        self.assertEqual(self.scheduled[-1][0], 100)       # frame 0 is already on screen
        for _ in range(4):
            self.run_next()
        self.assertEqual(self.shown, [1, 2, 0, 1])

    def test_each_delay_is_the_new_frames_own_delay(self):
        a = self.make([100, 200, 300])
        a.start()
        self.run_next()                                    # now showing frame 1
        self.assertEqual(self.scheduled[-1][0], 200)
        self.run_next()                                    # frame 2
        self.assertEqual(self.scheduled[-1][0], 300)

    def test_drawing_time_is_taken_off_the_next_delay(self):
        def slow(_i):
            self.clock.now += 0.06                         # drawing took 60 ms
        a = self.make([100, 100], show=slow)
        a.start()
        self.run_next()
        self.assertEqual(self.scheduled[-1][0], 40)

    def test_delay_never_drops_below_one_millisecond(self):
        def very_slow(_i):
            self.clock.now += 5.0
        a = self.make([100, 100], show=very_slow)
        a.start()
        self.run_next()
        self.assertEqual(self.scheduled[-1][0], 1)

    def test_stop_cancels_and_late_callbacks_do_nothing(self):
        a = self.make([100, 100])
        a.start()
        pending = self.scheduled[-1][1]
        a.stop()
        self.assertEqual(len(self.cancelled), 1)
        before = len(self.scheduled)
        pending()
        self.assertEqual(self.shown, [])
        self.assertEqual(len(self.scheduled), before)

    def test_start_twice_schedules_only_once(self):
        a = self.make([100, 100])
        a.start()
        a.start()
        self.assertEqual(len(self.scheduled), 1)

    def test_an_error_while_drawing_stops_the_animation(self):
        def boom(_i):
            raise RuntimeError("window is gone")
        a = self.make([100, 100], show=boom)
        a.start()
        self.run_next()
        self.assertFalse(a.running)
        self.assertEqual(len(self.scheduled), 1)           # nothing new was scheduled

    def test_can_restart_after_stop(self):
        a = self.make([100, 100])
        a.start()
        a.stop()
        a.start()
        self.assertTrue(a.running)
        self.assertEqual(len(self.scheduled), 2)


if __name__ == "__main__":
    unittest.main()
