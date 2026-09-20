def clamp_extract_fps(source_fps: float, extract_fps: float) -> float:
    source = max(float(source_fps or 0), 0.001)
    wanted = max(float(extract_fps or 0), 0.001)
    return min(wanted, source)


def sample_stride(source_fps: float, extract_fps: float) -> int:
    source = max(float(source_fps or 0), 0.001)
    extract = clamp_extract_fps(source, extract_fps)
    return max(1, round(source / extract))


def sampled_frame_count(source_frame_count: int, stride: int) -> int:
    count = max(0, int(source_frame_count or 0))
    step = max(1, int(stride or 1))
    if count == 0:
        return 0
    return (count + step - 1) // step


def duration_seconds(source_frame_count: int, source_fps: float) -> float:
    fps = max(float(source_fps or 0), 0.001)
    return max(0, int(source_frame_count or 0)) / fps
