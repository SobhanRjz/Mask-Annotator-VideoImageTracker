from pathlib import Path
import io,uuid
import numpy as np
from PIL import Image
from app.core.db import db
from app.core.settings import settings
from app.services.media_service import media_service
from app.services.stats_service import stats_service
from app.utils.images import save_mask,load_mask
class AnnotationService:
    def list(self,mid,frame=None,limit=500):
        q='''SELECT a.*,l.name label_name,l.color label_color FROM annotations a JOIN labels l ON l.id=a.label_id WHERE a.media_id=?''';args=[mid]
        if frame is not None:q+=' AND a.frame=?';args.append(frame)
        q+=' ORDER BY a.frame,a.id LIMIT ?';args.append(limit)
        with db() as c:return [dict(r) for r in c.execute(q,args)]
    def get(self,aid):
        with db() as c:
            r=c.execute('''SELECT a.*,l.name label_name,l.color label_color FROM annotations a JOIN labels l ON l.id=a.label_id WHERE a.id=?''',(aid,)).fetchone()
            if not r:raise KeyError('Annotation not found')
            return dict(r)
    def mask(self,aid):return load_mask(self.get(aid)['mask_path'])
    def save(self,mid,frame,lid,mask,source='manual',replace_id=None,track_group=None):
        m=media_service.get(mid);mask=np.asarray(mask,dtype=bool)
        if mask.shape!=(m['height'],m['width']):mask=np.asarray(Image.fromarray(mask.astype('uint8')*255).resize((m['width'],m['height']),Image.Resampling.NEAREST))>127
        if not mask.any():raise ValueError('Mask is empty')
        folder=settings.mask_root/str(mid);folder.mkdir(parents=True,exist_ok=True);path=folder/f'{uuid.uuid4().hex}.png';save_mask(path,mask);old=None
        with db() as c:
            if replace_id:
                old=c.execute('SELECT mask_path FROM annotations WHERE id=? AND media_id=?',(replace_id,mid)).fetchone();c.execute('UPDATE annotations SET frame=?,label_id=?,mask_path=?,source=?,track_group=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND media_id=?',(frame,lid,str(path),source,track_group,replace_id,mid));aid=replace_id
            else:
                cur=c.execute('INSERT INTO annotations(media_id,frame,label_id,mask_path,source,track_group) VALUES (?,?,?,?,?,?)',(mid,frame,lid,str(path),source,track_group));aid=cur.lastrowid
            c.execute('DELETE FROM healthy_frames WHERE media_id=? AND frame=?',(mid,frame))
        if old:Path(old['mask_path']).unlink(missing_ok=True)
        try:stats_service.remember_mask(path,mask)
        except Exception:pass # dashboard cache only; the dashboard backfills on a miss
        return self.get(aid)
    def delete(self,aid):
        a=self.get(aid)
        with db() as c:c.execute('DELETE FROM annotations WHERE id=?',(aid,))
        Path(a['mask_path']).unlink(missing_ok=True)
    def clear_frames(self,mid,frames):
        selected=sorted({int(frame) for frame in frames})
        if not selected:return {'deleted':0,'frames':[]}
        placeholders=','.join('?'*len(selected))
        with db() as c:
            rows=c.execute(
                f'''SELECT id,mask_path FROM annotations
                    WHERE media_id=? AND frame IN ({placeholders})''',
                [mid,*selected],
            ).fetchall()
            if rows:
                c.execute(
                    f'''DELETE FROM annotations
                        WHERE media_id=? AND frame IN ({placeholders})''',
                    [mid,*selected],
                )
        for row in rows:
            Path(row['mask_path']).unlink(missing_ok=True)
        return {'deleted':len(rows),'frames':selected}
    def delete_auto_range(self,mid,lid,a,b,exclude_id=None,exclude_ids=None):
        lo,hi=sorted((a,b));args=[mid,lid,'auto',lo,hi];q='SELECT id,mask_path FROM annotations WHERE media_id=? AND label_id=? AND source=? AND frame BETWEEN ? AND ?'
        excluded=[]
        if exclude_ids:excluded.extend(exclude_ids)
        elif exclude_id is not None:excluded.append(exclude_id)
        if excluded:
            q+=' AND id NOT IN (%s)'%','.join('?'*len(excluded));args.extend(excluded)
        with db() as c:
            rows=c.execute(q,args).fetchall()
            if rows:c.execute('DELETE FROM annotations WHERE id IN (%s)'%','.join('?'*len(rows)),[r['id'] for r in rows])
        for r in rows:Path(r['mask_path']).unlink(missing_ok=True)
        return len(rows)
    def bulk_save(self,mid,lid,masks,source='auto',track_group=None):
        with db() as c:manual={r['frame'] for r in c.execute('SELECT frame FROM annotations WHERE media_id=? AND label_id=? AND source<>?',(mid,lid,'auto'))}
        return [self.save(mid,f,lid,m,source,None,track_group)['id'] for f,m in sorted(masks.items()) if f not in manual]
    def require_full_label(self,lid,project_id):
        with db() as c:
            row=c.execute('SELECT id,kind,name FROM labels WHERE id=? AND project_id=?',(lid,project_id)).fetchone()
        if not row or row['kind']!='full':raise ValueError('Choose Healthy or Loss of view')
        return dict(row)
    def save_full_frame(self,mid,frame,lid,source='manual',track_group=None,replace_others=True):
        media=media_service.get(mid)
        frame=int(frame)
        count=int(media['frame_count'] or 0)
        if frame<0 or frame>=count:raise ValueError('Frame is out of range')
        self.require_full_label(lid,media['project_id'])
        existing=self.list(mid,frame)
        same=[item for item in existing if item['label_id']==lid]
        for item in same[1:]:self.delete(item['id'])
        if replace_others:
            for item in existing:
                if item['label_id']!=lid:self.delete(item['id'])
        mask=np.ones((int(media['height']),int(media['width'])),dtype=bool)
        return self.save(mid,frame,lid,mask,source,same[0]['id'] if same else None,track_group)
    def fill_full_frames(self,mid,lid,start,end,step=5,replace_auto=True,track_group=None,progress=None,cancelled=None):
        media=media_service.get(mid)
        self.require_full_label(lid,media['project_id'])
        stills=media_service.project_stills(media['project_id']) if media.get('kind')=='image' else None
        frames=_stride_frames(start,end,step)
        created=[];stopped=False;total=max(1,len(frames))
        for index,frame in enumerate(frames):
            if cancelled and cancelled():
                stopped=True;break
            if progress:progress(frame,min(95,int(100*(index+1)/total)))
            if stills:
                if not 0<=frame<len(stills):continue
                target_media=stills[frame]['id'];target_frame=0
            else:
                target_media=mid;target_frame=frame
            if self._excluded(target_media,target_frame):continue
            if not self._can_fill(target_media,target_frame,lid,replace_auto):continue
            if replace_auto:self._delete_auto_frame(target_media,target_frame)
            created.append(self.save_full_frame(target_media,target_frame,lid,'auto',track_group,False)['id'])
        return created,stopped
    def _excluded(self,mid,frame):
        with db() as c:return c.execute('SELECT 1 FROM excluded_frames WHERE media_id=? AND frame=?',(mid,frame)).fetchone() is not None
    def _can_fill(self,mid,frame,lid,replace_auto):
        rows=self.list(mid,frame)
        manual=[row for row in rows if row['source']!='auto']
        if any(row['label_id']!=lid for row in manual):return False
        if any(row['label_id']==lid for row in manual):return False
        if not replace_auto and rows:return False
        return True
    def _delete_auto_frame(self,mid,frame):
        with db() as c:
            rows=c.execute("SELECT id,mask_path FROM annotations WHERE media_id=? AND frame=? AND source='auto'",(mid,frame)).fetchall()
            if rows:c.execute('DELETE FROM annotations WHERE id IN (%s)'%','.join('?'*len(rows)),[row['id'] for row in rows])
        for row in rows:Path(row['mask_path']).unlink(missing_ok=True)
    def thumbnail(self,aid,size=220):
        a=self.get(aid);im=media_service.frame_rgb(a['media_id'],a['frame']).convert('RGBA');mask=self.mask(aid);overlay=np.zeros((mask.shape[0],mask.shape[1],4),dtype=np.uint8);overlay[mask]=[255,72,72,110];im.alpha_composite(Image.fromarray(overlay,'RGBA'));im.thumbnail((size,size));out=io.BytesIO();im.convert('RGB').save(out,'JPEG',quality=85);return out.getvalue()
def _stride_frames(start,end,step):
    step=max(1,int(step))
    if start==end:return [int(start)]
    direction=1 if end>start else -1
    frames=[];frame=int(start);end=int(end)
    while True:
        frames.append(frame)
        if frame==end:break
        nxt=frame+direction*step
        if (direction==1 and nxt>=end) or (direction==-1 and nxt<=end):
            if frames[-1]!=end:frames.append(end)
            break
        frame=nxt
    return frames
annotation_service=AnnotationService()
