import {useMemo,useState} from 'react';
import * as api from '../api/client';
import type {ProjectSummary} from '../types';
import {TimeChip} from './TimeChip';
import {TrashIcon} from './TrashIcon';

export function ProjectsPage(props:{
  projects:ProjectSummary[];
  boot:string;
  busy?:boolean;
  onCreate:()=>void;
  onImport:(file:File|null)=>void;
  onOpen:(project:ProjectSummary)=>void;
  onDelete:(project:ProjectSummary)=>void;
}){
  const [query,setQuery]=useState('');
  const filtered=useMemo(()=>{
    const needle=query.trim().toLowerCase();
    if(!needle)return props.projects;
    return props.projects.filter(item=>`${item.name} ${item.description} ${item.slug??''}`.toLowerCase().includes(needle));
  },[props.projects,query]);

  return <main className="catalog">
      <section className="catalog-hero">
        <div>
          <div className="eyebrow">INSPECTION LIBRARY</div>
          <h1>Your projects</h1>
          <p>Organize footage, review annotation progress, and return to active inspections.</p>
        </div>
        <div className="catalog-toolbar">
          <label className="catalog-search">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
            <input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search projects" aria-label="Search projects"/>
          </label>
          <label className={`upload-button${props.boot!=='ready'||props.busy?' disabled':''}`}>
            Import backup
            <input type="file" accept=".zip,application/zip" disabled={props.boot!=='ready'||props.busy} onChange={e=>{props.onImport(e.target.files?.[0]??null);e.target.value=''}}/>
          </label>
          <button className="primary" onClick={props.onCreate} disabled={props.boot!=='ready'||props.busy}>New project</button>
        </div>
      </section>
      <div className="catalog-grid">
        {filtered.map(item=>(
          <article className="catalog-card" key={item.id}>
            <button type="button" className="catalog-open" onClick={()=>props.onOpen(item)}>
              <div className="catalog-cover">
                {item.cover_media_id
                  ? <img src={api.frameUrl(item.cover_media_id,0,480)} alt=""/>
                  : <div className="catalog-ph">No media yet</div>}
                <span className="catalog-slug">/{item.slug||item.id}</span>
                <span className="catalog-count">{item.annotation_count} masks</span>
              </div>
              <div className="catalog-body">
                <div className="catalog-title-row"><h2>{item.name}</h2><span aria-hidden="true">↗</span></div>
                <p>{item.description||'Sewer inspection annotation job'}</p>
                <div className="meta">
                  <span>{item.media_count} media</span>
                  <TimeChip seconds={item.annotation_seconds??0} compact/>
                </div>
              </div>
            </button>
            <button type="button" className="danger catalog-delete" title="Delete project" aria-label={`Delete ${item.name}`} onClick={()=>props.onDelete(item)}>
              <TrashIcon/>
            </button>
          </article>
        ))}
        {props.boot!=='ready'&&!props.projects.length&&<div className="empty-state">
          <h2>{props.boot==='loading'?'Loading projects':'Waiting for backend'}</h2>
          <p>Cannot reach /api/projects yet. The UI retries until FastAPI is listening.</p>
        </div>}
        {props.boot==='ready'&&!props.projects.length&&<div className="empty-state catalog-empty">
          <h2>Name the first inspection</h2>
          <p>Use a unique site or survey name. It becomes the project URL, not a number.</p>
          <button className="primary" onClick={props.onCreate}>Create project</button>
        </div>}
        {props.boot==='ready'&&props.projects.length>0&&!filtered.length&&<div className="empty-state">
          <h2>No matching projects</h2>
          <p>Try a different name or description.</p>
        </div>}
      </div>
    </main>;
}
