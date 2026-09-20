import sqlite3
import shutil
from app.core.db import db
from app.core.settings import settings
from app.services.media_service import enrich
from app.utils.colors import ensure_unique, unique_color
from app.utils.slugs import allocate_slug
class ProjectService:
    def list(self):
        sql='''SELECT p.*, (SELECT COUNT(*) FROM media m WHERE m.project_id=p.id) media_count, (SELECT COUNT(*) FROM annotations a JOIN media m2 ON m2.id=a.media_id WHERE m2.project_id=p.id) annotation_count, (SELECT COALESCE(SUM(m.annotation_seconds),0) FROM media m WHERE m.project_id=p.id) annotation_seconds, (SELECT m.id FROM media m WHERE m.project_id=p.id AND (m.kind='image' OR m.extract_status='ready') ORDER BY m.id DESC LIMIT 1) cover_media_id FROM projects p ORDER BY p.updated_at DESC,p.id DESC'''
        with db() as c:return [dict(r) for r in c.execute(sql)]
    def resolve_id(self,ref):
        text=str(ref).strip()
        if not text:raise KeyError('Project not found')
        with db() as c:
            row=c.execute('SELECT id FROM projects WHERE slug=?',(text,)).fetchone()
            if row:return row['id']
            if text.isdigit():
                row=c.execute('SELECT id FROM projects WHERE id=?',(int(text),)).fetchone()
                if row:return row['id']
        raise KeyError('Project not found')
    def create(self,name,description='',seed_defaults=True):
        name=name.strip();description=description.strip()
        if not name:raise ValueError('Project name is required')
        with db() as c:
            existing=[row['slug'] for row in c.execute('SELECT slug FROM projects')]
            slug=allocate_slug(existing,name)
            try:
                cur=c.execute('INSERT INTO projects(name,slug,description) VALUES (?,?,?)',(name,slug,description));pid=cur.lastrowid
            except sqlite3.IntegrityError as exc:
                raise ValueError(f'A project named "{name}" already exists') from exc
            if seed_defaults:
                defaults=[('Root','#51B56D'),('Crack','#E45B5B'),('Obstacle','#F29D49'),('Deposits','#9A73E8'),('Deformed','#4FA3E3'),('Broken','#D85883'),('Joint Displaced','#D4B03D'),('Surface Damage','#5FC6B0')]
                c.executemany('INSERT INTO labels(project_id,name,color) VALUES (?,?,?)',[(pid,*x) for x in defaults])
        (settings.media_root/str(pid)).mkdir(parents=True,exist_ok=True);return self.get(pid)
    def get(self,ref):
        pid=self.resolve_id(ref)
        with db() as c:
            p=c.execute('SELECT * FROM projects WHERE id=?',(pid,)).fetchone()
            if not p:raise KeyError('Project not found')
            labels=[dict(x) for x in c.execute('SELECT * FROM labels WHERE project_id=? ORDER BY id',(pid,))]
            media=[enrich(x) for x in c.execute('''SELECT m.*, (SELECT COUNT(*) FROM annotations a WHERE a.media_id=m.id) annotation_count,(SELECT COUNT(*) FROM excluded_frames e WHERE e.media_id=m.id) excluded_count FROM media m WHERE project_id=? ORDER BY id DESC''',(pid,))]
            seconds=sum(int(item.get('annotation_seconds') or 0) for item in media)
            return {**dict(p),'labels':labels,'media':media,'annotation_seconds':seconds}
    def delete(self,pid):
        with db() as c:
            mask_rows=c.execute('SELECT a.mask_path FROM annotations a JOIN media m ON m.id=a.media_id WHERE m.project_id=?',(pid,)).fetchall()
            c.execute('DELETE FROM projects WHERE id=?',(pid,))
        for row in mask_rows:
            from pathlib import Path
            Path(row['mask_path']).unlink(missing_ok=True)
        shutil.rmtree(settings.media_root/str(pid),ignore_errors=True)
    def add_label(self,pid,name,color):
        name=name.strip()
        if not name:
            raise ValueError('Label name is required')
        with db() as c:
            existing=[row['color'] for row in c.execute('SELECT color FROM labels WHERE project_id=?',(pid,))]
            if color:
                next_color=ensure_unique(color,existing)
            else:
                next_color=unique_color(existing)
            try:
                cur=c.execute('INSERT INTO labels(project_id,name,color) VALUES (?,?,?)',(pid,name,next_color))
            except sqlite3.IntegrityError as exc:
                raise ValueError('Label name already exists') from exc
            return dict(c.execute('SELECT * FROM labels WHERE id=?',(cur.lastrowid,)).fetchone())
    def update_label(self,pid,lid,name=None,color=None):
        with db() as c:
            row=c.execute('SELECT * FROM labels WHERE id=? AND project_id=?',(lid,pid)).fetchone()
            if not row:
                raise KeyError('Label not found')
            next_name=name.strip() if name is not None else row['name']
            if not next_name:
                raise ValueError('Label name is required')
            others=[item['color'] for item in c.execute('SELECT color FROM labels WHERE project_id=? AND id<>?',(pid,lid))]
            next_color=ensure_unique(color,others) if color is not None else row['color']
            try:
                c.execute('UPDATE labels SET name=?,color=? WHERE id=? AND project_id=?',(next_name,next_color,lid,pid))
            except sqlite3.IntegrityError as exc:
                raise ValueError('Label name already exists') from exc
            return dict(c.execute('SELECT * FROM labels WHERE id=?',(lid,)).fetchone())
    def delete_label(self,pid,lid):
        with db() as c:
            n=c.execute('SELECT COUNT(*) n FROM annotations WHERE label_id=?',(lid,)).fetchone()['n']
            if n:raise ValueError(f'Label is used by {n} annotations')
            c.execute('DELETE FROM labels WHERE id=? AND project_id=?',(lid,pid))
project_service=ProjectService()
