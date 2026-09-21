import {forwardRef,useEffect,useImperativeHandle,useLayoutEffect,useRef,useState} from 'react';
import type {CSSProperties,PointerEvent as ReactPointerEvent} from 'react';
import type {BoxPrompt,Label,PromptPoint,ToolMode} from '../types';
import {brushStrokeUsesDetection,clampMenuPos,clickOutsideUnfocuses,paintOverlayCopy,panBy,selectDragStartsMarquee,selectEmptyRelease} from '../editorWorkflow';
import {MASK_FILL_ALPHA,alphaIntersectsBox,maskCentroid,outlineOffsets,overlayFillAlpha,overlayOutlineAlpha,overlayTone,unionMaskAlpha} from '../maskDraw';

export type MaskOverlay={id:number;color:string;url:string;name:string};

export interface AnnotationCanvasHandle{
  loadMaskBlob:(blob:Blob)=>Promise<void>;
  loadMaskDataUrl:(url:string|null)=>Promise<void>;
  mergeMaskBlob:(blob:Blob)=>Promise<void>;
  clearMask:()=>void;
  exportMaskDataUrl:()=>string|null;
  exportPng:()=>string;
  exportBounds:()=>{x:number;y:number;w:number;h:number}|null;
}

interface Props{
  imageUrl:string|null;
  points:PromptPoint[];
  box:BoxPrompt|null;
  tool:ToolMode;
  brushSize:number;
  zoom:number;
  disabled?:boolean;
  overlays:MaskOverlay[];
  focusedId:number|null;
  selectedIds:number[];
  labels:Label[];
  labelId:number|null;
  showLabelMenu?:boolean;
  onPoint:(p:PromptPoint)=>void;
  onBox:(b:BoxPrompt)=>void;
  onDirty:()=>void;
  onBeforeEdit:()=>void;
  onBrushStroke:()=>void;
  onSelect:(id:number,additive:boolean)=>void;
  onSelectIds:(ids:number[],additive:boolean)=>void;
  onUnfocus:()=>void;
  onLabelId:(id:number)=>void;
  onFinish:()=>void;
  finished?:boolean;
  finishedIds?:number[];
}

const MENU_POS_KEY='maskLabelBarPos';
function loadMenuPos(){
  try{
    const raw=localStorage.getItem(MENU_POS_KEY);
    if(!raw)return null;
    const value=JSON.parse(raw) as {x?:unknown;y?:unknown};
    if(typeof value.x==='number'&&typeof value.y==='number')return {x:value.x,y:value.y};
  }catch{}
  return null;
}
const loadImage=(src:string)=>new Promise<HTMLImageElement>((ok,bad)=>{const im=new Image();im.onload=()=>ok(im);im.onerror=()=>bad(new Error('Image load failed'));im.src=src});
const EMPTY_PNG='data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=';

function hexRgb(color:string):[number,number,number]{
  const value=color.replace('#','');
  if(value.length!==6)return [255,72,72];
  return [parseInt(value.slice(0,2),16),parseInt(value.slice(2,4),16),parseInt(value.slice(4,6),16)];
}

function binarizeMask(ctx:CanvasRenderingContext2D,img:CanvasImageSource,w:number,h:number){
  ctx.clearRect(0,0,w,h);
  ctx.drawImage(img,0,0,w,h);
  const data=ctx.getImageData(0,0,w,h);
  const px=data.data;
  for(let i=3;i<px.length;i+=4){
    px[i-3]=255;px[i-2]=255;px[i-1]=255;
    px[i]=px[i]>16?255:0;
  }
  ctx.putImageData(data,0,0);
}

