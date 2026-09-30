export function sourceFps(item:{source_fps?:number;fps?:number}){
  return item.source_fps||item.fps||25;
}

export function clampExtractRate(source:number,value:number){
  const fps=Math.max(source||0,0.1);
  const wanted=Number(value);
  if(!Number.isFinite(wanted))return Math.min(1,fps);
  return Math.min(fps,Math.max(0.1,wanted));
}

export function extractDialogVisible(queueLength:number,_hasReusedNotice=false){
  return queueLength>0;
}

export function defaultExtractRate(source:number){
  return Math.min(1,Math.max(source||0,0.1));
}

const TERMINAL=new Set(['completed','failed','cancelled']);

export function mergeExtractionJobs<T extends {media_id:number}>(current:Record<number,T>,updates:T[]){
  const next={...current};
  for(const job of updates)next[job.media_id]=job;
  return next;
}

export function extractionBatchFinished<T extends {media_id:number;status:string}>(polled:T[],known:Record<number,T>){
  const jobs=Object.values(mergeExtractionJobs(known,polled));
  return jobs.length>0&&jobs.every(job=>TERMINAL.has(job.status));
}

export function extractionJobsActive<T extends {status:string}>(jobs:Record<number,T>){
  return Object.values(jobs).some(job=>!TERMINAL.has(job.status));
}

export function completedExtractBatchStatus<T extends {status:string}>(jobs:T[]){
  if(!jobs.length)return '';
  return jobs.every(job=>job.status==='completed')?'Extraction complete':'Some videos could not be extracted';
}
