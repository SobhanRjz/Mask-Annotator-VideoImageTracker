import type {BoxPrompt,PromptPoint,ToolMode} from './types';

export function toolAfterGeneratedMask(current:ToolMode):ToolMode{
  return current;
}

export function keepPromptsAfterPredict(){
  return true;
}

export function closeSessionAfterPredict(){
  return false;
}

export function maskUrlForPrompt(points:PromptPoint[],box:BoxPrompt|null,canvasMask:string|null|undefined,merge=false){
  if(merge||!canvasMask)return null;
  if(points.some(point=>point.positive))return null;
  return canvasMask;
}

export function boxStartsNewInstance(hasCurrentMask:boolean, accepted=false){
  return hasCurrentMask && accepted;
}

export function idsToDropOnUndo(before:number[], after:number[]){
  const known=new Set(before);
  return after.filter(id=>!known.has(id));
}

export function selectDragStartsBox(_hitMask:boolean){
  return false;
}

export function selectDragStartsMarquee(){
  return true;
}

export function selectEmptyRelease(boxW:number,boxH:number){
  return boxW>3&&boxH>3?'marquee':'unfocus';
}

export function mergeSelection(current:number[],next:number[],additive:boolean){
  if(!additive)return [...next];
  const ids=new Set(current);
  for(const id of next)ids.add(id);
  return [...ids];
}

export function idsToDelete(selectedIds:number[],selectedId:number|null){
  if(selectedIds.length)return [...selectedIds];
  return selectedId==null?[]:[selectedId];
}

export function idsToTrack(selectedIds:number[],selectedId:number|null,frameAnnotationIds:number[]){
  if(selectedIds.length)return [...selectedIds];
  if(selectedId!=null)return [selectedId];
  return [...frameAnnotationIds];
}

export function trackButtonLabel(seedCount:number){
  return seedCount>1?`Track ${seedCount} masks`:'Track from this mask';
}

export function trackSeedsMatchFrom(
  kind:string,
  seeds:{media_id:number;frame:number}[],
  fromIndex:number,
  fromMediaId:number|undefined,
){
  if(kind==='image')return seeds.every(item=>item.media_id===fromMediaId&&item.frame===0);
  return seeds.every(item=>item.frame===fromIndex);
}

export function annotatedFrameCount(frames:{annotation_count:number}[]){
  return frames.reduce((n,item)=>n+(item.annotation_count>0?1:0),0);
}

export type FrameStatusFilter='all'|'annotated'|'unannotated';

export function filterFrames<T extends {annotation_count:number;labels?:{id:number}[]}>(
  frames:T[],
  status:FrameStatusFilter,
  labelIds:number[],
){
  const wanted=new Set(labelIds);
  return frames.filter(item=>{
    if(status==='annotated'&&item.annotation_count<=0)return false;
    if(status==='unannotated'&&item.annotation_count>0)return false;
    if(wanted.size&&!(item.labels??[]).some(label=>wanted.has(label.id)))return false;
    return true;
  });
}

export function toggleSelection(current:number[],id:number){
  return current.includes(id)?current.filter(item=>item!==id):[...current,id];
}

export function brushStrokeUsesDetection(hasFocusedMask:boolean){
  return hasFocusedMask?'paint':'detect';
}

export function escapeUnfocusesMasks(){
  return true;
}

export function panBy(origin:{x:number;y:number},start:{x:number;y:number},now:{x:number;y:number}){
  return {x:origin.x+(now.x-start.x),y:origin.y+(now.y-start.y)};
}

export function brushBoundsToBox(bounds:{x:number;y:number;w:number;h:number}|null):BoxPrompt|null{
  if(!bounds||bounds.w<3||bounds.h<3)return null;
  return [bounds.x,bounds.y,bounds.x+bounds.w,bounds.y+bounds.h];
}

export function displayIndex(zeroBased:number){
  return zeroBased+1;
}

export function fromDisplayIndex(oneBased:number){
  if(!Number.isFinite(oneBased))return 0;
  return Math.max(0,Math.round(oneBased)-1);
}

export function clampMenuPos(left:number,top:number,wrapW:number,wrapH:number,menuW:number,menuH:number){
  const maxLeft=Math.max(8,wrapW-menuW-8);
  const maxTop=Math.max(8,wrapH-menuH-8);
  return {
    left:Math.max(8,Math.min(left,maxLeft)),
    top:Math.max(8,Math.min(top,maxTop)),
  };
}

export function acceptedMaskId(staleSelectedId:number|null,savedId:number|null|undefined){
  return savedId??staleSelectedId;
}

export function paintOverlayCopy(overlayId:number,focusedId:number|null){
  return overlayId!==focusedId;
}

export function clickOutsideUnfocuses(tool:ToolMode){
  return tool!=='erase';
}

export const DEFAULT_TRACK_PATCH=16;
export const MIN_TRACK_PATCH=2;
export const MAX_TRACK_PATCH=128;

export function parseTrackPatch(value:unknown,fallback=DEFAULT_TRACK_PATCH){
  const size=typeof value==='number'?value:Number(value);
  if(!Number.isFinite(size))return fallback;
  return Math.max(MIN_TRACK_PATCH,Math.min(MAX_TRACK_PATCH,Math.round(size)));
}
