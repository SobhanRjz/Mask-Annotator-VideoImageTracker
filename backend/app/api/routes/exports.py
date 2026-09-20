from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.services.export_service import export_service

router = APIRouter(prefix='/exports', tags=['exports'])


class ExportIn(BaseModel):
    format: str
    project_ids: list[int] | None = None
    include_unannotated: bool = True
    include_auto: bool = True
    include_manual: bool = True


def _http(exc: Exception):
    if isinstance(exc, KeyError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    raise HTTPException(400, str(exc)) from exc


@router.post('')
def start(body: ExportIn):
    try:
        return export_service.start(
            body.format,
            body.project_ids,
            body.include_unannotated,
            body.include_auto,
            body.include_manual,
        )
    except Exception as exc:
        _http(exc)


@router.get('/projects/{pid}/{fmt}')
def export_sync(
    pid: int,
    fmt: str,
    include_unannotated: bool = True,
    include_auto: bool = True,
    include_manual: bool = True,
):
    try:
        path = export_service.build(
            pid,
            fmt,
            include_unannotated,
            include_auto,
            include_manual,
        )
        return FileResponse(path, filename=path.name, media_type='application/zip')
    except Exception as exc:
        _http(exc)


@router.get('/{jid}/download')
def download(jid: str):
    try:
        job = export_service.get(jid)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    if job['status'] != 'completed' or not job.get('path'):
        raise HTTPException(409, 'Export is not ready')
    return FileResponse(
        job['path'],
        filename=job['filename'] or 'export.zip',
        media_type='application/zip',
    )


@router.get('/{jid}')
def status(jid: str):
    try:
        return export_service.get(jid)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.delete('/{jid}')
def cancel(jid: str):
    try:
        return export_service.cancel(jid)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
