type HeatGrid={width:number;height:number;values:number[][]};
type ResumeTarget={project_id:number;project_slug:string|null;media_id:number|null;frame:number|null};

export function continueHref(target:ResumeTarget|null|undefined){
  if(!target)return '/projects';
  const slug=target.project_slug||String(target.project_id);
  if(target.media_id==null)return `/projects/${slug}`;
  const frame=target.frame&&target.frame>0?`?frame=${target.frame}`:'';
  return `/projects/${slug}/media/${target.media_id}${frame}`;
}

export function defectTotal(counts:number[]){
  return counts.reduce((sum,value)=>sum+value,0);
}

export function defectShare(count:number,total:number){
  if(!total)return 0;
  return Math.round((count/total)*100);
}

export function remainingFrames(extracted:number,annotated:number){
  return Math.max(0,extracted-annotated);
}

export function annotationPace(annotated:number,seconds:number){
  if(!annotated||!seconds)return 0;
  return Math.round(annotated/(seconds/3600));
}

export function heatmapForFilter(report:{heatmap:HeatGrid;heatmaps?:Record<string,HeatGrid>},filter:string):HeatGrid{
  if(filter==='all')return report.heatmap;
  return report.heatmaps?.[filter]??{
    width:report.heatmap.width,
    height:report.heatmap.height,
    values:report.heatmap.values.map(row=>row.map(()=>0)),
  };
}
