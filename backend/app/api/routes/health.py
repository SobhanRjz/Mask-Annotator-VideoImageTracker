import torch
from fastapi import APIRouter, HTTPException

from app.core.settings import settings
from app.services.cvat_service import cvat_service
from app.services.sam2_runtime import sam2_runtime

router = APIRouter(tags=["health"])


@router.get("/health")
def health():
    return {
        "status": "ok",
        "model": settings.model_id,
        "model_loaded": sam2_runtime.predictor is not None,
        "cuda": torch.cuda.is_available(),
        "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
        "allocated_vram_mb": round(torch.cuda.memory_allocated(0) / 1024 / 1024, 2)
        if torch.cuda.is_available()
        else 0,
    }


@router.get("/cvat/me")
def cvat_me():
    try:
        return cvat_service.current_user()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