function paintTint(ctx:CanvasRenderingContext2D,img:CanvasImageSource,color:string,alpha:number,w:number,h:number){
  const [r,g,b]=hexRgb(color);
  const tmp=document.createElement('canvas');
  tmp.width=w;tmp.height=h;
  const tctx=tmp.getContext('2d',{willReadFrequently:true});
  if(!tctx)return;
  binarizeMask(tctx,img,w,h);
  ctx.save();
  ctx.clearRect(0,0,w,h);
  ctx.drawImage(tmp,0,0);
  ctx.globalCompositeOperation='source-in';
  ctx.fillStyle=`rgba(${r},${g},${b},${alpha})`;
  ctx.fillRect(0,0,w,h);
  ctx.restore();
}

function paintWhiteRing(ctx:CanvasRenderingContext2D,img:CanvasImageSource,w:number,h:number,outlinePx:number,outlineAlpha:number){
  const bin=document.createElement('canvas');
  bin.width=w;bin.height=h;
  const bctx=bin.getContext('2d');
  if(!bctx)return;
  binarizeMask(bctx,img,w,h);
  const white=document.createElement('canvas');
  white.width=w;white.height=h;
  const wctx=white.getContext('2d');
  if(!wctx)return;
  wctx.drawImage(bin,0,0);
  wctx.globalCompositeOperation='source-in';
  wctx.fillStyle=`rgba(255,255,255,${outlineAlpha})`;
  wctx.fillRect(0,0,w,h);
  const ring=document.createElement('canvas');
  ring.width=w;ring.height=h;
  const rctx=ring.getContext('2d');
  if(!rctx)return;
  for(const off of outlineOffsets(outlinePx))rctx.drawImage(white,off.x,off.y);
  rctx.globalCompositeOperation='destination-out';
  rctx.drawImage(bin,0,0);
  ctx.drawImage(ring,0,0);
}

function paintOutlinedTint(ctx:CanvasRenderingContext2D,img:CanvasImageSource,color:string,alpha:number,w:number,h:number,outlinePx:number,outlineAlpha:number){
  paintTint(ctx,img,color,alpha,w,h);
  paintWhiteRing(ctx,img,w,h,outlinePx,outlineAlpha);
}

function layerOutlinePx(layer:HTMLCanvasElement){
  const displayW=layer.getBoundingClientRect().width;
  return Math.max(2,Math.round(2.2*layer.width/Math.max(1,displayW)));
}

function readBounds(canvas:HTMLCanvasElement){
  const ctx=canvas.getContext('2d',{willReadFrequently:true});
  if(!ctx)return null;
  const {width,height}=canvas;
  const data=ctx.getImageData(0,0,width,height).data;
  let minX=width,minY=height,maxX=0,maxY=0,found=false;
  for(let y=0;y<height;y++){
    for(let x=0;x<width;x++){
      if(data[(y*width+x)*4+3]>16){
        found=true;
        if(x<minX)minX=x;
        if(y<minY)minY=y;
        if(x>maxX)maxX=x;
        if(y>maxY)maxY=y;
      }
    }
  }
  return found?{x:minX,y:minY,w:maxX-minX+1,h:maxY-minY+1}:null;
}

