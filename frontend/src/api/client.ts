import type {Annotation,BoxPrompt,DashboardStats,ExportFormat,ExportJob,FrameInfo,Media,ModelSettings,ModelSwitchJob,Project,ProjectSummary,PromptPoint,TrackingJob,TrackingSettings} from '../types';
const API='/api';
async function req<T>(url:string,init?:RequestInit):Promise<T>{const r=await fetch(url,init);if(!r.ok){let m=`${r.status} ${r.statusText}`;try{const b=await r.json();m=b.detail??m}catch{}throw new Error(m)}return r.json() as Promise<T>}
export const frameUrl=(mid:number,f:number,thumb?:number)=>`${API}/media/${mid}/frame/${f}${thumb?`?thumb=${thumb}`:''}`;
export const annotationMaskUrl=(id:number)=>`${API}/annotations/${id}/mask.png?v=${Date.now()}`;
export const annotationThumbUrl=(id:number)=>`${API}/annotations/${id}/thumbnail.jpg?v=${Date.now()}`;
export const listProjects=()=>req<ProjectSummary[]>(`${API}/projects`);
export const createProject=(name:string,description='')=>req<Project>(`${API}/projects`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,description})});
export const getProject=(ref:string|number)=>req<Project>(`${API}/projects/${ref}`);
export const deleteProject=(ref:string|number)=>req(`${API}/projects/${ref}`,{method:'DELETE'});
export async function downloadProjectBackup(ref:string|number,filename:string){
  const response=await fetch(`${API}/projects/${ref}/backup`);
  if(!response.ok){
    let message=`${response.status} ${response.statusText}`;
    try{const body=await response.json();message=body.detail??message}catch{}
    throw new Error(message);
  }
  const header=response.headers.get('content-disposition')||'';
  const match=/filename="?([^"]+)"?/i.exec(header);
  const blob=await response.blob();
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');
  link.href=url;
  link.download=match?.[1]||filename||'project-backup.zip';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
