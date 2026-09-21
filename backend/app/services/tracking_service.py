import threading,uuid
from dataclasses import dataclass,field
from concurrent.futures import ThreadPoolExecutor
from app.services.annotation_service import annotation_service
from app.services.media_service import media_service
from app.services.sam2_runtime import sam2_runtime
@dataclass
class Job:
    id:str;media_id:int;annotation_ids:list;start_frame:int;end_frame:int;frame_step:int;replace_auto:bool;status:str='queued';progress:int=0;current_frame:int|None=None;created_annotations:list[int]=field(default_factory=list);removed:int=0;error:str|None=None;cancel_requested:bool=False;lock:threading.Lock=field(default_factory=threading.Lock,repr=False)
    def snapshot(self):
        with self.lock:
            data={k:v for k,v in self.__dict__.items() if k!='lock'}
            data['annotation_id']=self.annotation_ids[0] if self.annotation_ids else None
            return data
class TrackingService:
    def __init__(self):self.jobs={};self.guard=threading.Lock();self.pool=ThreadPoolExecutor(max_workers=1)
    def obj(self,jid):
        with self.guard:j=self.jobs.get(jid)
        if not j:raise KeyError('Tracking job not found')
        return j
    def start(self,mid,aids,start,end,step=5,replace=True):
        if isinstance(aids,int):aids=[aids]
        aids=list(dict.fromkeys(aids))
        if not aids:raise ValueError('At least one seed annotation is required')
        m=media_service.get(mid)
        if start==end:raise ValueError('Target frame must differ from seed')
        if m.get('kind')=='image':
            stills=media_service.project_stills(m['project_id'])
            last=len(stills)-1
            if last<0 or not(0<=start<=last and 0<=end<=last):raise ValueError('Frame out of range')
            if stills[start]['id']!=mid:raise ValueError('From picture must match the seed')
        elif not(0<=start<m['frame_count'] and 0<=end<m['frame_count']):raise ValueError('Frame out of range')
        j=Job(uuid.uuid4().hex,mid,aids,start,end,max(1,step),replace)
        with self.guard:self.jobs[j.id]=j
        self.pool.submit(self._run,j);return j.snapshot()
    def get(self,jid):return self.obj(jid).snapshot()
    def is_busy(self):
        with self.guard:
            return any(job.status in ('queued', 'running') for job in self.jobs.values())
    def cancel(self,jid):
        j=self.obj(jid)
        with j.lock:j.cancel_requested=True
        return j.snapshot()
    def _run(self,j):
        try:
            with j.lock:j.status='running';j.progress=1
            def prog(f,p):
                with j.lock:j.current_frame=f;j.progress=p
            def cancelled():
                with j.lock:return j.cancel_requested
            media=media_service.get(j.media_id)
            stills=media_service.project_stills(media['project_id']) if media.get('kind')=='image' else None
            outputs=sam2_runtime.track(j.media_id,j.annotation_ids,j.start_frame,j.end_frame,j.frame_step,prog,cancelled)
            stopped=cancelled()
            removed=0
            if j.replace_auto:
                by_label={}
                for aid,lid,masks in outputs:
                    if not masks:continue
                    farthest=max(masks,key=lambda frame:abs(frame-j.start_frame))
                    info=by_label.setdefault(lid,{'farthest':farthest,'exclude':[]})
                    info['exclude'].append(aid)
                    if abs(farthest-j.start_frame)>abs(info['farthest']-j.start_frame):info['farthest']=farthest
                for lid,info in by_label.items():
                    if stills:
                        lo,hi=sorted((j.start_frame,info['farthest']))
                        for still in stills[lo:hi+1]:
                            removed+=annotation_service.delete_auto_range(still['id'],lid,0,0,exclude_ids=info['exclude'])
                    else:
                        removed+=annotation_service.delete_auto_range(j.media_id,lid,j.start_frame,info['farthest'],exclude_ids=info['exclude'])
            with j.lock:j.progress=95;j.removed=removed
            created=[]
            farthest_saved=None
            for index,(aid,lid,masks) in enumerate(outputs,start=1):
                if not masks:continue
                group='sam2-%s-%s'%(j.id[:8],index)
                if stills:
                    for frame,mask in sorted(masks.items()):
                        if 0<=frame<len(stills):
                            created.extend(annotation_service.bulk_save(stills[frame]['id'],lid,{0:mask},'auto',group))
                else:
                    created.extend(annotation_service.bulk_save(j.media_id,lid,masks,'auto',group))
                last=max(masks,key=lambda frame:abs(frame-j.start_frame))
                if farthest_saved is None or abs(last-j.start_frame)>abs(farthest_saved-j.start_frame):farthest_saved=last
            with j.lock:
                j.created_annotations=created
                j.status='cancelled' if stopped else 'completed'
                j.progress=100
                j.current_frame=j.end_frame if not stopped else farthest_saved if farthest_saved is not None else j.current_frame
        except InterruptedError:
            with j.lock:j.status='cancelled'
        except Exception as e:
            with j.lock:j.status='failed';j.error=str(e)
tracking_service=TrackingService()
