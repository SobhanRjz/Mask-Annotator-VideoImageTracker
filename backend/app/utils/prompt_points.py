from __future__ import annotations

import numpy as np


def prompt_arrays(points, mask=None):
    if not points:
        return None, None
    coords = np.asarray([[item['x'], item['y']] for item in points], np.float32)
    labels = np.asarray([1 if item['positive'] else 0 for item in points], np.int32)
    if mask is not None and not (labels == 1).any():
        ys, xs = np.where(mask)
        if len(xs):
            seed = np.asarray([[float(xs.mean()), float(ys.mean())]], np.float32)
            coords = np.vstack([seed, coords])
            labels = np.concatenate([np.asarray([1], np.int32), labels])
    return coords, labels
