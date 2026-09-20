from fastapi import APIRouter,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel,Field
from app.services.sam2_runtime import sam2_runtime
from app.utils.images import data_url_to_mask
router=APIRouter(prefix='/prompts',tags=['prompts'])
class SessionIn(BaseModel):media_id:int;frame:int;annotation_id:int|None=None
class Point(BaseModel):x:float;y:float;positive:bool=True
class PredictIn(BaseModel):points:list[Point]=Field(default_factory=list);box:list[float]|None=None;mask_png_data_url:str|None=None
@router.post('/sessions')
def create(x:SessionIn):
    try:
        s=sam2_runtime.create_prompt_session(x.media_id,x.frame,x.annotation_id);return {'session_id':s.id,'width':s.width,'height':s.height}
    except RuntimeError as e:raise HTTPException(503,str(e))
    except Exception as e:raise HTTPException(400,str(e))
@router.delete('/sessions/{sid}')
def close(sid:str):sam2_runtime.close_prompt_session(sid);return {'ok':True}
@router.post('/sessions/{sid}/predict')
def predict(sid:str,x:PredictIn):
    try:
        mask=data_url_to_mask(x.mask_png_data_url) if x.mask_png_data_url else None
        return Response(sam2_runtime.prompt(sid,[p.model_dump() for p in x.points],x.box,mask),media_type='image/png',headers={'Cache-Control':'no-store'})
    except RuntimeError as e:raise HTTPException(503,str(e))
    except Exception as e:raise HTTPException(400,str(e))
