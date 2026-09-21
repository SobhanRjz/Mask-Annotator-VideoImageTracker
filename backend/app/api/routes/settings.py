from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.model_service import ModelSwitchBusy, model_service
from app.services.track_settings import (
    DEFAULT_PATCH,
    MAX_PATCH,
    MIN_PATCH,
    get_patch,
    set_patch,
)

router = APIRouter(prefix='/settings', tags=['settings'])


class ModelIn(BaseModel):
    key: str


class TrackingIn(BaseModel):
    track_patch_size: int = Field(..., ge=MIN_PATCH, le=MAX_PATCH)


def _http(exc: Exception):
    if isinstance(exc, ModelSwitchBusy):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, KeyError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, ValueError):
        raise HTTPException(400, str(exc)) from exc
    raise HTTPException(400, str(exc)) from exc


@router.get('/model')
def status():
    return model_service.status()


@router.post('/model')
def start(body: ModelIn):
    try:
        return model_service.start(body.key)
    except Exception as exc:
        _http(exc)


@router.get('/model/jobs/{job_id}')
def job(job_id: str):
    try:
        return model_service.get(job_id)
    except Exception as exc:
        _http(exc)


@router.get('/tracking')
def tracking_status():
    return {
        'track_patch_size': get_patch(),
        'min': MIN_PATCH,
        'max': MAX_PATCH,
        'default': DEFAULT_PATCH,
    }


@router.post('/tracking')
def tracking_save(body: TrackingIn):
    try:
        size = set_patch(body.track_patch_size)
    except Exception as exc:
        _http(exc)
    return {
        'track_patch_size': size,
        'min': MIN_PATCH,
        'max': MAX_PATCH,
        'default': DEFAULT_PATCH,
    }
