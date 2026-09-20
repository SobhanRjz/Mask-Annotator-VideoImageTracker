export type UploadedMedia={
  id?:number;
  name:string;
  kind:'video'|'image'|string;
  reused?:boolean;
  annotation_count?:number;
};

function annotationPhrase(count:number){
  return count===1?'its 1 annotation':`its ${count} annotations`;
}

function uniqueReused(items:UploadedMedia[]){
  const reused:UploadedMedia[]=[];
  const seen=new Set<number|string>();
  for(const item of items){
    if(!item.reused)continue;
    const key=item.id??item.name;
    if(seen.has(key))continue;
    seen.add(key);
    reused.push(item);
  }
  return reused;
}

export function reusedMediaStatus(items:UploadedMedia[]){
  const reused=items.filter(item=>item.reused);
  const fresh=items.filter(item=>!item.reused);
  const notices=reused.map(item=>{
    const kind=item.kind==='image'?'picture':'video';
    return `${item.name} already exists. Using that ${kind} with ${annotationPhrase(item.annotation_count??0)}.`;
  });
  if(!notices.length)return fresh.length?'Media uploaded':'';
  if(!fresh.length)return notices.join(' ');
  return `Media uploaded. ${notices.join(' ')}`;
}

export function reusedMediaNotice(items:UploadedMedia[]){
  const reused=uniqueReused(items);
  if(!reused.length)return null;
  const allPictures=reused.every(item=>item.kind==='image');
  const allVideos=reused.every(item=>item.kind!=='image');
  let title='These files already exist';
  if(reused.length===1)title=reused[0].kind==='image'?'This picture already exists':'This video already exists';
  else if(allPictures)title='These pictures already exist';
  else if(allVideos)title='These videos already exist';
  const hint=reused.map(item=>`Using ${item.name} with ${annotationPhrase(item.annotation_count??0)}.`).join(' ');
  return {title,hint};
}

