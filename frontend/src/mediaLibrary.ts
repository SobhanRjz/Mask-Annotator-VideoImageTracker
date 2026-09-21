import type {FrameInfo,Media} from './types';

export type StillFrameRow=FrameInfo&{mediaId:number;index:number};

export function stillFrameRows(stills:Media[],details:Record<number,FrameInfo>={}):StillFrameRow[]{
  return stills.map((item,index)=>{
    const info=details[item.id];
    return {
      mediaId:item.id,
      index,
      frame:info?.frame??0,
      annotation_count:info?.annotation_count??item.annotation_count??0,
      excluded:info?.excluded??false,
      labels:info?.labels??[],
    };
  });
}

export type LibraryTab='all'|'completed'|'not_annotated';

export type LibraryRow=
  | {kind:'video';media:Media;complete:boolean}
  | {kind:'pictures';images:Media[];complete:boolean};

export function stillsOf(media:Media[]){
  return media.filter(item=>item.kind==='image').slice().sort((a,b)=>a.id-b.id);
}

export function picturesComplete(images:Media[]){
  const stills=stillsOf(images);
  return stills.length>0&&stills.every(item=>!!item.annotation_complete);
}

export function libraryRows(media:Media[]):LibraryRow[]{
  const images=stillsOf(media);
  const rows:LibraryRow[]=[];
  if(images.length)rows.push({kind:'pictures',images,complete:picturesComplete(images)});
  for(const item of media){
    if(item.kind!=='video')continue;
    rows.push({kind:'video',media:item,complete:!!item.annotation_complete});
  }
  return rows;
}

export function filterLibrary(rows:LibraryRow[],tab:LibraryTab){
  if(tab==='all')return rows;
  if(tab==='completed')return rows.filter(row=>row.complete);
  return rows.filter(row=>!row.complete);
}

export function libraryTabCounts(rows:LibraryRow[]){
  return {
    all:rows.length,
    completed:rows.filter(row=>row.complete).length,
    not_annotated:rows.filter(row=>!row.complete).length,
  };
}

export function firstIncompleteStill(media:Media[]){
  const stills=stillsOf(media);
  return stills.find(item=>!item.annotation_complete)??stills[0]??null;
}

export function stillIndex(media:Media[],id:number){
  return stillsOf(media).findIndex(item=>item.id===id);
}

export function stepStill(media:Media[],id:number,delta:number){
  const stills=stillsOf(media);
  const index=stills.findIndex(item=>item.id===id);
  if(index<0||!stills.length)return null;
  const next=Math.max(0,Math.min(stills.length-1,index+delta));
  return stills[next];
}

export function trackLastIndex(kind:string,stillCount:number,frameCount:number){
  if(kind==='image')return Math.max(0,stillCount-1);
  return Math.max(0,frameCount-1);
}

export function trackCursor(kind:string,stillIndex:number,frame:number){
  return kind==='image'?Math.max(0,stillIndex):frame;
}

export function trackSeedMediaId(kind:string,stills:Media[],fromIndex:number,currentMediaId:number){
  if(kind!=='image')return currentMediaId;
  return stills[fromIndex]?.id??currentMediaId;
}
