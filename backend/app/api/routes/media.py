from fastapi import APIRouter,HTTPException,Query
from fastapi.responses import Response
from pydantic import BaseModel,Field
from app.services.media_service import media_service
router=APIRouter(prefix='/media',tags=['media'])
class ExcludeIn(BaseModel):excluded:bool=True;delete_annotations:bool=False
class ExtractIn(BaseModel):frames_per_second:float=Field(gt=0,le=120)
class TimeIn(BaseModel):seconds:int=Field(ge=0,le=30)
class CompleteIn(BaseModel):annotation_complete:bool
@router.get('/{mid}')
def get(mid:int):
    try:return media_service.get(mid)
    except KeyError as e:raise HTTPException(404,str(e))
@router.get('/{mid}/frame/{frame}')
def frame(mid:int,frame:int,thumb:int|None=Query(None)):
    try:
        im=media_service.frame_rgb(mid,frame)
        if thumb:im.thumbnail((thumb,thumb))
        import io
        out=io.BytesIO();im.save(out,'JPEG',quality=85 if thumb else 92);return Response(out.getvalue(),media_type='image/jpeg',headers={'Cache-Control':'no-store'})
    except Exception as e:raise HTTPException(400,str(e))
@router.get('/{mid}/frames')
def frames(mid:int,start:int=0,limit:int=40):return media_service.frames(mid,start,limit)
@router.post('/{mid}/extract')
def extract(mid:int,x:ExtractIn):
    try:return media_service.extract(mid,x.frames_per_second)
    except KeyError as e:raise HTTPException(404,str(e))
    except ValueError as e:raise HTTPException(400,str(e))
@router.post('/{mid}/frames/{frame}/exclude')
def exclude(mid:int,frame:int,x:ExcludeIn):return media_service.set_excluded(mid,frame,x.excluded,x.delete_annotations)
@router.post('/{mid}/time')
def add_time(mid:int,x:TimeIn):
    try:return media_service.add_annotation_seconds(mid,x.seconds)
    except KeyError as e:raise HTTPException(404,str(e))
@router.patch('/{mid}')
def patch(mid:int,x:CompleteIn):
    try:return media_service.set_complete(mid,x.annotation_complete)
    except KeyError as e:raise HTTPException(404,str(e))
    except ValueError as e:raise HTTPException(400,str(e))
@router.delete('/{mid}')
def delete(mid:int):media_service.delete(mid);return {'ok':True}
