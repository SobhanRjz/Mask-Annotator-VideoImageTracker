import {FormEvent,useEffect,useMemo,useRef,useState} from 'react';
import type {Media} from '../types';

function estimate(sourceFps:number,sourceFrames:number,extractFps:number){
  const fps=Math.max(sourceFps||0,0.001);
  const wanted=Math.min(Math.max(extractFps||0,0.001),fps);
  const stride=Math.max(1,Math.round(fps/wanted));
  const count=sourceFrames<=0?0:Math.ceil(sourceFrames/stride);
  return {stride,count,actualFps:fps/stride};
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
  media:Media;
  remaining:number;
  busy?:boolean;
  onCancel:()=>void;
  onExtract:(framesPerSecond:number)=>void;
}){
  const sourceFps=props.media.source_fps||props.media.fps||25;
  const sourceFrames=props.media.source_frame_count||0;
  const [fps,setFps]=useState(Math.min(1,sourceFps));
  const input=useRef<HTMLInputElement>(null);
  useEffect(()=>{input.current?.focus()},[props.media.id]);
  const preview=useMemo(()=>estimate(sourceFps,sourceFrames,fps),[sourceFps,sourceFrames,fps]);
  const submit=(e:FormEvent)=>{
    e.preventDefault();
    if(props.busy||preview.count<=0)return;
    props.onExtract(fps);
  };
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!props.busy)props.onCancel()}}>
    <form className="modal extract-modal" onSubmit={submit} onKeyDown={e=>{if(e.key==='Escape'&&!props.busy)props.onCancel()}}>
      <h2>Extract frames</h2>
      <p>{props.media.name} is <strong>{sourceFps.toFixed(2)} fps</strong>
        {props.media.duration_sec!=null&&<> · {formatDuration(props.media.duration_sec)}</>}
        {sourceFrames>0&&<> · {sourceFrames.toLocaleString()} source frames</>}.
        Choose how many frames to keep each second. Tracking later uses only this extracted set.</p>
      <label>Frames to extract per second
        <input ref={input} type="number" min={0.1} max={sourceFps} step={0.1} value={fps} disabled={props.busy}
          onChange={e=>setFps(Math.max(0.1,Number(e.target.value)||0.1))}/>
      </label>
      <div className="extract-preview">
        <span>Dataset size</span>
        <strong>{preview.count.toLocaleString()} frames</strong>
        <small>about {preview.actualFps.toFixed(2)} fps · every {preview.stride} source frame{preview.stride===1?'':'s'}</small>
      </div>
      {props.remaining>1&&<p className="muted">{props.remaining-1} more video{props.remaining-1===1?'':'s'} waiting.</p>}
      <div className="modal-actions">
        <button type="button" onClick={props.onCancel} disabled={props.busy}>Skip for now</button>
        <button type="submit" className="primary" disabled={props.busy||preview.count<=0}>{props.busy?'Extracting…':'Extract frames'}</button>
      </div>
    </form>
  </div>;
}
