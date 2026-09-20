from fastapi import APIRouter,HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from app.services.annotation_service import annotation_service
from app.utils.images import data_url_to_mask,overlay_png
router=APIRouter(prefix='/annotations',tags=['annotations'])
class SaveIn(BaseModel):media_id:int;frame:int;label_id:int;mask_png_data_url:str;replace_annotation_id:int|None=None;source:str='manual'
@router.get('/media/{mid}')
def ls(mid:int,frame:int|None=None,limit:int=500):return annotation_service.list(mid,frame,limit)
@router.get('/{aid}/mask.png')
def mask(aid:int):return Response(overlay_png(annotation_service.mask(aid)),media_type='image/png',headers={'Cache-Control':'no-store'})
@router.get('/{aid}/thumbnail.jpg')
def thumb(aid:int):return Response(annotation_service.thumbnail(aid),media_type='image/jpeg',headers={'Cache-Control':'no-store'})
@router.post('/masks')
def save(x:SaveIn):
    try:return annotation_service.save(x.media_id,x.frame,x.label_id,data_url_to_mask(x.mask_png_data_url),x.source,x.replace_annotation_id)
    except Exception as e:raise HTTPException(400,str(e))
@router.delete('/{aid}')
def delete(aid:int):annotation_service.delete(aid);return {'ok':True}
