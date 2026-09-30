import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch


class ExtractionJobTests(unittest.TestCase):
    def test_ffmpeg_progress_is_converted_to_percent(self):
        from app.services.extraction_service import parse_progress

        self.assertEqual(parse_progress("out_time_us=5000000\n", 10), 50)
        self.assertEqual(parse_progress("out_time_ms=7500000\n", 10), 75)
        self.assertEqual(parse_progress("progress=end\n", 10), 100)

    def test_start_returns_job_before_extraction_finishes(self):
        from app.services.extraction_service import ExtractionService

        service = ExtractionService()
        completed = []

        def fake_extract(_mid, _fps, progress=None, **_kwargs):
            progress(40)
            time.sleep(0.05)
            progress(90)
            completed.append(True)
            return {"id": 7, "frame_count": 12, "extract_status": "ready"}

        with patch("app.services.extraction_service.media_service") as media, patch(
            "app.services.extraction_service.media_service.extract", fake_extract
        ):
            media.get.return_value = {
                "id": 7,
                "kind": "video",
                "extract_status": "pending",
            }
            job = service.start(7, 0.5)
            self.assertIn(job["status"], {"queued", "running"})
            self.assertEqual(job["media_id"], 7)
            deadline = time.time() + 2
            snapshot = service.get(job["id"])
            while snapshot["status"] in {"queued", "running"}:
                if time.time() > deadline:
                    self.fail(f"job did not finish: {snapshot}")
                time.sleep(0.02)
                snapshot = service.get(job["id"])

        self.assertEqual(snapshot["status"], "completed")
        self.assertEqual(snapshot["progress"], 100)
        self.assertTrue(completed)
        service.pool.shutdown(wait=False)

    def test_same_media_cannot_have_two_active_jobs(self):
        from app.services.extraction_service import ExtractionService

        service = ExtractionService()
        def slow_extract(*_args, **_kwargs):
            time.sleep(0.15)
            return {"id": 7, "frame_count": 12}

        with patch("app.services.extraction_service.media_service") as media, patch(
            "app.services.extraction_service.media_service.extract", slow_extract
        ):
            media.get.return_value = {
                "id": 7,
                "kind": "video",
                "extract_status": "pending",
            }
            first = service.start(7, 1)
            with self.assertRaises(ValueError):
                service.start(7, 2)
            service.cancel(first["id"])
        service.pool.shutdown(wait=False)

    def test_failed_extraction_is_reported(self):
        from app.services.extraction_service import ExtractionService

        service = ExtractionService()

        def fail(*_args, **_kwargs):
            raise RuntimeError("ffmpeg failed")

        with patch("app.services.extraction_service.media_service") as media, patch(
            "app.services.extraction_service.media_service.extract", fail
        ):
            media.get.return_value = {
                "id": 7,
                "kind": "video",
                "extract_status": "pending",
            }
            job = service.start(7, 1)
            deadline = time.time() + 2
            snapshot = service.get(job["id"])
            while snapshot["status"] in {"queued", "running"}:
                if time.time() > deadline:
                    self.fail(f"job did not finish: {snapshot}")
                time.sleep(0.02)
                snapshot = service.get(job["id"])

        self.assertEqual(snapshot["status"], "failed")
        self.assertEqual(snapshot["error"], "ffmpeg failed")
        service.pool.shutdown(wait=False)


class BulkAnnotationClearTests(unittest.TestCase):
    def test_clear_frames_deletes_masks_for_selected_frames(self):
        import numpy as np

        from app.core.db import initialize_db
        from app.core.settings import settings
        from app.services.annotation_service import AnnotationService
        from app.services.media_service import media_service
        from app.services.project_service import project_service

        with tempfile.TemporaryDirectory() as root:
            old_root = settings.data_root
            settings.data_root = Path(root)
            try:
                initialize_db()
                project = project_service.create("clear-frames")
                from app.core.db import db

                with db() as conn:
                    conn.execute(
                        """INSERT INTO media(
                            id, project_id, name, kind, path, width, height,
                            frame_count, fps, extract_status
                        ) VALUES (9, ?, 'video.mp4', 'video', ?, 4, 4, 3, 1, 'ready')""",
                        (project["id"], str(Path(root) / "video.mp4")),
                    )
                service = AnnotationService()
                with patch.object(
                    media_service,
                    "get",
                    return_value={
                        "id": 9,
                        "project_id": project["id"],
                        "width": 4,
                        "height": 4,
                        "frame_count": 3,
                    },
                ):
                    label_id = project["labels"][0]["id"]
                    service.save(9, 0, label_id, np.ones((4, 4), dtype=bool))
                    service.save(9, 1, label_id, np.ones((4, 4), dtype=bool))
                    result = service.clear_frames(9, [0])
                self.assertEqual(result["deleted"], 1)
            finally:
                settings.data_root = old_root


if __name__ == "__main__":
    unittest.main()
