from __future__ import annotations

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from app.core.db import get_setting, set_setting
from app.core.settings import settings
from app.services.model_catalog import (
    CATALOG,
    DEFAULT_KEY,
    catalog_entry,
    checkpoint_cached,
    ensure_checkpoint,
    key_for_model_id,
)
from app.services.sam2_runtime import sam2_runtime
from app.services.tracking_service import tracking_service

SAM_MODEL_KEY = 'sam_model'


class ModelSwitchBusy(Exception):
    def __init__(self):
        super().__init__('A model switch is already running')


def active_model_key():
    saved = get_setting(SAM_MODEL_KEY)
    if saved:
        try:
            catalog_entry(saved)
            return saved
        except ValueError:
            pass
    return key_for_model_id(settings.model_id)


@dataclass
class SwitchJob:
    id: str
    key: str
    status: str = 'queued'
    progress: int = 0
    message: str = 'Waiting for tracker to finish…'
    error: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self):
        with self.lock:
            return {
                key: value
                for key, value in self.__dict__.items()
                if key != 'lock'
            }


class ModelService:
    def __init__(
        self,
        runtime=None,
        tracking=None,
        ensure_checkpoint=None,
        is_cached=None,
        load_setting=None,
        save_setting=None,
    ):
        self.runtime = runtime or sam2_runtime
        self.tracking = tracking or tracking_service
        self.ensure_checkpoint = ensure_checkpoint
        self.is_cached = is_cached or checkpoint_cached
        self.load_setting = load_setting
        self.save_setting = save_setting
        self.jobs = {}
        self.current_id = None
        self.guard = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1)

    def _ensure(self, key, progress=None):
        if self.ensure_checkpoint:
            return self.ensure_checkpoint(key, progress)
        return ensure_checkpoint(key, progress)

    def _read_key(self):
        if self.load_setting:
            saved = self.load_setting()
            if saved:
                try:
                    catalog_entry(saved)
                    return saved
                except ValueError:
                    pass
            return getattr(self.runtime, 'model_key', None) or DEFAULT_KEY
        return active_model_key()

    def _write_key(self, key):
        if self.save_setting:
            self.save_setting(key)
            return
        set_setting(SAM_MODEL_KEY, key)

    def _busy_job(self):
        with self.guard:
            job_id = self.current_id
            job = self.jobs.get(job_id) if job_id else None
        if not job:
            return None
        with job.lock:
            if job.status in ('queued', 'running'):
                return job
        return None

    def status(self):
        runtime = self.runtime.status()
        active = runtime.get('key') or self._read_key()
        job = None
        with self.guard:
            if self.current_id and self.current_id in self.jobs:
                job = self.jobs[self.current_id].snapshot()
        return {
            'active': active,
            'model_id': runtime.get('model') or catalog_entry(active)['model_id'],
            'ready': runtime.get('ready'),
            'loading': runtime.get('loading'),
            'error': runtime.get('error'),
            'models': [
                {
                    **entry,
                    'cached': bool(self.is_cached(entry['key'])),
                    'active': entry['key'] == active,
                }
                for entry in CATALOG.values()
            ],
            'job': job,
        }

    def obj(self, job_id: str):
        with self.guard:
            job = self.jobs.get(job_id)
        if not job:
            raise KeyError('Model switch job not found')
        return job

    def get(self, job_id: str):
        return self.obj(job_id).snapshot()

    def start(self, key: str):
        catalog_entry(key)
        with self.guard:
            current = self.current_id
            job = self.jobs.get(current) if current else None
            if job:
                with job.lock:
                    busy = job.status in ('queued', 'running')
                if busy:
                    raise ModelSwitchBusy()
            job = SwitchJob(uuid.uuid4().hex, key)
            self.jobs[job.id] = job
            self.current_id = job.id
        self.pool.submit(self._run, job)
        return job.snapshot()

    def _run(self, job: SwitchJob):
        try:
            with job.lock:
                job.status = 'running'
                job.progress = 1
                job.message = 'Waiting for tracker to finish…'
            self._wait_idle(job)
            cached = bool(self.is_cached(job.key))
            if cached:
                with job.lock:
                    job.progress = 80
                    job.message = 'Already downloaded — loading onto GPU…'
            else:
                with job.lock:
                    job.message = 'Downloading 0%'
                def download_progress(done, total):
                    percent = 5 + int((done / max(1, total)) * 75)
                    with job.lock:
                        job.progress = min(80, percent)
                        job.message = f'Downloading {min(100, int(done / max(1, total) * 100))}%'
                self._ensure(job.key, download_progress)
                with job.lock:
                    job.progress = max(job.progress, 80)
                    job.message = 'Loading onto GPU…'
            self._wait_idle(job)
            entry = catalog_entry(job.key)

            def load_progress(percent):
                with job.lock:
                    job.progress = max(job.progress, percent)
                    job.message = 'Loading onto GPU…'

            self.runtime.swap(job.key, entry['model_id'], load_progress)
            self._write_key(job.key)
            with job.lock:
                job.status = 'completed'
                job.progress = 100
                job.message = 'Ready'
        except Exception as exc:
            with job.lock:
                job.status = 'failed'
                job.error = str(exc)
                job.message = str(exc)

    def _wait_idle(self, job: SwitchJob):
        while self.tracking.is_busy() or getattr(self.runtime, 'loading', False):
            with job.lock:
                job.message = 'Waiting for tracker to finish…'
            time.sleep(0.15)


model_service = ModelService()
