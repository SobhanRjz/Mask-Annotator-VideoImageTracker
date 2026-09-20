import unittest

import numpy as np

from app.utils.prompt_points import prompt_arrays


class PromptPointTests(unittest.TestCase):
    def test_all_clicks_are_kept_in_order(self):
        coords, labels = prompt_arrays(
            [
                {'x': 10.0, 'y': 20.0, 'positive': True},
                {'x': 30.0, 'y': 40.0, 'positive': False},
                {'x': 12.0, 'y': 22.0, 'positive': True},
            ],
            None,
        )
        np.testing.assert_array_equal(coords, [[10, 20], [30, 40], [12, 22]])
        np.testing.assert_array_equal(labels, [1, 0, 1])

    def test_negative_only_on_a_mask_adds_a_positive_seed(self):
        mask = np.zeros((10, 10), dtype=bool)
        mask[2:5, 4:8] = True
        coords, labels = prompt_arrays(
            [{'x': 1.0, 'y': 1.0, 'positive': False}],
            mask,
        )
        self.assertEqual(int((labels == 1).sum()), 1)
        self.assertEqual(int((labels == 0).sum()), 1)
        self.assertAlmostEqual(float(coords[0, 0]), 5.5, places=5)
        self.assertAlmostEqual(float(coords[0, 1]), 3.0, places=5)
        np.testing.assert_array_equal(coords[1], [1, 1])

    def test_existing_positive_is_not_replaced_by_a_centroid(self):
        mask = np.ones((4, 4), dtype=bool)
        coords, labels = prompt_arrays(
            [
                {'x': 2.0, 'y': 1.0, 'positive': True},
                {'x': 0.0, 'y': 0.0, 'positive': False},
            ],
            mask,
        )
        np.testing.assert_array_equal(coords, [[2, 1], [0, 0]])
        np.testing.assert_array_equal(labels, [1, 0])

    def test_empty_points_stay_empty(self):
        coords, labels = prompt_arrays([], np.ones((3, 3), dtype=bool))
        self.assertIsNone(coords)
        self.assertIsNone(labels)


if __name__ == '__main__':
    unittest.main()
