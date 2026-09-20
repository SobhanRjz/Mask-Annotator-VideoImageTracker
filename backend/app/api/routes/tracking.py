from fastapi import APIRouter,HTTPException
from pydantic import BaseModel,Field
from app.services.tracking_service import tracking_service
from app.services.sam2_runtime import sam2_runtime
router=APIRouter(prefix='/tracking',tags=['tracking'])
class TrackIn(BaseModel):media_id:int;annotation_id:int|None=None;annotation_ids:list[int]|None=None;start_frame:int;end_frame:int;frame_step:int=Field(1,ge=1,le=60);replace_auto_masks:bool=True
@router.post('')
def start(x:TrackIn):
    try:
        sam2_runtime.req()
        aids=list(x.annotation_ids or [])
        if x.annotation_id is not None and x.annotation_id not in aids:aids.insert(0,x.annotation_id)
        return tracking_service.start(x.media_id,aids,x.start_frame,x.end_frame,x.frame_step,x.replace_auto_masks)
    except RuntimeError as e:raise HTTPException(503,str(e))
    except ValueError as e:raise HTTPException(400,str(e))
@router.get('/{jid}')
def status(jid:str):return tracking_service.get(jid)
@router.delete('/{jid}')
def cancel(jid:str):return tracking_service.cancel(jid)
