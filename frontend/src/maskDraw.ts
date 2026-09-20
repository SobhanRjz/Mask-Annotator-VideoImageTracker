export type OverlayTone='idle'|'selected'|'focused';

export const MASK_FILL_ALPHA=.2;

export function maskCentroid(data:Uint8ClampedArray,width:number,height:number){
  let sx=0,sy=0,n=0;
  for(let y=0;y<height;y++){
    for(let x=0;x<width;x++){
      if(data[(y*width+x)*4+3]>16){sx+=x;sy+=y;n++}
    }
  }
  return n?{x:sx/n,y:sy/n}:null;
}

export function overlayFillAlpha(tone:OverlayTone|boolean){
  if(tone===true||tone==='focused')return MASK_FILL_ALPHA;
  if(tone==='selected')return .16;
  return .12;
}

export function overlayOutlineAlpha(tone:OverlayTone|boolean){
  if(tone===true||tone==='focused')return .95;
  if(tone==='selected')return .9;
  return .82;
}

export function overlayTone(id:number,focusedId:number|null,selectedIds:number[]):OverlayTone{
  if(id===focusedId)return 'focused';
  if(selectedIds.includes(id))return 'selected';
  return 'idle';
}

export function outlineOffsets(radius:number){
  const r=Math.max(1,Math.round(radius));
  const pts:{x:number;y:number}[]=[];
  for(let dy=-r;dy<=r;dy++){
    for(let dx=-r;dx<=r;dx++){
      if(dx===0&&dy===0)continue;
      if(dx*dx+dy*dy<=r*r)pts.push({x:dx,y:dy});
    }
  }
  return pts;
}

export function unionMaskAlpha(a:Uint8ClampedArray,b:Uint8ClampedArray){
  const out=new Uint8ClampedArray(a.length);
  const n=Math.min(a.length,b.length);
  for(let i=0;i<n;i+=4){
    const on=a[i+3]>16||b[i+3]>16;
    out[i]=255;out[i+1]=255;out[i+2]=255;out[i+3]=on?255:0;
  }
  return out;
}

export function alphaIntersectsBox(data:Uint8ClampedArray,width:number,height:number,box:{x0:number;y0:number;x1:number;y1:number}){
  const x0=Math.max(0,Math.min(width-1,Math.floor(Math.min(box.x0,box.x1))));
  const x1=Math.max(0,Math.min(width-1,Math.floor(Math.max(box.x0,box.x1))));
  const y0=Math.max(0,Math.min(height-1,Math.floor(Math.min(box.y0,box.y1))));
  const y1=Math.max(0,Math.min(height-1,Math.floor(Math.max(box.y0,box.y1))));
  const step=Math.max(1,Math.round(Math.max(x1-x0,y1-y0)/240));
  for(let y=y0;y<=y1;y+=step){
    for(let x=x0;x<=x1;x+=step){
      if(data[(y*width+x)*4+3]>16)return true;
    }
  }
  return false;
}
