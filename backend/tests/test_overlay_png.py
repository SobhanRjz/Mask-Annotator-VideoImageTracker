import io
import unittest

import numpy as np
from PIL import Image

from app.utils.images import overlay_png


class OverlayPngTests(unittest.TestCase):
    def test_mask_pixels_are_opaque(self):
        mask = np.zeros((4, 4), dtype=bool)
        mask[1, 2] = True
        png = overlay_png(mask)
        pixels = np.asarray(Image.open(io.BytesIO(png)).convert('RGBA'))
        self.assertEqual(int(pixels[1, 2, 3]), 255)
        self.assertEqual(int(pixels[0, 0, 3]), 0)

    def test_fit_mask_nearest_neighbor_resize(self):
        from app.utils.images import fit_mask
        src = np.zeros((2, 2), dtype=bool)
        src[0, 1] = True
        out = fit_mask(src, 4, 4)
        self.assertEqual(out.shape, (4, 4))
        self.assertTrue(out[0, 2])
        self.assertFalse(out[3, 0])
