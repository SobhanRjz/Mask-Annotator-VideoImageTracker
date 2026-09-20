import {FormEvent,useEffect,useRef,useState} from 'react';
import type {ExportFormat,ExportJob,ProjectSummary} from '../types';
import * as api from '../api/client';
import {defaultExportOptions,exportHasContent,exportProjectIds,preparingExportLabel,type ExportOptions} from '../exportWorkflow';

const OPTIONS:{fmt:ExportFormat;title:string;hint:string}[]=[
  {fmt:'coco',title:'COCO instance',hint:'Official instances JSON plus JPEG frames for Detectron, MMDetection, and similar tools.'},
  {fmt:'yolo',title:'YOLO segmentation',hint:'Normalized polygons, classes.txt, and data.yaml ready for Ultralytics YOLO-seg.'},
  {fmt:'voc',title:'Pascal VOC masks',hint:'JPEG frames with class and instance PNGs for semantic and instance pipelines.'},
  {fmt:'native',title:'Native backup',hint:'Lossless mask PNGs and project.json for this annotator.'},
];

export function ExportDialog(props:{
  projects:ProjectSummary[];
  defaultProjectId:number|null;
  onClose:()=>void;
}){
  const [options,setOptions]=useState<ExportOptions>(()=>defaultExportOptions(props.defaultProjectId));
  const [job,setJob]=useState<ExportJob|null>(null);
  const [error,setError]=useState<string|null>(null);
  const downloadedId=useRef<string|null>(null);
  const running=job?.status==='queued'||job?.status==='running';
  const ready=job?.status==='completed';

  useEffect(()=>{
    if(!job||(job.status!=='queued'&&job.status!=='running'))return;
    const timer=window.setInterval(async()=>{
      try{
        const next=await api.exportStatus(job.id);
        setJob(next);
        if(next.status==='completed'&&next.filename&&downloadedId.current!==next.id){
          downloadedId.current=next.id;
          await api.downloadExport(next.id,next.filename);
        }
      }catch(err){
        setError(err instanceof Error?err.message:'Export status failed');
      }
    },700);
    return()=>window.clearInterval(timer);
  },[job?.id,job?.status]);

  const patch=(partial:Partial<ExportOptions>)=>setOptions(current=>({...current,...partial}));

  const submit=async(event:FormEvent)=>{
    event.preventDefault();
    if(running||!exportHasContent(options))return;
    if(options.scope==='project'&&options.projectId==null)return;
    setError(null);
    try{
      const started=await api.startExport({
        format:options.format,
        project_ids:exportProjectIds(options),
        include_unannotated:options.includeUnannotated,
        include_auto:options.includeAuto,
        include_manual:options.includeManual,
      });
      setJob(started);
      if(started.status==='completed'&&started.filename&&downloadedId.current!==started.id){
        downloadedId.current=started.id;
        await api.downloadExport(started.id,started.filename);
      }
    }catch(err){
      setError(err instanceof Error?err.message:'Could not start export');
    }
  };

  const stop=async()=>{
    if(!job||!running)return;
    try{
      setJob(await api.cancelExport(job.id));
    }catch(err){
      setError(err instanceof Error?err.message:'Could not stop export');
    }
  };

  const close=()=>{
    if(running)return;
    props.onClose();
  };

  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)close()}}>
    <form className="modal export-modal" onSubmit={submit} onKeyDown={e=>{if(e.key==='Escape')close()}}>
      <h2>Export annotations</h2>
      <p>Choose the project scope, format, and which frames or masks to include. The ZIP is prepared on the server, then downloaded.</p>

      <div className="export-scope">
        <span>Projects</span>
        <label className="switch-row">
          <input type="radio" name="export-scope" checked={options.scope==='all'} disabled={running} onChange={()=>patch({scope:'all'})}/>
          All projects (merge into one dataset)
        </label>
        <label className="switch-row">
          <input type="radio" name="export-scope" checked={options.scope==='project'} disabled={running||!props.projects.length} onChange={()=>patch({scope:'project',projectId:options.projectId??props.defaultProjectId??props.projects[0]?.id??null})}/>
          One project
        </label>
        {options.scope==='project'&&<select value={options.projectId??''} disabled={running} onChange={e=>patch({projectId:Number(e.target.value)})}>
          {props.projects.map(project=>(
            <option key={project.id} value={project.id}>{project.name}</option>
          ))}
        </select>}
      </div>

      <div className="export-options">
        {OPTIONS.map(option=>(
          <button type="button" key={option.fmt} className={`export-option${options.format===option.fmt?' selected':''}`} disabled={running} onClick={()=>patch({format:option.fmt})}>
            <strong>{option.title}</strong>
            <span>{option.hint}</span>
          </button>
        ))}
      </div>

      <div className="export-filters">
        <h3>Include in this export</h3>
        <label className="switch-row">
          <input type="checkbox" checked={options.includeUnannotated} disabled={running} onChange={e=>patch({includeUnannotated:e.target.checked})}/>
          Frames with no annotations
        </label>
        <label className="switch-row">
          <input type="checkbox" checked={options.includeManual} disabled={running} onChange={e=>patch({includeManual:e.target.checked})}/>
          Manual masks
        </label>
        <label className="switch-row">
          <input type="checkbox" checked={options.includeAuto} disabled={running} onChange={e=>patch({includeAuto:e.target.checked})}/>
          Auto-tracked masks
        </label>
        {!exportHasContent(options)&&<p className="error-inline">Turn on at least one of the filters above.</p>}
      </div>

      {(running||ready||job?.status==='failed'||job?.status==='cancelled')&&<div className="export-progress job">
        <div>
          <strong>{preparingExportLabel(job?.status??'running',job?.progress??0,job?.message)}</strong>
          <span>{job?.progress??0}%</span>
        </div>
        <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={job?.progress??0} aria-label="Preparing the export">
          <i style={{width:`${job?.progress??0}%`}}/>
        </div>
        {job?.error&&<p className="error-inline">{job.error}</p>}
        {ready&&<small>Download started. You can close this dialog.</small>}
      </div>}

      {error&&<p className="error-inline">{error}</p>}

      <div className="modal-actions">
        {running
          ? <button type="button" className="danger" onClick={()=>{void stop()}}>Stop</button>
          : <button type="button" onClick={close}>{ready?'Close':'Cancel'}</button>}
        <button type="submit" className="primary" disabled={running||!exportHasContent(options)||!props.projects.length}>
          {running?'Preparing…':'export'}
        </button>
      </div>
    </form>
  </div>;
}
