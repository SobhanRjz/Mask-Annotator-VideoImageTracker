import unittest

from app.utils.extract import (
    clamp_extract_fps,
    duration_seconds,
    sample_stride,
    sampled_frame_count,
)


class ExtractMathTests(unittest.TestCase):
    def test_stride_one_fps_from_25(self):
        self.assertEqual(sample_stride(25, 1), 25)
        self.assertEqual(sampled_frame_count(2500, 25), 100)

    def test_stride_two_fps_from_30(self):
        self.assertEqual(sample_stride(30, 2), 15)
        self.assertEqual(sampled_frame_count(300, 15), 20)

    def test_cannot_extract_faster_than_source(self):
        self.assertEqual(clamp_extract_fps(25, 60), 25)
        self.assertEqual(sample_stride(25, 60), 1)
        self.assertEqual(sampled_frame_count(100, 1), 100)

    def test_duration(self):
        self.assertAlmostEqual(duration_seconds(2500, 25), 100.0)

    def test_empty_video(self):
        self.assertEqual(sampled_frame_count(0, 5), 0)


if __name__ == '__main__':
    unittest.main()
