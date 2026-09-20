import {useEffect,useRef} from 'react';

export function MaskHeatmap(props:{values:number[][]}){
  const canvas=useRef<HTMLCanvasElement>(null);
  useEffect(()=>{
    const node=canvas.current;
    const grid=props.values;
    if(!node||!grid.length||!grid[0]?.length)return;
    const height=grid.length;
    const width=grid[0].length;
    node.width=width;
    node.height=height;
    const ctx=node.getContext('2d');
    if(!ctx)return;
    const image=ctx.createImageData(width,height);
    for(let y=0;y<height;y++){
      for(let x=0;x<width;x++){
        const t=Math.max(0,Math.min(1,grid[y][x]??0));
        const i=(y*width+x)*4;
        image.data[i]=Math.round(18+t*237);
        image.data[i+1]=Math.round(28+t*110);
        image.data[i+2]=Math.round(48*(1-t)+18);
        image.data[i+3]=255;
      }
    }
    ctx.putImageData(image,0,0);
  },[props.values]);
  return <canvas ref={canvas} className="heatmap-canvas" aria-label="Annotation location heatmap"/>;
}
