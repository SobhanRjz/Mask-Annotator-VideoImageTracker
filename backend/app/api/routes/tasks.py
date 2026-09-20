from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.services.cvat_service import cvat_service
from app.utils.images import bool_mask_to_overlay_png

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}")
def task_info(task_id: int):
    try:
        return cvat_service.task_info(task_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{task_id}/frames/{frame}")
def task_frame(task_id: int, frame: int):
    try:
        jpeg, _, _ = cvat_service.frame_jpeg(task_id, frame)
        return Response(content=jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"})
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{task_id}/masks")
def list_masks(task_id: int, frame: int | None = Query(default=None, ge=0)):
    try:
        return {"masks": cvat_service.list_masks(task_id, frame)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/{task_id}/masks/{shape_id}/png")
def mask_png(task_id: int, shape_id: int):
    try:
        mask, _ = cvat_service.get_mask(task_id, shape_id)
        return Response(
            content=bool_mask_to_overlay_png(mask),
            media_type="image/png",
            headers={"Cache-Control": "no-store"},
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
