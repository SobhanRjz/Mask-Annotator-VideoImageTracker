from __future__ import annotations
import gc,tempfile,threading,uuid
from dataclasses import dataclass
from pathlib import Path
import numpy as np,torch
from sam2.sam2_video_predictor import SAM2VideoPredictor
from app.core.settings import settings
from app.services.media_service import media_service
from app.services.annotation_service import annotation_service
from app.utils.images import fit_mask,overlay_png
from app.utils.prompt_points import prompt_arrays
@dataclass
class PromptSession:
    id:str;media_id:int;frame:int;temp_dir:tempfile.TemporaryDirectory;frame_dir:Path;state:dict;width:int;height:int;initial_mask:np.ndarray|None=None
class Sam2Runtime:
    def __init__(self):self.predictor=None;self.lock=threading.RLock();self.sessions={};self.loading=False;self.load_error:str|None=None
    def status(self):
        with self.lock:return {'ready':self.predictor is not None,'loading':self.loading,'error':self.load_error}
    def initialize(self):
        with self.lock:
            if self.predictor is not None or self.loading:return
            self.loading=True;self.load_error=None
        try:
            if not torch.cuda.is_available():raise RuntimeError('CUDA is not available')
            torch.backends.cuda.matmul.allow_tf32=True;torch.backends.cudnn.allow_tf32=True
            print('='*64);print('SEWER SAM2 ANNOTATOR');print('GPU:',torch.cuda.get_device_name(0));print('Model:',settings.model_id);print('='*64)
            predictor=SAM2VideoPredictor.from_pretrained(settings.model_id,device='cuda')
            with self.lock:self.predictor=predictor
            print('SAM2 MODEL LOADED SUCCESSFULLY')
        except Exception as e:
            with self.lock:self.load_error=str(e)
            print('SAM2 LOAD FAILED:',e)
        finally:
            with self.lock:self.loading=False
    def shutdown(self):
        for sid in list(self.sessions):self.close_prompt_session(sid)
        self.predictor=None;self.cleanup()
    def cleanup(self):
        gc.collect()
        if torch.cuda.is_available():torch.cuda.empty_cache()
    def req(self):
        with self.lock:
            if self.load_error:raise RuntimeError(f'SAM2 failed to load: {self.load_error}')
            if self.predictor is None:raise RuntimeError('SAM2 is still loading. Wait until the model is ready, then retry.')
            return self.predictor
    def create_prompt_session(self,mid,frame,aid=None):
        p=self.req()
        with self.lock:
            td=tempfile.TemporaryDirectory(prefix='sam2-prompt-');d=Path(td.name)/'frames';d.mkdir();(d/'000000.jpg').write_bytes(media_service.frame_jpeg(mid,frame,95));m=media_service.get(mid);initial=None
            if aid is not None:
                meta=annotation_service.get(aid)
                if meta['media_id']!=mid or meta['frame']!=frame:td.cleanup();raise ValueError('Annotation does not belong to this frame')
                initial=annotation_service.mask(aid)
            state=p.init_state(video_path=str(d),offload_video_to_cpu=True,offload_state_to_cpu=True,async_loading_frames=False);s=PromptSession(uuid.uuid4().hex,mid,frame,td,d,state,m['width'],m['height'],initial);self.sessions[s.id]=s;return s
    def close_prompt_session(self,sid):
        s=self.sessions.pop(sid,None)
        if not s:return
        try:self.predictor.reset_state(s.state)
        except Exception:pass
        try:s.temp_dir.cleanup()
        except Exception:pass
        self.cleanup()
    def prompt(self,sid,points,box=None,mask=None):
        p=self.req();s=self.sessions.get(sid)
        if not s:raise KeyError('Prompt session expired')
        box_arr=np.asarray(box,np.float32) if box else None
        prompt_mask=fit_mask(mask,s.height,s.width) if mask is not None else s.initial_mask
        coords,labels=prompt_arrays(points,prompt_mask)
        if coords is None and box_arr is None and prompt_mask is None:raise ValueError('Add a positive point, rectangle, or mask')
        with self.lock,torch.inference_mode(),torch.autocast(device_type='cuda',dtype=torch.bfloat16):
            p.reset_state(s.state);logits=None;ids=[1]
            if prompt_mask is not None:_,ids,logits=p.add_new_mask(inference_state=s.state,frame_idx=0,obj_id=1,mask=prompt_mask)
            if coords is not None or box_arr is not None:_,ids,logits=p.add_new_points_or_box(inference_state=s.state,frame_idx=0,obj_id=1,points=coords,labels=labels,box=box_arr,clear_old_points=True,normalize_coords=True)
            mask=(logits[list(ids).index(1),0]>0).detach().cpu().numpy().astype(bool);return overlay_png(mask)
    def track(self,mid,aids,start,end,step,progress,cancel):
        p=self.req()
        if isinstance(aids,int):aids=[aids]
        seeds=[annotation_service.get(aid) for aid in aids]
        if not seeds:raise ValueError('At least one seed annotation is required')
        for meta in seeds:
            if meta['media_id']!=mid or meta['frame']!=start:raise ValueError('Seed annotation/frame mismatch')
        lo,hi=sorted((start,end));reverse=end<start;seed_local=start-lo;td=None;state=None
        empty=[(meta['id'],meta['label_id'],{}) for meta in seeds]
        try:
            with self.lock:
                td=tempfile.TemporaryDirectory(prefix='sam2-track-');d=Path(td.name)/'frames';d.mkdir()
                for local,f in enumerate(range(lo,hi+1)):
                    if cancel():return empty
                    (d/f'{local:06d}.jpg').write_bytes(media_service.frame_jpeg(mid,f,settings.jpeg_quality))
                state=p.init_state(video_path=str(d),offload_video_to_cpu=True,offload_state_to_cpu=True,async_loading_frames=True);results={meta['id']:{} for meta in seeds};total=abs(end-start)+1;done=0
                with torch.inference_mode(),torch.autocast(device_type='cuda',dtype=torch.bfloat16):
                    obj_to_aid={}
                    for index,meta in enumerate(seeds,start=1):
                        p.add_new_mask(inference_state=state,frame_idx=seed_local,obj_id=index,mask=annotation_service.mask(meta['id']));obj_to_aid[index]=meta['id']
                    for local,ids,logits in p.propagate_in_video(inference_state=state,start_frame_idx=seed_local,max_frame_num_to_track=abs(end-start),reverse=reverse):
                        if cancel():break
                        f=lo+int(local);done+=1;progress(f,min(90,int(done/total*90)))
                        if f==start:continue
                        if abs(f-start)%max(1,step)!=0 and f!=end:continue
                        ids=list(ids)
                        for obj_id,aid in obj_to_aid.items():
                            if obj_id not in ids:continue
                            mask=(logits[ids.index(obj_id),0]>0).detach().cpu().numpy().astype(bool)
                            if mask.any():results[aid][f]=mask
                return [(meta['id'],meta['label_id'],results[meta['id']]) for meta in seeds]
        finally:
            if state is not None:
                try:p.reset_state(state)
                except Exception:pass
            if td:
                try:td.cleanup()
                except Exception:pass
            self.cleanup()
sam2_runtime=Sam2Runtime()
