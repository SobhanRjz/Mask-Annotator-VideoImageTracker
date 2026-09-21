from app.core.db import get_setting, set_setting

TRACK_PATCH_KEY = 'track_patch_size'
DEFAULT_PATCH = 16
MIN_PATCH = 2
MAX_PATCH = 128


def parse_patch(value, default=DEFAULT_PATCH):
    if value is None or value == '':
        return default
    try:
        size = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError('Images per patch must be a whole number') from exc
    return max(MIN_PATCH, min(MAX_PATCH, size))


def get_patch():
    try:
        return parse_patch(get_setting(TRACK_PATCH_KEY, str(DEFAULT_PATCH)))
    except ValueError:
        return DEFAULT_PATCH


def set_patch(value):
    size = parse_patch(value)
    set_setting(TRACK_PATCH_KEY, str(size))
    return size


def track_windows(start, end, patch):
    if start == end:
        return []
    patch = parse_patch(patch)
    step = 1 if end > start else -1
    windows = []
    current = start
    while current != end:
        span = min(patch - 1, abs(end - current))
        nxt = current + step * span
        windows.append((current, nxt))
        current = nxt
    return windows
