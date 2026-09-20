import json
import subprocess
from io import BytesIO
from pathlib import Path

from PIL import Image


class FFmpegError(RuntimeError):
    pass


def parse_frame_rate(value: str) -> float:
    text = str(value or '').strip()
    if not text or text in {'0/0', 'N/A'}:
        return 0.0
    if '/' in text:
        numerator, denominator = text.split('/', 1)
        den = float(denominator)
        return float(numerator) / den if den else 0.0
    return float(text)


def is_nearly_black(image: Image.Image, threshold: float = 2.0) -> bool:
    sample = image.convert('RGB').resize((48, 36))
    pixels = list(sample.getdata())
    if not pixels:
        return True
    mean = sum(sum(pixel) for pixel in pixels) / (len(pixels) * 3)
    return mean < threshold


def extract_command(source: str, pattern: str, fps: float, quality: int = 2) -> list[str]:
    return [
        'ffmpeg', '-y', '-hide_banner', '-loglevel', 'error',
        '-i', str(source),
        '-vf', f'yadif,fps={float(fps):.6f}',
        '-q:v', str(quality),
        '-start_number', '0',
        str(pattern),
    ]


def _run(args: list[str], check_stdout: bool = False) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True)
    if result.returncode != 0 or (check_stdout and not result.stdout):
        err = result.stderr.decode('utf-8', 'ignore').strip()[-800:]
        raise FFmpegError(err or f'ffmpeg failed: {" ".join(args)}')
    return result


def probe(path: str) -> dict:
    result = _run([
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-show_entries', 'stream=codec_type,width,height,avg_frame_rate,nb_frames,duration,codec_name',
        '-of', 'json', str(path),
    ])
    data = json.loads(result.stdout.decode('utf-8') or '{}')
    stream = next((item for item in data.get('streams') or [] if item.get('codec_type') == 'video'), None)
    if not stream:
        raise FFmpegError('No video stream found')
    fps = parse_frame_rate(stream.get('avg_frame_rate') or '0/0') or 25.0
    duration = float(stream.get('duration') or (data.get('format') or {}).get('duration') or 0)
    frames = stream.get('nb_frames')
    try:
        count = int(frames) if frames not in (None, 'N/A', '') else 0
    except ValueError:
        count = 0
    if count <= 0 and duration > 0:
        count = max(1, round(duration * fps))
    return {
        'width': int(stream.get('width') or 0),
        'height': int(stream.get('height') or 0),
        'fps': fps,
        'frame_count': count,
        'duration': duration,
        'codec': stream.get('codec_name'),
    }


def extract_jpegs(source: str, dest_dir: Path, fps: float, quality: int = 2) -> int:
    dest_dir.mkdir(parents=True, exist_ok=True)
    pattern = dest_dir / '%06d.jpg'
    _run(extract_command(source, str(pattern), fps, quality))
    return len(sorted(dest_dir.glob('*.jpg')))


def read_frame(source: str, seconds: float) -> Image.Image:
    result = _run([
        'ffmpeg', '-hide_banner', '-loglevel', 'error',
        '-ss', f'{max(0.0, float(seconds)):.6f}',
        '-i', str(source),
        '-frames:v', '1',
        '-vf', 'yadif',
        '-f', 'image2pipe', '-vcodec', 'png', 'pipe:1',
    ], check_stdout=True)
    return Image.open(BytesIO(result.stdout)).convert('RGB')
