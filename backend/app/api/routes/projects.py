from fastapi import APIRouter,HTTPException,UploadFile,File
from fastapi.responses import FileResponse
from pydantic import BaseModel
from app.services.project_service import project_service
from app.services.media_service import media_service
from app.services.backup_service import backup_service
router=APIRouter(prefix='/projects',tags=['projects'])
class ProjectIn(BaseModel):name:str;description:str=''
class DefectLabelIn(BaseModel):name:str;color:str|None=None
class DefectCatalogIn(BaseModel):labels:list[DefectLabelIn]=[]
class ImagesCompleteIn(BaseModel):annotation_complete:bool

def pid_of(ref:str)->int:
    try:return project_service.resolve_id(ref)
    except KeyError as e:raise HTTPException(404,str(e))

def _http(exc:Exception):
    if isinstance(exc,KeyError):
        raise HTTPException(404,str(exc)) from exc
    if isinstance(exc,ValueError):
        raise HTTPException(400,str(exc)) from exc
    raise HTTPException(400,str(exc)) from exc

@router.get('')
def ls():return project_service.list()
@router.post('')
def create(x:ProjectIn):
    try:return project_service.create(x.name,x.description)
    except ValueError as e:
        raise HTTPException(409 if 'already exists' in str(e) else 400,str(e))
@router.post('/backup')
def import_backup(file:UploadFile=File(...)):
    try:return backup_service.restore_upload(file)
    except Exception as e:_http(e)
@router.get('/catalog/labels')
def defect_labels():return project_service.defect_labels()
@router.put('/catalog/labels')
def put_defect_labels(x:DefectCatalogIn):
    try:return project_service.save_defect_labels([{'name':item.name,'color':item.color} for item in x.labels])
    except ValueError as e:raise HTTPException(400,str(e))
@router.get('/{pid}')
def get(pid:str):
    try:return project_service.get(pid)
    except KeyError as e:raise HTTPException(404,str(e))
@router.get('/{pid}/backup')
def download_backup(pid:str):
    try:
        path=backup_service.build(pid_of(pid))
    except Exception as e:_http(e)
    return FileResponse(path,filename=path.name,media_type='application/zip')
@router.delete('/{pid}')
def delete(pid:str):project_service.delete(pid_of(pid));return {'ok':True}
@router.post('/{pid}/media')
def upload(pid:str,files:list[UploadFile]=File(...)):return media_service.upload(pid_of(pid),files)
@router.patch('/{pid}/images/complete')
def images_complete(pid:str,x:ImagesCompleteIn):
    try:return media_service.set_project_images_complete(pid_of(pid),x.annotation_complete)
    except ValueError as e:raise HTTPException(400,str(e))
@router.delete('/{pid}/images')
def delete_images(pid:str):return media_service.delete_project_images(pid_of(pid))