export const AnnotationCanvas=forwardRef<AnnotationCanvasHandle,Props>(function AnnotationCanvas(props,ref){
  const wrapRef=useRef<HTMLDivElement|null>(null);
  const imgRef=useRef<HTMLImageElement|null>(null);
  const canvasRef=useRef<HTMLCanvasElement|null>(null);
  const overlayRef=useRef<HTMLCanvasElement|null>(null);
  const drawing=useRef(false);
  const last=useRef<{x:number;y:number}|null>(null);
  const boxStart=useRef<{x:number;y:number}|null>(null);
  const dragPan=useRef<{x:number;y:number;panX:number;panY:number}|null>(null);
  const overlayImgs=useRef<Record<number,HTMLImageElement>>({});
  const overlayAlpha=useRef<Record<number,Uint8ClampedArray>>({});
  const [size,setSize]=useState({width:1,height:1});
  const [pan,setPan]=useState({x:0,y:0});
  const [panning,setPanning]=useState(false);
  const [cursor,setCursor]=useState<{x:number;y:number}|null>(null);
  const [draftBox,setDraftBox]=useState<BoxPrompt|null>(null);
  const [menuOpen,setMenuOpen]=useState(false);
  const [bounds,setBounds]=useState<{x:number;y:number;w:number;h:number}|null>(null);
  const [menuStyle,setMenuStyle]=useState<CSSProperties>({display:'none'});
  const [overlayLabels,setOverlayLabels]=useState<{id:number;name:string;x:number;y:number}[]>([]);
  const [pinnedMenu,setPinnedMenu]=useState<{x:number;y:number}|null>(loadMenuPos);
  const [draggingMenu,setDraggingMenu]=useState(false);
  const menuRef=useRef<HTMLDivElement|null>(null);
  const dragMenu=useRef<{dx:number;dy:number;w:number;h:number}|null>(null);
  const labelColor=props.labels.find(label=>label.id===props.labelId)?.color??'#FF4848';
  const labelColorRef=useRef(labelColor);
  labelColorRef.current=labelColor;

  const paintOverlayLayer=(imgs:Record<number,HTMLImageElement>,alphas:Record<number,Uint8ClampedArray>)=>{
    const layer=overlayRef.current;
    if(!layer)return;
    const ctx=layer.getContext('2d');
    if(!ctx)return;
    ctx.clearRect(0,0,layer.width,layer.height);
    const outlinePx=layerOutlinePx(layer);
    const labels:{id:number;name:string;x:number;y:number}[]=[];
    for(const overlay of props.overlays){
      const img=imgs[overlay.id];
      const alpha=alphas[overlay.id];
      if(!img)continue;
      if(paintOverlayCopy(overlay.id,props.focusedId)){
        const tone=overlayTone(overlay.id,props.focusedId,props.selectedIds);
        const tmp=document.createElement('canvas');
        tmp.width=layer.width;tmp.height=layer.height;
        const tctx=tmp.getContext('2d');
        if(!tctx)continue;
        paintOutlinedTint(tctx,img,overlay.color,overlayFillAlpha(tone),layer.width,layer.height,outlinePx,overlayOutlineAlpha(tone));
        ctx.drawImage(tmp,0,0);
      }
      if(overlay.id===props.focusedId||!alpha)continue;
      const mw=img.naturalWidth||img.width;
      const mh=img.naturalHeight||img.height;
      const c=maskCentroid(alpha,mw,mh);
      if(c)labels.push({id:overlay.id,name:overlay.name,x:c.x/Math.max(1,mw)*layer.width,y:c.y/Math.max(1,mh)*layer.height});
    }
    const live=canvasRef.current;
    if(live)paintWhiteRing(ctx,live,layer.width,layer.height,outlinePx,overlayOutlineAlpha('focused'));
    setOverlayLabels(labels);
  };

  const refreshBounds=()=>{
    const c=canvasRef.current;
    setBounds(c?readBounds(c):null);
    paintOverlayLayer(overlayImgs.current,overlayAlpha.current);
  };

  const loadMaskDataUrl=async(url:string|null)=>{
    const c=canvasRef.current;
    if(!c)return;
    const ctx=c.getContext('2d');
    if(!ctx)return;
    ctx.clearRect(0,0,c.width,c.height);
    if(url){
      const im=await loadImage(url);
      paintTint(ctx,im,labelColorRef.current,MASK_FILL_ALPHA,c.width,c.height);
    }
    refreshBounds();
  };

  const mergeMaskBlob=async(blob:Blob)=>{
    const c=canvasRef.current;
    if(!c)return;
    const ctx=c.getContext('2d',{willReadFrequently:true});
    if(!ctx)return;
    const prev=ctx.getImageData(0,0,c.width,c.height);
    const url=URL.createObjectURL(blob);
    try{
      const im=await loadImage(url);
      const tmp=document.createElement('canvas');
      tmp.width=c.width;tmp.height=c.height;
      const tctx=tmp.getContext('2d',{willReadFrequently:true});
      if(!tctx)return;
      tctx.drawImage(im,0,0,c.width,c.height);
      const next=tctx.getImageData(0,0,c.width,c.height);
      const merged=unionMaskAlpha(prev.data,next.data);
      tctx.putImageData(new ImageData(merged,c.width,c.height),0,0);
      paintTint(ctx,tmp,labelColorRef.current,MASK_FILL_ALPHA,c.width,c.height);
    }finally{URL.revokeObjectURL(url)}
    refreshBounds();
  };

  useImperativeHandle(ref,()=>({
    async loadMaskBlob(blob){
      const url=URL.createObjectURL(blob);
      try{await loadMaskDataUrl(url)}finally{URL.revokeObjectURL(url)}
    },
    loadMaskDataUrl,
    mergeMaskBlob,
    clearMask(){
      const c=canvasRef.current;
      c?.getContext('2d')?.clearRect(0,0,c.width,c.height);
      setBounds(null);
    },
    exportMaskDataUrl(){
      const c=canvasRef.current;
      if(!c)return null;
      const ctx=c.getContext('2d',{willReadFrequently:true});
      if(!ctx)return null;
      const d=ctx.getImageData(0,0,c.width,c.height).data;
      for(let i=3;i<d.length;i+=4)if(d[i]>16)return c.toDataURL('image/png');
      return null;
    },
    exportPng(){return canvasRef.current?.toDataURL('image/png')??EMPTY_PNG},
    exportBounds(){return canvasRef.current?readBounds(canvasRef.current):null},
  }),[labelColor]);

  useEffect(()=>{setDraftBox(null);setMenuOpen(false);setBounds(null);setOverlayLabels([]);setPan({x:0,y:0})},[props.imageUrl]);

  useEffect(()=>{
    const c=canvasRef.current;
    if(!c||c.width<2)return;
    const ctx=c.getContext('2d');
    if(!ctx)return;
    const tmp=document.createElement('canvas');
    tmp.width=c.width;tmp.height=c.height;
    tmp.getContext('2d')!.drawImage(c,0,0);
    paintTint(ctx,tmp,labelColor,MASK_FILL_ALPHA,c.width,c.height);
    paintOverlayLayer(overlayImgs.current,overlayAlpha.current);
  },[labelColor]);

  useEffect(()=>{
    let stop=false;
    const nextImgs:Record<number,HTMLImageElement>={};
    const nextAlpha:Record<number,Uint8ClampedArray>={};
    Promise.all(props.overlays.map(async overlay=>{
      const im=await loadImage(overlay.url);
      const c=document.createElement('canvas');
      c.width=im.naturalWidth||im.width;
      c.height=im.naturalHeight||im.height;
      const ctx=c.getContext('2d',{willReadFrequently:true});
      if(ctx){ctx.drawImage(im,0,0);nextAlpha[overlay.id]=ctx.getImageData(0,0,c.width,c.height).data}
      nextImgs[overlay.id]=im;
    })).then(()=>{
      if(stop)return;
      overlayImgs.current=nextImgs;
      overlayAlpha.current=nextAlpha;
      paintOverlayLayer(nextImgs,nextAlpha);
    }).catch(()=>{});
    return()=>{stop=true};
  },[props.overlays,props.focusedId,props.selectedIds,size.width,size.height]);

  useLayoutEffect(()=>{
    if(draggingMenu)return;
    const wrap=wrapRef.current;
    const canvas=canvasRef.current;
    const menu=menuRef.current;
    if(!wrap||!props.imageUrl){setMenuStyle({display:'none'});return}
    const wr=wrap.getBoundingClientRect();
    const mw=menu?.offsetWidth||188;
    const mh=menu?.offsetHeight||40;
    if(pinnedMenu){
      const pos=clampMenuPos(pinnedMenu.x*wr.width,pinnedMenu.y*wr.height,wr.width,wr.height,mw,mh);
      setMenuStyle({position:'absolute',left:pos.left,top:pos.top,zIndex:6});
      return;
    }
    if(!canvas||!bounds){setMenuStyle({display:'none'});return}
    const cr=canvas.getBoundingClientRect();
    const sx=cr.width/Math.max(1,canvas.width);
    const sy=cr.height/Math.max(1,canvas.height);
    let left=cr.left-wr.left+(bounds.x+bounds.w)*sx+10;
    const top=Math.max(8,cr.top-wr.top+bounds.y*sy);
    if(left>wr.width-mw-8)left=Math.max(8,cr.left-wr.left+bounds.x*sx-mw-10);
    const pos=clampMenuPos(left,top,wr.width,wr.height,mw,mh);
    setMenuStyle({position:'absolute',left:pos.left,top:pos.top,zIndex:6});
  },[bounds,props.zoom,props.imageUrl,size,menuOpen,pinnedMenu,pan,draggingMenu]);

  const toImage=(e:ReactPointerEvent<HTMLCanvasElement>)=>{
    const c=canvasRef.current;
    if(!c)return null;
    const r=c.getBoundingClientRect();
    return {x:Math.max(0,Math.min(c.width,(e.clientX-r.left)/r.width*c.width)),y:Math.max(0,Math.min(c.height,(e.clientY-r.top)/r.height*c.height))};
  };

  const hitOverlay=(p:{x:number;y:number})=>{
    const c=canvasRef.current;
    if(c){
      const ctx=c.getContext('2d',{willReadFrequently:true});
      if(ctx){
        const x=Math.max(0,Math.min(c.width-1,Math.round(p.x)));
        const y=Math.max(0,Math.min(c.height-1,Math.round(p.y)));
        if(ctx.getImageData(x,y,1,1).data[3]>16&&props.focusedId!=null)return props.focusedId;
      }
    }
    for(let i=props.overlays.length-1;i>=0;i--){
      const overlay=props.overlays[i];
      const img=overlayImgs.current[overlay.id];
      const data=overlayAlpha.current[overlay.id];
      if(!img||!data)continue;
      const w=img.naturalWidth||img.width;
      const h=img.naturalHeight||img.height;
      const x=Math.max(0,Math.min(w-1,Math.round(p.x/size.width*w)));
      const y=Math.max(0,Math.min(h-1,Math.round(p.y/size.height*h)));
      if(data[(y*w+x)*4+3]>16)return overlay.id;
    }
    return null;
  };

  const hitsInBox=(b:BoxPrompt)=>{
    const ids:number[]=[];
    for(const overlay of props.overlays){
      const img=overlayImgs.current[overlay.id];
      const data=overlayAlpha.current[overlay.id];
      if(!img||!data)continue;
      const mw=img.naturalWidth||img.width;
      const mh=img.naturalHeight||img.height;
      if(alphaIntersectsBox(data,mw,mh,{
        x0:b[0]/Math.max(1,size.width)*mw,
        y0:b[1]/Math.max(1,size.height)*mh,
        x1:b[2]/Math.max(1,size.width)*mw,
        y1:b[3]/Math.max(1,size.height)*mh,
      }))ids.push(overlay.id);
    }
    return ids;
  };

  const drawBrush=(a:{x:number;y:number},b:{x:number;y:number})=>{
    const c=canvasRef.current;
    if(!c)return;
    const ctx=c.getContext('2d')!;
    const [r,g,bch]=hexRgb(labelColor);
    ctx.save();
    ctx.lineCap='round';ctx.lineJoin='round';ctx.lineWidth=props.brushSize;
    ctx.globalCompositeOperation=props.tool==='erase'?'destination-out':'source-over';
    ctx.strokeStyle=props.tool==='erase'?'rgba(0,0,0,1)':`rgba(${r},${g},${bch},${MASK_FILL_ALPHA})`;
    ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke();ctx.restore();
  };

  const down=(e:ReactPointerEvent<HTMLCanvasElement>)=>{
    if(props.disabled)return;
    if(props.tool==='pan'){
      if(e.button!==0)return;
      dragPan.current={x:e.clientX,y:e.clientY,panX:pan.x,panY:pan.y};
      setPanning(true);
      e.currentTarget.setPointerCapture(e.pointerId);
      return;
    }
    const p=toImage(e);
    if(!p)return;
    if(props.tool==='select'){
      if(e.button!==0)return;
      if(selectDragStartsMarquee()){
        boxStart.current=p;
        e.currentTarget.setPointerCapture(e.pointerId);
      }
      return;
    }
    if(e.button===2){e.preventDefault();props.onPoint({...p,positive:false});return}
    if(e.button!==0)return;
    if(props.tool==='positive'||props.tool==='negative'){props.onPoint({...p,positive:props.tool!=='negative'});return}
    if(props.tool==='box'){boxStart.current=p;setDraftBox([p.x,p.y,p.x,p.y]);e.currentTarget.setPointerCapture(e.pointerId);return}
    if(props.tool==='erase'&&props.focusedId!=null){
      const img=overlayImgs.current[props.focusedId];
      const c=canvasRef.current;
      const ctx=c?.getContext('2d',{willReadFrequently:true});
      if(img&&c&&ctx){
        const data=ctx.getImageData(0,0,c.width,c.height).data;
        let empty=true;
        for(let i=3;i<data.length;i+=4){if(data[i]>16){empty=false;break}}
        if(empty)paintTint(ctx,img,labelColor,MASK_FILL_ALPHA,c.width,c.height);
      }
    }
    if(clickOutsideUnfocuses(props.tool)&&props.focusedId!=null&&hitOverlay(p)==null){props.onUnfocus();return}
    if(!(props.tool==='brush'&&brushStrokeUsesDetection(props.focusedId!=null)==='detect'))props.onBeforeEdit();
    drawing.current=true;last.current=p;e.currentTarget.setPointerCapture(e.pointerId);drawBrush(p,p);props.onDirty();
  };

  const move=(e:ReactPointerEvent<HTMLCanvasElement>)=>{
    if(dragPan.current){
      setPan(panBy({x:dragPan.current.panX,y:dragPan.current.panY},{x:dragPan.current.x,y:dragPan.current.y},{x:e.clientX,y:e.clientY}));
      return;
    }
    const p=toImage(e);setCursor(p);if(!p)return;
    if((props.tool==='box'||props.tool==='select')&&boxStart.current){
      const s=boxStart.current;setDraftBox([Math.min(s.x,p.x),Math.min(s.y,p.y),Math.max(s.x,p.x),Math.max(s.y,p.y)]);return;
    }
    if(!drawing.current||!last.current)return;drawBrush(last.current,p);last.current=p;props.onDirty();
  };

  const up=(e:ReactPointerEvent<HTMLCanvasElement>)=>{
    if(dragPan.current){dragPan.current=null;setPanning(false)}
    if((props.tool==='box'||props.tool==='select')&&boxStart.current){
      const p=toImage(e);const s=boxStart.current;boxStart.current=null;
      if(p){
        const b:[number,number,number,number]=[Math.min(s.x,p.x),Math.min(s.y,p.y),Math.max(s.x,p.x),Math.max(s.y,p.y)];
        const w=b[2]-b[0],h=b[3]-b[1];
        if(props.tool==='select'){
          const additive=e.shiftKey||e.ctrlKey||e.metaKey;
          if(selectEmptyRelease(w,h)==='marquee'){
            const ids=hitsInBox(b);
            if(ids.length)props.onSelectIds(ids,additive);
            else props.onUnfocus();
          }else{
            const hit=hitOverlay(p);
            if(hit!=null)props.onSelect(hit,additive);
            else props.onUnfocus();
          }
        }else if(w>3&&h>3)props.onBox(b);
      }
      setDraftBox(null);
    }
    if(drawing.current){
      refreshBounds();
      if(props.tool==='brush')props.onBrushStroke();
    }
    drawing.current=false;last.current=null;
    try{e.currentTarget.releasePointerCapture(e.pointerId)}catch{}
  };

  const currentLabel=props.labels.find(label=>label.id===props.labelId);
  const hasMask=Boolean(bounds)||Boolean(props.focusedId)||Boolean(props.showLabelMenu);

  const pinMenuAt=(left:number,top:number)=>{
    const wrap=wrapRef.current;
    if(!wrap)return;
    const wr=wrap.getBoundingClientRect();
    const menu=menuRef.current;
    const pos=clampMenuPos(left,top,wr.width,wr.height,menu?.offsetWidth||188,menu?.offsetHeight||40);
    const next={x:pos.left/Math.max(1,wr.width),y:pos.top/Math.max(1,wr.height)};
    setPinnedMenu(next);
    localStorage.setItem(MENU_POS_KEY,JSON.stringify(next));
    setMenuStyle({position:'absolute',left:pos.left,top:pos.top,zIndex:6});
  };

  const startMenuDrag=(e:ReactPointerEvent<HTMLButtonElement>)=>{
    if(e.button!==0)return;
    const wrap=wrapRef.current;
    const menu=menuRef.current;
    if(!wrap||!menu)return;
    const wr=wrap.getBoundingClientRect();
    const mr=menu.getBoundingClientRect();
    dragMenu.current={dx:e.clientX-mr.left,dy:e.clientY-mr.top,w:mr.width,h:mr.height};
    setDraggingMenu(true);
    e.currentTarget.setPointerCapture(e.pointerId);
    e.preventDefault();
    e.stopPropagation();
  };

  const moveMenuDrag=(e:ReactPointerEvent<HTMLButtonElement>)=>{
    if(!dragMenu.current)return;
    const wrap=wrapRef.current;
    if(!wrap)return;
    const wr=wrap.getBoundingClientRect();
    const pos=clampMenuPos(e.clientX-wr.left-dragMenu.current.dx,e.clientY-wr.top-dragMenu.current.dy,wr.width,wr.height,dragMenu.current.w,dragMenu.current.h);
    setMenuStyle({position:'absolute',left:pos.left,top:pos.top,zIndex:6});
  };

  const endMenuDrag=(e:ReactPointerEvent<HTMLButtonElement>)=>{
    if(!dragMenu.current)return;
    const wrap=wrapRef.current;
    if(wrap){
      const wr=wrap.getBoundingClientRect();
      const pos=clampMenuPos(e.clientX-wr.left-dragMenu.current.dx,e.clientY-wr.top-dragMenu.current.dy,wr.width,wr.height,dragMenu.current.w,dragMenu.current.h);
      pinMenuAt(pos.left,pos.top);
    }
    dragMenu.current=null;
    setDraggingMenu(false);
  };

  const resetMenuDock=()=>{
    dragMenu.current=null;
    setDraggingMenu(false);
    setPinnedMenu(null);
    localStorage.removeItem(MENU_POS_KEY);
  };

  return <div className="canvas-scroll" ref={wrapRef} onContextMenu={e=>e.preventDefault()}>
    <div className="canvas-stage" style={{transform:`translate(${pan.x}px, ${pan.y}px) scale(${props.zoom})`}}>
      {props.imageUrl?<><img ref={imgRef} src={props.imageUrl} draggable={false} alt="annotation frame" onLoad={e=>{
        const im=e.currentTarget;
        setSize({width:im.naturalWidth,height:im.naturalHeight});
        for(const node of [canvasRef.current,overlayRef.current]){
          if(node&&(node.width!==im.naturalWidth||node.height!==im.naturalHeight)){
            node.width=im.naturalWidth;node.height=im.naturalHeight;
          }
        }
      }}/>
      <canvas ref={overlayRef} width={size.width} height={size.height} className="mask-canvas overlay-canvas"/>
      <canvas ref={canvasRef} width={size.width} height={size.height} className={`mask-canvas tool-${props.tool}${panning?' panning':''}`} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up} onPointerLeave={()=>setCursor(null)} onContextMenu={e=>e.preventDefault()}/>
      <svg className="prompt-layer" viewBox={`0 0 ${size.width} ${size.height}`} preserveAspectRatio="none">
        {props.points.map((p,i)=><g key={i}><circle cx={p.x} cy={p.y} r={9} className={p.positive?'point-pos':'point-neg'}/><circle cx={p.x} cy={p.y} r={2.5} className="point-core"/></g>)}
        {(draftBox??props.box)&&<rect x={(draftBox??props.box)![0]} y={(draftBox??props.box)![1]} width={(draftBox??props.box)![2]-(draftBox??props.box)![0]} height={(draftBox??props.box)![3]-(draftBox??props.box)![1]} className={props.tool==='select'?'prompt-box marquee':'prompt-box'}/>}
        {cursor&&(props.tool==='brush'||props.tool==='erase')&&<circle cx={cursor.x} cy={cursor.y} r={props.brushSize/2} className="brush-cursor"/>}
      </svg>
      {overlayLabels.map(item=>(
        <span key={item.id} className={`mask-name-chip${props.finishedIds?.includes(item.id)?' done':''}`} style={{left:item.x,top:item.y,transform:`translate(-50%,-50%) scale(${1/Math.max(.01,props.zoom)})`}}>{item.name}</span>
      ))}
      </>:<div className="empty-canvas"><strong>Select a video or image</strong><span>Choose a project, upload media, then start annotation.</span></div>}
    </div>
    {hasMask&&props.imageUrl&&<div ref={menuRef} className={`mask-label-menu${draggingMenu?' dragging':''}${pinnedMenu?' pinned':''}`} style={menuStyle}>
      <div className="mask-label-bar">
        <button type="button" className="mask-label-handle" title="Drag to move. Double-click to snap back to the mask." aria-label="Move class bar" onPointerDown={startMenuDrag} onPointerMove={moveMenuDrag} onPointerUp={endMenuDrag} onPointerCancel={endMenuDrag} onDoubleClick={resetMenuDock}>
          <svg width="10" height="16" viewBox="0 0 10 16" aria-hidden="true">
            <circle cx="3" cy="3" r="1.2"/><circle cx="7" cy="3" r="1.2"/>
            <circle cx="3" cy="8" r="1.2"/><circle cx="7" cy="8" r="1.2"/>
            <circle cx="3" cy="13" r="1.2"/><circle cx="7" cy="13" r="1.2"/>
          </svg>
        </button>
        <button type="button" className="mask-label-toggle" onClick={()=>setMenuOpen(open=>!open)}>
          <i style={{background:currentLabel?.color??'#4e8ef7'}}/>
          <span>{currentLabel?.name??'Choose class'}</span>
          <b>▾</b>
        </button>
        <button type="button" className={`mask-finish${props.finished?' on':''}`} title={props.finished?'Mark this mask not finished':'Mark this mask finished'} aria-label={props.finished?'Mark this mask not finished':'Mark this mask finished'} aria-pressed={Boolean(props.finished)} onClick={props.onFinish}>
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <rect x="4" y="4" width="16" height="16" rx="4"/>
            <path d="m7.8 12.2 2.8 2.8 5.6-6"/>
          </svg>
        </button>
      </div>
      {menuOpen&&<div className="mask-label-list">
        {props.labels.map(label=>(
          <button type="button" key={label.id} className={label.id===props.labelId?'active':''} onClick={()=>{props.onLabelId(label.id);setMenuOpen(false)}}>
            <i style={{background:label.color}}/>
            <span>{label.name}</span>
          </button>
        ))}
      </div>}
    </div>}
  </div>;
});