export async function importProjectBackup(file:File){
  const fd=new FormData();
  fd.append('file',file);
  return req<Project>(`${API}/projects/backup`,{method:'POST',body:fd});
}
export const getStats=()=>req<DashboardStats>(`${API}/stats`);
export const getModelSettings=()=>req<ModelSettings>(`${API}/settings/model`);
export const switchSamModel=(key:string)=>req<ModelSwitchJob>(`${API}/settings/model`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});
export const modelSwitchStatus=(id:string)=>req<ModelSwitchJob>(`${API}/settings/model/jobs/${id}`);
export const getTrackingSettings=()=>req<TrackingSettings>(`${API}/settings/tracking`);
export const saveTrackingSettings=(track_patch_size:number)=>req<TrackingSettings>(`${API}/settings/tracking`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({track_patch_size})});
export async function uploadMedia(pid:number,files:File[]){const fd=new FormData();files.forEach(f=>fd.append('files',f));return req<Media[]>(`${API}/projects/${pid}/media`,{method:'POST',body:fd})}
export const extractMedia=(mid:number,framesPerSecond:number)=>req<Media>(`${API}/media/${mid}/extract`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({frames_per_second:framesPerSecond})});
export const addLabel=(pid:number,name:string,color:string)=>req(`${API}/projects/${pid}/labels`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,color})});
export const updateLabel=(pid:number,lid:number,patch:{name?:string;color?:string})=>req(`${API}/projects/${pid}/labels/${lid}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)});
export const deleteLabel=(pid:number,lid:number)=>req(`${API}/projects/${pid}/labels/${lid}`,{method:'DELETE'});
export const getFrames=(mid:number,start=0,limit=20000)=>req<FrameInfo[]>(`${API}/media/${mid}/frames?start=${Math.max(0,start)}&limit=${limit}`);
export const excludeFrame=(mid:number,frame:number,excluded:boolean,del=false)=>req(`${API}/media/${mid}/frames/${frame}/exclude`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({excluded,delete_annotations:del})});
export const deleteMedia=(mid:number)=>req(`${API}/media/${mid}`,{method:'DELETE'});
export const setMediaComplete=(mid:number,annotation_complete:boolean)=>req<Media>(`${API}/media/${mid}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({annotation_complete})});
export const setProjectImagesComplete=(ref:string|number,annotation_complete:boolean)=>req<{annotation_complete:boolean;updated:number}>(`${API}/projects/${ref}/images/complete`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({annotation_complete})});
export const deleteProjectImages=(ref:string|number)=>req<{ok:boolean;deleted:number}>(`${API}/projects/${ref}/images`,{method:'DELETE'});
export const addAnnotationTime=(mid:number,seconds:number)=>req<{annotation_seconds:number;project_annotation_seconds:number}>(`${API}/media/${mid}/time`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seconds})});
export const listAnnotations=(mid:number,frame?:number,limit=500)=>req<Annotation[]>(`${API}/annotations/media/${mid}?${frame===undefined?'':`frame=${frame}&`}limit=${limit}`);
export async function getMaskBlob(id:number){const r=await fetch(annotationMaskUrl(id));if(!r.ok)throw new Error('Cannot load mask');return r.blob()}
export const deleteAnnotation=(id:number)=>req(`${API}/annotations/${id}`,{method:'DELETE'});
export const saveMask=(x:{mediaId:number;frame:number;labelId:number;maskDataUrl:string;replaceId?:number|null;source?:string})=>req<Annotation>(`${API}/annotations/masks`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({media_id:x.mediaId,frame:x.frame,label_id:x.labelId,mask_png_data_url:x.maskDataUrl,replace_annotation_id:x.replaceId??null,source:x.source??'manual'})});
export const createPrompt=(mid:number,frame:number,aid?:number|null)=>req<{session_id:string;width:number;height:number}>(`${API}/prompts/sessions`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({media_id:mid,frame,annotation_id:aid??null})});
export const closePrompt=(sid:string)=>fetch(`${API}/prompts/sessions/${sid}`,{method:'DELETE'});
export async function predictPrompt(sid:string,points:PromptPoint[],box:BoxPrompt|null,maskDataUrl?:string|null){const r=await fetch(`${API}/prompts/sessions/${sid}/predict`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({points,box,mask_png_data_url:maskDataUrl??null})});if(!r.ok){const b=await r.json().catch(()=>({}));throw new Error(b.detail??'SAM2 prompt failed')}return r.blob()}
export const startTracking=(x:{mediaId:number;annotationIds:number[];startFrame:number;endFrame:number;frameStep:number;replace:boolean})=>req<TrackingJob>(`${API}/tracking`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({media_id:x.mediaId,annotation_ids:x.annotationIds,annotation_id:x.annotationIds[0],start_frame:x.startFrame,end_frame:x.endFrame,frame_step:x.frameStep,replace_auto_masks:x.replace})});
export const trackingStatus=(id:string)=>req<TrackingJob>(`${API}/tracking/${id}`);
export const cancelTracking=(id:string)=>req<TrackingJob>(`${API}/tracking/${id}`,{method:'DELETE'});
export const exportUrl=(pid:number,fmt:ExportFormat)=>`${API}/exports/projects/${pid}/${fmt}`;
export const startExport=(body:{
  format:ExportFormat;
  project_ids:number[]|null;
  include_unannotated:boolean;
  include_auto:boolean;
  include_manual:boolean;
})=>req<ExportJob>(`${API}/exports`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
export const exportStatus=(id:string)=>req<ExportJob>(`${API}/exports/${id}`);
export const cancelExport=(id:string)=>req<ExportJob>(`${API}/exports/${id}`,{method:'DELETE'});
export async function downloadExport(id:string,filename:string){
  const response=await fetch(`${API}/exports/${id}/download`);
  if(!response.ok){
    let message=`${response.status} ${response.statusText}`;
    try{const body=await response.json();message=body.detail??message}catch{}
    throw new Error(message);
  }
  const blob=await response.blob();
  const url=URL.createObjectURL(blob);
  const link=document.createElement('a');
  link.href=url;
  link.download=filename||'export.zip';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
