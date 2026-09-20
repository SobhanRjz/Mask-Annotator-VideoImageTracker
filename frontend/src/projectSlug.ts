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
