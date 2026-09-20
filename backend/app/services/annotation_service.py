from pathlib import Path
import io,uuid
import numpy as np
from PIL import Image
from app.core.db import db
from app.core.settings import settings
from app.services.media_service import media_service
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
        if old:Path(old['mask_path']).unlink(missing_ok=True)
        return self.get(aid)
    def delete(self,aid):
        a=self.get(aid)
        with db() as c:c.execute('DELETE FROM annotations WHERE id=?',(aid,))
        Path(a['mask_path']).unlink(missing_ok=True)
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
    def thumbnail(self,aid,size=220):
        a=self.get(aid);im=media_service.frame_rgb(a['media_id'],a['frame']).convert('RGBA');mask=self.mask(aid);overlay=np.zeros((mask.shape[0],mask.shape[1],4),dtype=np.uint8);overlay[mask]=[255,72,72,110];im.alpha_composite(Image.fromarray(overlay,'RGBA'));im.thumbnail((size,size));out=io.BytesIO();im.convert('RGB').save(out,'JPEG',quality=85);return out.getvalue()
annotation_service=AnnotationService()
