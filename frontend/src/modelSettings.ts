import type {ModelSwitchJob} from './types';

export function cacheLabel(cached:boolean){
  return cached?'Downloaded':'Not downloaded';
}

export function modelJobActive(job:ModelSwitchJob|null|undefined){
  return job?.status==='queued'||job?.status==='running';
}

export function modelProgressText(job:ModelSwitchJob|null|undefined){
  if(!job)return '';
  if(job.status==='failed')return job.error||job.message||'Model switch failed';
  return job.message||'Working…';
}

export function modelCardDisabled(job:ModelSwitchJob|null|undefined,key:string,active:string){
  if(modelJobActive(job))return true;
  return key===active&&!job;
}
