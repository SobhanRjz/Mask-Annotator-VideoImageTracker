from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import json
import shutil
import threading
import uuid
import zipfile

import cv2
import numpy as np
from PIL import Image
from concurrent.futures import ThreadPoolExecutor

from app.core.db import db
from app.core.settings import settings
from app.services.annotation_service import annotation_service
from app.services.media_service import media_service


FORMATS = ('coco', 'yolo', 'voc', 'native')


def contours(mask: np.ndarray, mode=cv2.RETR_EXTERNAL):
    found, _hierarchy = cv2.findContours(
        mask.astype(np.uint8),
        mode,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    polygons = []
    if _hierarchy is None:
        return polygons
    for contour in found:
        if len(contour) < 3 or cv2.contourArea(contour) <= 2:
            continue
        polygons.append(contour.reshape(-1, 2))
    return polygons


def mask_to_rle(mask: np.ndarray):
    height, width = mask.shape
    pixels = np.asfortranarray(mask.astype(np.uint8)).ravel(order='F')
    if pixels.size == 0:
        return {'size': [int(height), int(width)], 'counts': []}
    changes = np.flatnonzero(pixels[1:] != pixels[:-1]) + 1
    starts = np.concatenate(([0], changes))
    lengths = np.diff(np.concatenate((starts, [pixels.size]))).tolist()
    counts = [0, *lengths] if int(pixels[0]) == 1 else lengths
    return {'size': [int(height), int(width)], 'counts': [int(value) for value in counts]}


def coco_segmentation(mask: np.ndarray):
    return mask_to_rle(mask)


def clamp01(value: float):
    return min(1.0, max(0.0, value))


def hex_rgb(color: str):
    text = (color or '').lstrip('#')
    if len(text) == 3:
        text = ''.join(char * 2 for char in text)
    if len(text) != 6:
        return (128, 128, 128)
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def allowed_source(source: str, include_auto: bool, include_manual: bool):
    if source == 'auto':
        return include_auto
    return include_manual


@dataclass
class ExportJob:
    id: str
    fmt: str
    project_ids: list[int] | None
    include_unannotated: bool
    include_auto: bool
    include_manual: bool
    status: str = 'queued'
    progress: int = 0
    message: str = 'Preparing the export'
    filename: str | None = None
    path: str | None = None
    error: str | None = None
    image_count: int = 0
    annotation_count: int = 0
    cancel_requested: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def snapshot(self):
        with self.lock:
            return {
                key: value
                for key, value in self.__dict__.items()
                if key != 'lock'
            }


class ExportService:
    def __init__(self):
        self.jobs = {}
        self.guard = threading.Lock()
        self.pool = ThreadPoolExecutor(max_workers=1)

    def obj(self, job_id: str):
        with self.guard:
            job = self.jobs.get(job_id)
        if not job:
            raise KeyError('Export job not found')
        return job

    def start(
        self,
        fmt: str,
        project_ids: list[int] | None = None,
        include_unannotated: bool = True,
        include_auto: bool = True,
        include_manual: bool = True,
    ):
        fmt = self._format(fmt)
        self._require_filters(include_unannotated, include_auto, include_manual)
        job = ExportJob(
            uuid.uuid4().hex,
            fmt,
            list(project_ids) if project_ids is not None else None,
            include_unannotated,
            include_auto,
            include_manual,
        )
        with self.guard:
            self.jobs[job.id] = job
        self.pool.submit(self._run, job)
        return job.snapshot()

    def get(self, job_id: str):
        return self.obj(job_id).snapshot()

    def cancel(self, job_id: str):
        job = self.obj(job_id)
        with job.lock:
            job.cancel_requested = True
            if job.status in ('queued', 'running'):
                job.message = 'Stopping export'
        return job.snapshot()

    def build(
        self,
        project_id: int,
        fmt: str,
        include_unannotated: bool = True,
        include_auto: bool = True,
        include_manual: bool = True,
        progress=None,
        cancelled=None,
    ) -> Path:
        return self.build_many(
            [project_id],
            fmt,
            include_unannotated,
            include_auto,
            include_manual,
            progress,
            cancelled,
        )

    def build_many(
        self,
        project_ids: list[int] | None,
        fmt: str,
        include_unannotated: bool = True,
        include_auto: bool = True,
        include_manual: bool = True,
        progress=None,
        cancelled=None,
    ) -> Path:
        fmt = self._format(fmt)
        self._require_filters(include_unannotated, include_auto, include_manual)
        projects, labels_by_project = self._load_projects(project_ids)
        if not projects:
            raise ValueError('No projects to export')

        token = uuid.uuid4().hex[:10]
        work = settings.export_root / f'work-{token}'
        work.mkdir(parents=True, exist_ok=True)
        images_dir = work / 'images'
        images_dir.mkdir()

        categories, label_to_category, label_to_yolo, label_rows = self._merge_labels(
            labels_by_project
        )
        image_records = []
        annotation_records = []
        yolo_lines: dict[str, str] = {}
        native_annotations = []
        voc_class_dir = work / 'SegmentationClass'
        voc_instance_dir = work / 'SegmentationObject'
        voc_list: list[str] = []
        if fmt == 'voc':
            voc_class_dir.mkdir()
            voc_instance_dir.mkdir()
            (work / 'JPEGImages').mkdir()

        image_id = 1
        annotation_id = 1
        medias = []
        for project in projects:
            with db() as conn:
                rows = conn.execute(
                    'SELECT * FROM media WHERE project_id=? ORDER BY id',
                    (project['id'],),
                ).fetchall()
            medias.extend((project, dict(row)) for row in rows)

        frame_total = max(1, sum(int(media['frame_count'] or 0) for _, media in medias))
        processed = 0

        def report(percent: int, message: str):
            if progress:
                progress(max(0, min(99, percent)), message)

        report(2, 'Preparing the export')

        try:
            for project, media in medias:
                if cancelled and cancelled():
                    raise InterruptedError('Export cancelled')
                with db() as conn:
                    excluded = {
                        row['frame']
                        for row in conn.execute(
                            'SELECT frame FROM excluded_frames WHERE media_id=?',
                            (media['id'],),
                        )
                    }
                    annotation_rows = conn.execute(
                        'SELECT * FROM annotations WHERE media_id=? ORDER BY frame,id',
                        (media['id'],),
                    ).fetchall()

                annotations_by_frame: dict[int, list[dict]] = {}
                for row in annotation_rows:
                    item = dict(row)
                    if allowed_source(item['source'], include_auto, include_manual):
                        annotations_by_frame.setdefault(item['frame'], []).append(item)

                for frame in range(int(media['frame_count'] or 0)):
                    processed += 1
                    if cancelled and cancelled():
                        raise InterruptedError('Export cancelled')
                    if processed == 1 or processed % 5 == 0 or processed == frame_total:
                        report(
                            5 + int(80 * processed / frame_total),
                            f'Preparing the export · {processed}/{frame_total} frames',
                        )
                    if frame in excluded:
                        continue

                    frame_annotations = annotations_by_frame.get(frame, [])
                    if not frame_annotations and not include_unannotated:
                        continue

                    file_name = (
                        f"m{media['id']}_{Path(media['name']).stem}_f{frame:06d}.jpg"
                    )
                    jpeg = media_service.frame_jpeg(
                        media['id'], frame, settings.jpeg_quality
                    )
                    (images_dir / file_name).write_bytes(jpeg)
                    if fmt == 'voc':
                        (work / 'JPEGImages' / file_name).write_bytes(jpeg)

                    width = int(media['width'])
                    height = int(media['height'])
                    image_records.append(
                        {
                            'id': image_id,
                            'file_name': file_name,
                            'width': width,
                            'height': height,
                            'media_id': media['id'],
                            'frame': frame,
                            'project_id': project['id'],
                        }
                    )
                    voc_list.append(Path(file_name).stem)
                    voc_class = np.zeros((height, width), dtype=np.uint8)
                    voc_instance = np.zeros((height, width), dtype=np.uint8)
                    frame_yolo_lines: list[str] = []

                    for instance_index, annotation in enumerate(frame_annotations, start=1):
                        mask = annotation_service.mask(annotation['id'])
                        ys, xs = np.where(mask)
                        if not len(xs):
                            continue
                        x0, y0 = int(xs.min()), int(ys.min())
                        x1, y1 = int(xs.max()), int(ys.max())
                        category_id = label_to_category[annotation['label_id']]
                        segmentation = coco_segmentation(mask)
                        annotation_records.append(
                            {
                                'id': annotation_id,
                                'image_id': image_id,
                                'category_id': category_id,
                                'segmentation': segmentation,
                                'area': float(mask.sum()),
                                'bbox': [x0, y0, x1 - x0 + 1, y1 - y0 + 1],
                                'iscrowd': 0,
                            }
                        )
                        native_annotations.append(
                            {
                                'id': annotation['id'],
                                'media_id': annotation['media_id'],
                                'frame': annotation['frame'],
                                'label_id': annotation['label_id'],
                                'source': annotation['source'],
                                'track_group': annotation.get('track_group'),
                                'mask': f"masks/ann_{annotation['id']}.png",
                            }
                        )
                        if fmt == 'native':
                            masks_dir = work / 'masks'
                            masks_dir.mkdir(exist_ok=True)
                            shutil.copy2(
                                annotation['mask_path'],
                                masks_dir / f"ann_{annotation['id']}.png",
                            )
                        if fmt == 'voc':
                            if instance_index >= 255:
                                raise ValueError(
                                    'VOC supports at most 254 instances per image'
                                )
                            voc_class[mask] = category_id
                            voc_instance[mask] = instance_index
                        for contour in contours(mask, cv2.RETR_EXTERNAL):
                            points: list[float] = []
                            for x, y in contour:
                                points += [
                                    round(clamp01(float(x) / max(width, 1)), 6),
                                    round(clamp01(float(y) / max(height, 1)), 6),
                                ]
                            if len(points) >= 6:
                                frame_yolo_lines.append(
                                    str(label_to_yolo[annotation['label_id']])
                                    + ' '
                                    + ' '.join(map(str, points))
                                )
                        annotation_id += 1

                    yolo_lines[file_name] = (
                        '\n'.join(frame_yolo_lines) + ('\n' if frame_yolo_lines else '')
                    )
                    if fmt == 'voc':
                        class_image = Image.fromarray(voc_class)
                        class_image.putpalette(self._voc_class_palette(categories, label_rows))
                        class_image.save(voc_class_dir / f'{Path(file_name).stem}.png')
                        instance_image = Image.fromarray(voc_instance)
                        instance_image.putpalette(self._voc_instance_palette())
                        instance_image.save(voc_instance_dir / f'{Path(file_name).stem}.png')
                    image_id += 1

            report(90, 'Writing annotation files')
            self._write_format(
                work,
                fmt,
                projects,
                categories,
                label_rows,
                image_records,
                annotation_records,
                yolo_lines,
                native_annotations,
                voc_list,
                include_unannotated,
                include_auto,
                include_manual,
            )

            stem = (
                Path(projects[0]['name']).stem
                if len(projects) == 1
                else 'all-projects'
            )
            output = settings.export_root / f'{stem}-{fmt}-{token}.zip'
            report(94, 'Compressing export zip')
            try:
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for path in work.rglob('*'):
                        if cancelled and cancelled():
                            raise InterruptedError('Export cancelled')
                        if path.is_file():
                            archive.write(path, path.relative_to(work))
            except InterruptedError:
                output.unlink(missing_ok=True)
                raise
            return output
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _run(self, job: ExportJob):
        try:
            with job.lock:
                job.status = 'running'
                job.progress = 1
                job.message = 'Preparing the export'

            def progress(percent: int, message: str):
                with job.lock:
                    job.progress = percent
                    job.message = message

            def cancelled():
                with job.lock:
                    return job.cancel_requested

            output = self.build_many(
                job.project_ids,
                job.fmt,
                job.include_unannotated,
                job.include_auto,
                job.include_manual,
                progress,
                cancelled,
            )
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
            with job.lock:
                job.path = str(output)
                job.filename = output.name
                job.status = 'completed'
                job.progress = 100
                job.message = 'Export ready'
                job.image_count = sum(
                    1 for name in names if name.startswith('images/') and name.endswith('.jpg')
                )
        except InterruptedError:
            with job.lock:
                job.status = 'cancelled'
                job.progress = job.progress
                job.message = 'Export cancelled'
        except Exception as exc:
            with job.lock:
                job.status = 'failed'
                job.error = str(exc)
                job.message = 'Export failed'

    def _format(self, fmt: str):
        fmt = (fmt or '').lower()
        if fmt not in FORMATS:
            raise ValueError('Supported formats: coco, yolo, voc, native')
        return fmt

    def _require_filters(self, include_unannotated, include_auto, include_manual):
        if not (include_unannotated or include_auto or include_manual):
            raise ValueError(
                'Select unannotated frames, auto masks, or manual masks'
            )

    def _load_projects(self, project_ids: list[int] | None):
        with db() as conn:
            if project_ids is None:
                projects = [
                    dict(row)
                    for row in conn.execute('SELECT * FROM projects ORDER BY id')
                ]
            else:
                projects = []
                for project_id in project_ids:
                    row = conn.execute(
                        'SELECT * FROM projects WHERE id=?', (project_id,)
                    ).fetchone()
                    if not row:
                        raise KeyError('Project not found')
                    projects.append(dict(row))
            labels_by_project = {}
            for project in projects:
                labels_by_project[project['id']] = [
                    dict(row)
                    for row in conn.execute(
                        'SELECT * FROM labels WHERE project_id=? ORDER BY id',
                        (project['id'],),
                    )
                ]
        return projects, labels_by_project

    def _merge_labels(self, labels_by_project: dict[int, list[dict]]):
        categories = []
        label_to_category = {}
        label_to_yolo = {}
        label_rows = []
        name_to_category = {}
        for project_id in sorted(labels_by_project):
            for row in labels_by_project[project_id]:
                label_rows.append(row)
                name = row['name']
                if name not in name_to_category:
                    category_id = len(categories) + 1
                    name_to_category[name] = category_id
                    categories.append(
                        {
                            'id': category_id,
                            'name': name,
                            'supercategory': 'defect',
                        }
                    )
                label_to_category[row['id']] = name_to_category[name]
                label_to_yolo[row['id']] = name_to_category[name] - 1
        return categories, label_to_category, label_to_yolo, label_rows

    def _write_format(
        self,
        work: Path,
        fmt: str,
        projects: list[dict],
        categories: list[dict],
        label_rows: list[dict],
        image_records: list[dict],
        annotation_records: list[dict],
        yolo_lines: dict[str, str],
        native_annotations: list[dict],
        voc_list: list[str],
        include_unannotated: bool,
        include_auto: bool,
        include_manual: bool,
    ):
        if fmt == 'coco':
            coco_images = [
                {
                    'id': row['id'],
                    'file_name': row['file_name'],
                    'width': row['width'],
                    'height': row['height'],
                }
                for row in image_records
            ]
            now = datetime.now(timezone.utc).strftime('%Y-%m-%d')
            description = (
                projects[0]['name']
                if len(projects) == 1
                else f"Merged export of {len(projects)} projects"
            )
            coco = {
                'info': {
                    'description': description,
                    'version': '2.0',
                    'year': int(now[:4]),
                    'contributor': 'Sewer SAM2 Annotator',
                    'date_created': now,
                },
                'licenses': [],
                'images': coco_images,
                'annotations': annotation_records,
                'categories': categories,
            }
            annotations_dir = work / 'annotations'
            annotations_dir.mkdir(exist_ok=True)
            (annotations_dir / 'instances_default.json').write_text(
                json.dumps(coco, indent=2), encoding='utf-8'
            )
            return

        if fmt == 'yolo':
            labels_dir = work / 'labels'
            labels_dir.mkdir()
            for image_name, text in yolo_lines.items():
                (labels_dir / (Path(image_name).stem + '.txt')).write_text(
                    text, encoding='utf-8'
                )
            names = [row['name'] for row in categories]
            (work / 'classes.txt').write_text(
                '\n'.join(names) + ('\n' if names else ''), encoding='utf-8'
            )
            yaml_names = ''.join(
                f"  {index}: {row['name']}\n" for index, row in enumerate(categories)
            )
            data_yaml = (
                'path: .\n'
                'train: images\n'
                'val: images\n'
                'names:\n'
                + (yaml_names if yaml_names else '  {}\n')
            )
            (work / 'data.yaml').write_text(data_yaml, encoding='utf-8')
            return

        if fmt == 'voc':
            sets = work / 'ImageSets' / 'Segmentation'
            sets.mkdir(parents=True)
            split_text = '\n'.join(voc_list) + ('\n' if voc_list else '')
            for split_name in ('default.txt', 'train.txt', 'trainval.txt'):
                (sets / split_name).write_text(split_text, encoding='utf-8')
            labelmap = ['# name:color_rgb:parts:actions', 'background:0,0,0::']
            seen = set()
            for row in label_rows:
                if row['name'] in seen:
                    continue
                seen.add(row['name'])
                red, green, blue = hex_rgb(row['color'])
                labelmap.append(f"{row['name']}:{red},{green},{blue}::")
            (work / 'labelmap.txt').write_text('\n'.join(labelmap) + '\n', encoding='utf-8')
            return

        data = {
            'format': 'sewer-annotator-v2',
            'merged': len(projects) > 1,
            'project': projects[0] if len(projects) == 1 else None,
            'projects': projects,
            'labels': label_rows,
            'images': image_records,
            'annotations': native_annotations,
            'options': {
                'include_unannotated': include_unannotated,
                'include_auto': include_auto,
                'include_manual': include_manual,
            },
        }
        (work / 'project.json').write_text(json.dumps(data, indent=2), encoding='utf-8')

    def _voc_class_palette(self, categories, label_rows):
        palette = [0] * 768
        colors = {row['name']: hex_rgb(row['color']) for row in label_rows}
        for category in categories:
            offset = int(category['id']) * 3
            palette[offset:offset + 3] = colors.get(category['name'], (128, 128, 128))
        return palette

    def _voc_instance_palette(self):
        palette = [0] * 768
        for index in range(256):
            value = index
            red = green = blue = 0
            for shift in range(8):
                red |= ((value >> 0) & 1) << (7 - shift)
                green |= ((value >> 1) & 1) << (7 - shift)
                blue |= ((value >> 2) & 1) << (7 - shift)
                value >>= 3
            palette[index * 3:index * 3 + 3] = (red, green, blue)
        return palette


export_service = ExportService()
