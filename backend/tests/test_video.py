import unittest
from io import BytesIO

from PIL import Image


class VideoHelperTests(unittest.TestCase):
    def test_parse_fraction_frame_rate(self):
        from app.utils.video import parse_frame_rate
        self.assertAlmostEqual(parse_frame_rate('25/1'), 25.0)
        self.assertAlmostEqual(parse_frame_rate('30000/1001'), 29.97, places=2)

    def test_nearly_black_detects_failed_decode(self):
        from app.utils.video import is_nearly_black
        black = Image.new('RGB', (64, 48), (0, 0, 0))
        real = Image.new('RGB', (64, 48), (120, 90, 40))
        self.assertTrue(is_nearly_black(black))
        self.assertFalse(is_nearly_black(real))

    def test_extract_command_deinterlaces(self):
        from app.utils.video import extract_command
        cmd = extract_command('/data/video.mpg', '/data/out/%06d.jpg', 2.0)
        self.assertIn('ffmpeg', cmd[0])
        self.assertIn('yadif', ' '.join(cmd))
        self.assertIn('fps=2.000000', ' '.join(cmd))
        self.assertIn('-start_number', cmd)


if __name__ == '__main__':
    unittest.main()
