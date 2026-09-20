from pathlib import Path
import hashlib


def sha256_file(path: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while True:
            data = handle.read(chunk)
            if not data:
                break
            digest.update(data)
    return digest.hexdigest()


def sha256_copy(src, dest: Path, chunk: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('wb') as handle:
        while True:
            data = src.read(chunk)
            if not data:
                break
            digest.update(data)
            handle.write(data)
    return digest.hexdigest()
