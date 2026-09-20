from pathlib import Path
import json
import shutil
import uuid
import zipfile

from app.core.db import db
from app.core.settings import settings
from app.utils.files import sha256_file
from app.utils.slugs import allocate_name


BACKUP_FORMAT = 'sewer-annotator-backup-v1'


class BackupService:
    def build(self, project_id) -> Path:
        with db() as conn:
            project = conn.execute(
                'SELECT * FROM projects WHERE id=?', (project_id,)
            ).fetchone()
            if not project:
                raise KeyError('Project not found')
            project = dict(project)
            labels = [
                dict(row)
                for row in conn.execute(
                    'SELECT id,name,color FROM labels WHERE project_id=? ORDER BY id',
                    (project_id,),
                )
            ]
            media_rows = [
                dict(row)
                for row in conn.execute(
                    'SELECT * FROM media WHERE project_id=? ORDER BY id',
                    (project_id,),
                )
            ]
            media_ids = [row['id'] for row in media_rows]
            excluded_rows = []
            annotation_rows = []
            if media_ids:
                placeholders = ','.join('?' * len(media_ids))
                excluded_rows = [
                    dict(row)
                    for row in conn.execute(
                        f'SELECT media_id,frame FROM excluded_frames WHERE media_id IN ({placeholders}) ORDER BY media_id,frame',
                        media_ids,
                    )
                ]
                annotation_rows = [
                    dict(row)
                    for row in conn.execute(
                        f'SELECT * FROM annotations WHERE media_id IN ({placeholders}) ORDER BY id',
                        media_ids,
                    )
                ]

        token = uuid.uuid4().hex[:10]
        work = settings.export_root / f'backup-work-{token}'
        work.mkdir(parents=True, exist_ok=True)
        try:
            media_payload = []
            for media in media_rows:
                source = Path(media['path'])
                if not source.is_file():
                    raise ValueError(f"Media file missing: {media['name']}")
                suffix = source.suffix.lower() or '.bin'
                rel_source = f"media/{media['id']}/source{suffix}"
                target = work / rel_source
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                frames_rel = None
                frames_dir = media.get('frames_dir')
                if frames_dir:
                    frames_path = Path(frames_dir)
                    if frames_path.is_dir() and any(frames_path.iterdir()):
                        frames_rel = f"media/{media['id']}/frames"
                        shutil.copytree(frames_path, work / frames_rel)
                media_payload.append(
                    {
                        'id': media['id'],
                        'name': media['name'],
                        'kind': media['kind'],
                        'width': media['width'],
                        'height': media['height'],
                        'frame_count': media['frame_count'],
                        'fps': media['fps'],
                        'source_fps': media.get('source_fps'),
                        'source_frame_count': media.get('source_frame_count'),
                        'extract_fps': media.get('extract_fps'),
                        'extract_status': media.get('extract_status') or 'ready',
                        'annotation_complete': int(media.get('annotation_complete') or 0),
                        'annotation_seconds': int(media.get('annotation_seconds') or 0),
                        'content_hash': media.get('content_hash'),
                        'source': rel_source,
                        'frames': frames_rel,
                    }
                )

            annotations_payload = []
            for annotation in annotation_rows:
                mask_path = Path(annotation['mask_path'])
                rel_mask = f"masks/{annotation['id']}.png"
                if mask_path.is_file():
                    mask_dest = work / rel_mask
                    mask_dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(mask_path, mask_dest)
                annotations_payload.append(
                    {
                        'id': annotation['id'],
                        'media_id': annotation['media_id'],
                        'frame': annotation['frame'],
                        'label_id': annotation['label_id'],
                        'source': annotation['source'],
                        'track_group': annotation.get('track_group'),
                        'mask': rel_mask,
                    }
                )

            payload = {
                'format': BACKUP_FORMAT,
                'project': {
                    'name': project['name'],
                    'description': project.get('description') or '',
                },
                'labels': labels,
                'media': media_payload,
                'excluded_frames': excluded_rows,
                'annotations': annotations_payload,
            }
            (work / 'backup.json').write_text(
                json.dumps(payload, indent=2), encoding='utf-8'
            )
            stem = project.get('slug') or Path(project['name']).stem or 'project'
            output = settings.export_root / f'{stem}-backup-{token}.zip'
            with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                for path in work.rglob('*'):
                    if path.is_file():
                        archive.write(path, path.relative_to(work).as_posix())
            return output
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def restore_upload(self, uploaded) -> dict:
        dest = settings.export_root / f'import-{uuid.uuid4().hex[:10]}.zip'
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with dest.open('wb') as handle:
                shutil.copyfileobj(uploaded.file, handle)
            return self.restore(dest)
        finally:
            dest.unlink(missing_ok=True)

    def restore(self, zip_path: Path) -> dict:
        work = settings.export_root / f'import-work-{uuid.uuid4().hex[:10]}'
        work.mkdir(parents=True, exist_ok=True)
        created_id = None
        try:
            with zipfile.ZipFile(zip_path) as archive:
                self._extract_safe(archive, work)
            payload = self._read_payload(work)
            from app.services.project_service import project_service

            with db() as conn:
                existing = [row['name'] for row in conn.execute('SELECT name FROM projects')]
            name = allocate_name(existing, payload['project'].get('name') or 'Project')
            created = project_service.create(
                name,
                payload['project'].get('description') or '',
                seed_defaults=False,
            )
            created_id = created['id']
            self._restore_into(created_id, payload, work)
            return project_service.get(created_id)
        except Exception:
            if created_id is not None:
                from app.services.project_service import project_service
                project_service.delete(created_id)
            raise
        finally:
            shutil.rmtree(work, ignore_errors=True)

    def _read_payload(self, work: Path) -> dict:
        backup_path = work / 'backup.json'
        if not backup_path.is_file():
            if (work / 'project.json').is_file():
                raise ValueError(
                    'This is a dataset export, not a recovery backup. '
                    'Use the backup downloaded when deleting a project.'
                )
            raise ValueError('Not a recovery backup')
        payload = json.loads(backup_path.read_text(encoding='utf-8'))
        fmt = payload.get('format')
        if fmt != BACKUP_FORMAT:
            if fmt == 'sewer-annotator-v2':
                raise ValueError(
                    'This is a dataset export, not a recovery backup. '
                    'Use the backup downloaded when deleting a project.'
                )
            raise ValueError('Not a recovery backup')
        return payload

    def _restore_into(self, project_id: int, payload: dict, work: Path):
        folder = settings.media_root / str(project_id)
        folder.mkdir(parents=True, exist_ok=True)
        label_map = {}
        media_map = {}
        with db() as conn:
            for label in payload.get('labels') or []:
                cur = conn.execute(
                    'INSERT INTO labels(project_id,name,color) VALUES (?,?,?)',
                    (project_id, label['name'], label.get('color') or '#5B8FF9'),
                )
                label_map[label['id']] = cur.lastrowid

            for media in payload.get('media') or []:
                source_rel = media.get('source')
                if not source_rel:
                    raise ValueError(f"Backup is missing the file for {media.get('name')}")
                source = self._safe_join(work, source_rel)
                if not source.is_file():
                    raise ValueError(f"Backup is missing the file for {media.get('name')}")
                suffix = source.suffix.lower() or Path(media.get('name') or '').suffix.lower() or '.bin'
                dest = folder / f'{uuid.uuid4().hex}{suffix}'
                shutil.copy2(source, dest)
                digest = media.get('content_hash') or sha256_file(dest)
                cur = conn.execute(
                    '''INSERT INTO media(
                        project_id, name, kind, path, width, height, frame_count, fps,
                        source_fps, source_frame_count, extract_fps, extract_status,
                        annotation_complete, annotation_seconds, content_hash
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                    (
                        project_id,
                        media['name'],
                        media['kind'],
                        str(dest),
                        media['width'],
                        media['height'],
                        media['frame_count'],
                        media['fps'],
                        media.get('source_fps'),
                        media.get('source_frame_count'),
                        media.get('extract_fps'),
                        media.get('extract_status') or 'ready',
                        int(media.get('annotation_complete') or 0),
                        int(media.get('annotation_seconds') or 0),
                        digest,
                    ),
                )
                new_mid = cur.lastrowid
                media_map[media['id']] = new_mid
                frames_rel = media.get('frames')
                if frames_rel:
                    frames_src = self._safe_join(work, frames_rel)
                    if frames_src.is_dir():
                        frames_dir = dest.parent / f'{new_mid}_frames'
                        shutil.copytree(frames_src, frames_dir)
                        conn.execute(
                            'UPDATE media SET frames_dir=? WHERE id=?',
                            (str(frames_dir), new_mid),
                        )

            for excluded in payload.get('excluded_frames') or []:
                new_mid = media_map.get(excluded['media_id'])
                if new_mid is None:
                    continue
                conn.execute(
                    'INSERT OR IGNORE INTO excluded_frames(media_id, frame) VALUES (?,?)',
                    (new_mid, excluded['frame']),
                )

            for annotation in payload.get('annotations') or []:
                new_mid = media_map.get(annotation['media_id'])
                new_lid = label_map.get(annotation['label_id'])
                if new_mid is None or new_lid is None:
                    raise ValueError('Backup annotation is missing media or label')
                mask_src = self._safe_join(work, annotation['mask'])
                if not mask_src.is_file():
                    raise ValueError('Backup is missing a mask file')
                mask_dir = settings.mask_root / str(new_mid)
                mask_dir.mkdir(parents=True, exist_ok=True)
                mask_dest = mask_dir / f'{uuid.uuid4().hex}.png'
                shutil.copy2(mask_src, mask_dest)
                conn.execute(
                    '''INSERT INTO annotations(
                        media_id, frame, label_id, mask_path, source, track_group
                    ) VALUES (?,?,?,?,?,?)''',
                    (
                        new_mid,
                        annotation['frame'],
                        new_lid,
                        str(mask_dest),
                        annotation.get('source') or 'manual',
                        annotation.get('track_group'),
                    ),
                )

    def _extract_safe(self, archive: zipfile.ZipFile, dest: Path):
        dest = dest.resolve()
        for info in archive.infolist():
            name = info.filename.replace('\\', '/')
            if not name or name.endswith('/'):
                continue
            target = self._safe_join(dest, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, target.open('wb') as handle:
                shutil.copyfileobj(src, handle)

    def _safe_join(self, root: Path, relative: str) -> Path:
        root = root.resolve()
        target = (root / relative).resolve()
        if target != root and root not in target.parents:
            raise ValueError('Invalid backup path')
        return target


backup_service = BackupService()
