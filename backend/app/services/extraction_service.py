import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.services.media_service import media_service


def parse_progress(output: str, duration: float) -> int:
    values = {}
    for line in output.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    if values.get("progress") == "end":
        return 100
    seconds = 0.0
    if "out_time_us" in values:
        seconds = float(values["out_time_us"] or 0) / 1_000_000
    elif "out_time_ms" in values:
        seconds = float(values["out_time_ms"] or 0) / 1_000_000
    if duration <= 0:
        return 0
    return max(0, min(99, round(seconds / duration * 100)))


@dataclass
class ExtractionJob:
    id: str
    media_id: int
    requested_fps: float
    status: str = "queued"
    progress: int = 0
    frame_count: int = 0
    error: str | None = None
    cancel_requested: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self):
        with self.lock:
            return {
                key: value
                for key, value in self.__dict__.items()
                if key != "lock"
            }


class ExtractionService:
    def __init__(self):
        self.jobs = {}
        self.guard = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1)

    def obj(self, job_id: str):
        with self.guard:
            job = self.jobs.get(job_id)
        if not job:
            raise KeyError("Extraction job not found")
        return job

    def start(self, media_id: int, frames_per_second: float):
        media = media_service.get(media_id)
        if media["kind"] != "video":
            raise ValueError("Only videos need frame extraction")
        with self.guard:
            active = any(
                job.media_id == media_id
                and job.status in {"queued", "running"}
                for job in self.jobs.values()
            )
            if active:
                raise ValueError("Extraction is already running for this video")
            job = ExtractionJob(
                uuid.uuid4().hex,
                media_id,
                float(frames_per_second),
            )
            self.jobs[job.id] = job
        self.pool.submit(self._run, job)
        return job.snapshot()

    def get(self, job_id: str):
        return self.obj(job_id).snapshot()

    def cancel(self, job_id: str):
        job = self.obj(job_id)
        with job.lock:
            job.cancel_requested = True
        return job.snapshot()

    def _run(self, job: ExtractionJob):
        try:
            with job.lock:
                job.status = "running"
                job.progress = 1

            def progress(percent):
                with job.lock:
                    if not job.cancel_requested:
                        job.progress = max(job.progress, min(99, int(percent)))

            media = media_service.extract(
                job.media_id,
                job.requested_fps,
                progress=progress,
                job_id=job.id,
            )
            with job.lock:
                job.frame_count = int(media["frame_count"])
                job.progress = 100
                job.status = "completed"
        except Exception as exc:
            with job.lock:
                job.status = "failed"
                job.error = str(exc)


extraction_service = ExtractionService()
