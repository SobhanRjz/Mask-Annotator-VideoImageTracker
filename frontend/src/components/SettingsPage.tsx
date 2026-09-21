import {useEffect,useState} from 'react';
import * as api from '../api/client';
import {DEFAULT_TRACK_PATCH,MAX_TRACK_PATCH,MIN_TRACK_PATCH,parseTrackPatch} from '../editorWorkflow';
import {cacheLabel,modelJobActive,modelProgressText} from '../modelSettings';
import type {ModelSettings,TrackingSettings} from '../types';

export function SettingsPage(){
  const [report,setReport]=useState<ModelSettings|null>(null);
  const [tracking,setTracking]=useState<TrackingSettings|null>(null);
  const [patchDraft,setPatchDraft]=useState(String(DEFAULT_TRACK_PATCH));
  const [error,setError]=useState<string|null>(null);
  const job=report?.job??null;
  const running=modelJobActive(job);

  useEffect(()=>{
    let stop=false;
    api.getTrackingSettings().then(track=>{
      if(stop)return;
      setTracking(track);
      setPatchDraft(String(track.track_patch_size));
    }).catch(err=>{
      if(!stop)setError(err instanceof Error?err.message:String(err));
    });
    return()=>{stop=true};
  },[]);

  useEffect(()=>{
    let stop=false;
    const load=async()=>{
      try{
        const next=await api.getModelSettings();
        if(!stop){
          setReport(next);
          setError(null);
        }
      }catch(err){
        if(!stop)setError(err instanceof Error?err.message:String(err));
      }
    };
    load();
    const timer=window.setInterval(load,running?700:4000);
    return()=>{stop=true;window.clearInterval(timer)};
  },[running,job?.id]);

  const select=async(key:string)=>{
    if(running||key===report?.active)return;
    setError(null);
    try{
      const started=await api.switchSamModel(key);
      setReport(current=>current?{...current,job:started}:current);
    }catch(err){
      setError(err instanceof Error?err.message:String(err));
    }
  };

  const savePatch=async()=>{
    const size=parseTrackPatch(patchDraft,tracking?.track_patch_size??DEFAULT_TRACK_PATCH);
    setPatchDraft(String(size));
    if(size===tracking?.track_patch_size)return;
    setError(null);
    try{
      const next=await api.saveTrackingSettings(size);
      setTracking(next);
    }catch(err){
      setError(err instanceof Error?err.message:String(err));
    }
  };

  return <main className="settings">
    <section className="dash-hero">
      <div>
        <h1>Settings</h1>
        <p>Choose the SAM 2.1 size for prompts and tracking on this machine.</p>
      </div>
    </section>

    {error&&<p className="error-inline settings-error">{error}</p>}

    <div className="model-grid">
      {(report?.models??[]).map(item=>(
        <button
          key={item.key}
          type="button"
          className={`model-card${item.active?' active':''}`}
          disabled={running}
          onClick={()=>void select(item.key)}
        >
          <div className="model-card-top">
            <strong>{item.label}</strong>
            {item.active&&<span className="model-active">Active</span>}
          </div>
          <code>{item.model_id}</code>
          <span className={item.cached?'model-cache on':'model-cache'}>{cacheLabel(item.cached)}</span>
          {item.note&&<small>{item.note}</small>}
        </button>
      ))}
    </div>

    {job&&<div className="job settings-job">
      <div><span>{modelProgressText(job)}</span><span>{job.progress}%</span></div>
      <div className="progress"><i style={{width:`${job.progress}%`}}/></div>
      {job.status==='failed'&&<small className="error-inline">{job.error||job.message}</small>}
    </div>}

    <section className="settings-track">
      <div>
        <h2>Video tracker</h2>
        <p>SAM2 still reads every frame in the range. Images per patch is how many of those frames share one GPU window. Larger is usually faster; smaller uses less VRAM.</p>
      </div>
      <label>
        Images per patch
        <input
          type="number"
          min={tracking?.min??MIN_TRACK_PATCH}
          max={tracking?.max??MAX_TRACK_PATCH}
          value={patchDraft}
          onChange={e=>setPatchDraft(e.target.value)}
          onBlur={()=>void savePatch()}
          onKeyDown={e=>{if(e.key==='Enter'){e.currentTarget.blur()}}}
        />
      </label>
      <small>{MIN_TRACK_PATCH}–{MAX_TRACK_PATCH}. Default {DEFAULT_TRACK_PATCH}.</small>
    </section>
  </main>;
}
