import {FormEvent,useEffect,useMemo,useRef,useState} from 'react';
import {clampExtractRate,defaultExtractRate,sourceFps} from '../extractWorkflow';
import type {ExtractionJob,Media} from '../types';

export function estimate(sourceFps:number,sourceFrames:number,extractFps:number){
  const fps=Math.max(sourceFps||0,0.001);
  const wanted=Math.min(Math.max(extractFps||0,0.1),fps);
  const duration=sourceFrames>0?sourceFrames/fps:0;
  const count=duration<=0?0:Math.max(1,Math.ceil(duration*wanted));
  return {count,actualFps:wanted,duration};
}

export function formatDuration(seconds:number){
  const total=Math.max(0,Math.round(seconds||0));
  const h=Math.floor(total/3600);
  const m=Math.floor((total%3600)/60);
  const s=total%60;
  if(h>0)return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${m}:${String(s).padStart(2,'0')}`;
}

export function ExtractDialog(props:{
  media:Media[];
  jobs:Record<number,ExtractionJob>;
  busy?:boolean;
  onCancel:()=>void;
  onExtract:(framesPerSecond:Record<number,number>)=>void;
}){
  const [rates,setRates]=useState<Record<number,number>>(()=>Object.fromEntries(props.media.map(item=>{
    const fps=sourceFps(item);
    return [item.id,defaultExtractRate(fps)];
  })));
  const input=useRef<HTMLInputElement>(null);
  useEffect(()=>{
    input.current?.focus();
    setRates(current=>Object.fromEntries(props.media.map(item=>{
      const fps=sourceFps(item);
      return [item.id,clampExtractRate(fps,current[item.id]??defaultExtractRate(fps))];
    })));
  },[props.media]);
  const total=useMemo(()=>props.media.reduce((sum,item)=>{
    const fps=sourceFps(item);
    return sum+estimate(fps,item.source_frame_count||0,rates[item.id]??defaultExtractRate(fps)).count;
  },0),[props.media,rates]);
  const running=Object.values(props.jobs).some(job=>!['completed','failed','cancelled'].includes(job.status));
  const submit=(e:FormEvent)=>{
    e.preventDefault();
    if(props.busy||running||!props.media.length)return;
    props.onExtract(Object.fromEntries(props.media.map(item=>{
      const fps=sourceFps(item);
      return [item.id,clampExtractRate(fps,rates[item.id]??defaultExtractRate(fps))];
    })));
  };
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!props.busy&&!running)props.onCancel()}}>
    <form className="modal extract-modal" noValidate onSubmit={submit} onKeyDown={e=>{if(e.key==='Escape'&&!props.busy&&!running)props.onCancel()}}>
      <h2>Extract frames from videos</h2>
      <p>Set a sampling rate for each video. For example, <strong>0.5 fps</strong> keeps one frame every two seconds.</p>
      <div className="extract-video-list">
        {props.media.map((item,index)=>{
          const fps=sourceFps(item);
          const value=clampExtractRate(fps,rates[item.id]??defaultExtractRate(fps));
          const preview=estimate(fps,item.source_frame_count||0,value);
          const job=props.jobs[item.id];
          const terminal=job&&['completed','failed','cancelled'].includes(job.status);
          return <div className="extract-video-row" key={item.id}>
            <div className="extract-video-name">
              <span>{index+1}</span>
              <strong title={item.name}>{item.name}</strong>
              {job&&<small className={job.status==='failed'?'error-inline':''}>{job.status==='completed'?'Complete':job.status==='failed'?job.error||'Failed':`${job.status} · ${job.progress}%`}</small>}
            </div>
            <label>FPS
              <input ref={index===0?input:undefined} type="number" min={0.1} max={fps} step={0.1} value={value} disabled={props.busy||running||Boolean(terminal)}
                onChange={e=>setRates(current=>({...current,[item.id]:clampExtractRate(fps,Number(e.target.value))}))}/>
            </label>
            <div className="extract-row-count">
              <b>{preview.count.toLocaleString()}</b>
              <span>frames · {formatDuration(preview.duration)}</span>
              {job&&<div className="progress"><i style={{width:`${job.progress}%`}}/></div>}
            </div>
          </div>;
        })}
      </div>
      <div className="extract-preview">
        <span>Estimated total</span>
        <strong>{total.toLocaleString()} frames</strong>
        <small>FFmpeg samples by time, so fractional FPS values are preserved.</small>
      </div>
      <div className="modal-actions">
        <button type="button" onClick={props.onCancel} disabled={props.busy||running}>Skip for now</button>
        <button type="submit" className="primary" disabled={props.busy||running||!props.media.length}>{running?'Extracting…':'Extract frames'}</button>
      </div>
    </form>
  </div>;
}
