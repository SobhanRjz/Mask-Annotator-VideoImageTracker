export function slugifyProjectName(name:string){
  const slug=name.normalize('NFKD').replace(/[^\x00-\x7F]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,80);
  return slug||'project';
}

export function projectHref(project:{slug?:string|null;id:number},path=''){
  return `/projects/${project.slug||project.id}${path}`;
}

export function coveragePercent(annotated:number,extracted:number){
  if(!extracted)return 0;
  return Math.round((annotated/extracted)*1000)/10;
}

export function typedNameMatches(typed:string,expected:string){
  return typed.trim()===expected.trim()&&expected.trim().length>0;
}

const MONTHS=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

export function formatProjectDate(value:string|null|undefined){
  const match=/^(\d{4})-(\d{2})-(\d{2})/.exec(String(value||'').trim());
  if(!match)return '';
  const month=MONTHS[Number(match[2])-1];
  if(!month)return '';
  return `${Number(match[3])} ${month} ${match[1]}`;
}

export function projectBadge(annotationCount:number,date:string|null|undefined){
  const masks=`${annotationCount} mask${annotationCount===1?'':'s'}`;
  const when=formatProjectDate(date);
  return when?`${masks} · ${when}`:masks;
}
