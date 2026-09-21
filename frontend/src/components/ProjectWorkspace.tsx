import {useMemo,useState} from 'react';
import * as api from '../api/client';
import {filterLibrary,firstIncompleteStill,libraryRows,libraryTabCounts,type LibraryTab} from '../mediaLibrary';
import {mediaReady,type Label,type Media,type Project} from '../types';
import {formatDuration} from './ExtractDialog';
import {TimeChip} from './TimeChip';
import {TrashIcon} from './TrashIcon';

export function DoneCheck(props:{checked:boolean;onChange:(value:boolean)=>void;disabled?:boolean}){
  return <label className={`done-check${props.checked?' on':''}${props.disabled?' disabled':''}`} onClick={e=>e.stopPropagation()}>
    <input type="checkbox" checked={props.checked} disabled={props.disabled} onChange={e=>props.onChange(e.target.checked)}/>
    <span className="done-box" aria-hidden="true">{props.checked&&<svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round"><path d="m5 12 5 5 9-10"/></svg>}</span>
    Done
  </label>;
}

export function ProjectWorkspace(props:{
  project:Project;
  onUpload:(files:FileList|null)=>void;
  onAnnotate:(item:Media)=>void;
  onExtract:(item:Media)=>void;
  onDeleteMedia:(item:Media)=>void;
  onDeletePictures:()=>void;
  onSetVideoComplete:(item:Media,complete:boolean)=>void;
  onSetPicturesComplete:(complete:boolean)=>void;
  onAddLabel:()=>void;
  onLabelColor:(id:number,color:string)=>void;
  onDeleteLabel:(label:Label)=>void;
  onDeleteProject:()=>void;
}){
  const {project}=props;
  const [tab,setTab]=useState<LibraryTab>('all');
  const videos=project.media.filter(item=>item.kind==='video');
  const images=project.media.filter(item=>item.kind==='image');
  const extracted=project.media.reduce((sum,item)=>sum+(mediaReady(item)?item.frame_count:0),0);
  const cover=project.media.find(item=>mediaReady(item));
  const rows=useMemo(()=>libraryRows(project.media),[project.media]);
  const counts=libraryTabCounts(rows);
  const visible=filterLibrary(rows,tab);
  const completion=rows.length?Math.round((counts.completed/rows.length)*100):0;

  return <main className="workspace">
      <section className="workspace-hero">
        {cover&&<img className="workspace-cover" src={api.frameUrl(cover.id,0,960)} alt=""/>}
        <div className="workspace-hero-copy">
          <div className="eyebrow">ACTIVE INSPECTION</div>
          <h1>{project.name}</h1>
          <p>{project.description||'Upload CCTV, extract a frame set, then annotate defects with SAM2.'}</p>
          <code className="workspace-slug">/projects/{project.slug||project.id}</code>
          <div className="workspace-kpis">
            <div><span>Videos</span><b>{videos.length}</b></div>
            <div><span>Images</span><b>{images.length}</b></div>
            <div><span>Extracted frames</span><b>{extracted}</b></div>
            <div><span>Masks</span><b>{project.media.reduce((sum,item)=>sum+(item.annotation_count??0),0)}</b></div>
            <div><span>Time</span><b><TimeChip seconds={project.annotation_seconds??0} compact/></b></div>
          </div>
          <div className="workspace-progress">
            <div><span>Project completion</span><b>{completion}%</b></div>
            <i aria-hidden="true"><b style={{width:`${completion}%`}}/></i>
          </div>
        </div>
        <div className="workspace-actions">
          <label className="primary upload-button">Upload media<input type="file" multiple accept="video/*,image/*" onChange={e=>props.onUpload(e.target.files)}/></label>
          <button type="button" className="danger workspace-delete" title="Delete project" aria-label={`Delete ${project.name}`} onClick={props.onDeleteProject}>
            <TrashIcon/>
          </button>
        </div>
      </section>

      <div className="workspace-grid">
        <section className="workspace-media">
          <div className="section-title">
            <div>
              <h2>Media library</h2>
              <p>{rows.length} work item{rows.length===1?'':'s'} · {counts.completed} completed · {counts.not_annotated} waiting</p>
            </div>
            {rows.length>0&&<div className="filter-seg library-tabs" role="group" aria-label="Media status">
              {([['all','All',counts.all],['completed','Completed',counts.completed],['not_annotated','Not annotated',counts.not_annotated]] as const).map(([value,label,count])=>(
                <button type="button" key={value} className={tab===value?'active':''} aria-pressed={tab===value} onClick={()=>setTab(value)}>{label} · {count}</button>
              ))}
            </div>}
          </div>
          {project.media.length===0&&<div className="empty-state workspace-empty">
            <h2>No footage in this job yet</h2>
            <p>Drop sewer CCTV or stills. Videos wait for an extract rate before annotation.</p>
          </div>}
          {project.media.length>0&&visible.length===0&&<div className="empty-state workspace-empty">
            <h2>Nothing in this filter</h2>
            <p>Switch tabs to see completed or unfinished media.</p>
          </div>}
          <div className="media-table">
            {visible.map(row=>{
              if(row.kind==='pictures'){
                const open=firstIncompleteStill(row.images)??row.images[0];
                return <article className={`media-row compact${row.complete?' complete':''}`} key="pictures">
                  <button className="media-thumb" onClick={()=>props.onAnnotate(open)}>
                    <img src={api.frameUrl(row.images[0].id,0,360)} alt=""/>
                    <span className="kind">pictures</span>
                  </button>
                  <div className="media-copy">
                    <strong>Pictures</strong>
                    <small>{row.images.length} still{row.images.length!==1?'s':''}
                      {' · '}{row.images.reduce((sum,item)=>sum+(item.annotation_count??0),0)} annotations
                    </small>
                    <div className="meta">
                      <TimeChip seconds={row.images.reduce((sum,item)=>sum+(item.annotation_seconds??0),0)} compact/>
                    </div>
                  </div>
                  <div className="media-actions">
                    <DoneCheck checked={row.complete} onChange={value=>props.onSetPicturesComplete(value)}/>
                    <button className="annotate" onClick={()=>props.onAnnotate(open)}>Annotate</button>
                    <button className="danger" onClick={props.onDeletePictures}>Delete</button>
                  </div>
                </article>;
              }
              const item=row.media;
              return <article className={`media-row compact${row.complete?' complete':''}`} key={item.id}>
                <button className="media-thumb" onClick={()=>mediaReady(item)?props.onAnnotate(item):props.onExtract(item)}>
                  {mediaReady(item)
                    ? <img src={api.frameUrl(item.id,0,360)} alt=""/>
                    : <div className="media-placeholder">Not extracted</div>}
                  <span className="kind">{item.kind}</span>
                </button>
                <div className="media-copy">
                  <strong title={item.name}>{item.name}</strong>
                  <small>{item.width}×{item.height}
                    <> · {(item.source_fps??item.fps).toFixed(2)} fps · {formatDuration(item.duration_sec??0)}</>
                    {mediaReady(item)?<> · {item.frame_count} frame{item.frame_count!==1?'s':''}</>:<> · waiting for extract</>}
                  </small>
                  <div className="meta">
                    <span>{item.annotation_count??0} annotations</span>
                    <span>{item.excluded_count??0} excluded</span>
                    <TimeChip seconds={item.annotation_seconds??0} compact/>
                  </div>
                </div>
                <div className="media-actions">
                  <DoneCheck checked={row.complete} onChange={value=>props.onSetVideoComplete(item,value)}/>
                  {mediaReady(item)
                    ? <button className="annotate" onClick={()=>props.onAnnotate(item)}>Annotate</button>
                    : <button className="extract" onClick={()=>props.onExtract(item)}>Extract frames</button>}
                  <button className="danger" onClick={()=>props.onDeleteMedia(item)}>Delete</button>
                </div>
              </article>;
            })}
          </div>
        </section>
        <aside className="labels-panel workspace-labels">
          <div className="section-title">
            <div><div className="panel-kicker">PROJECT LABELS</div><h2>Defect legend</h2><p>{project.labels.length} classes for this inspection.</p></div>
            <button onClick={props.onAddLabel}>+ Add</button>
          </div>
          <div className="label-list">
            {project.labels.map(label=>(
              <div className="label-row" key={label.id}>
                <label className="swatch" title="Change color">
                  <input type="color" value={label.color.toLowerCase()} onChange={e=>props.onLabelColor(label.id,e.target.value)}/>
                </label>
                <span>{label.name}</span>
                <button className="ghost danger-text" onClick={()=>props.onDeleteLabel(label)}>×</button>
              </div>
            ))}
          </div>
        </aside>
      </div>
    </main>;
}
