const PALETTE=[
  '#51B56D','#E45B5B','#F29D49','#9A73E8','#4FA3E3',
  '#D85883','#D4B03D','#5FC6B0','#F06292','#26A69A',
  '#FF8A65','#7E57C2','#29B6F6','#9CCC65','#FF7043',
  '#5C6BC0','#26C6DA','#EC407A','#8D6E63','#42A5F5',
  '#66BB6A','#FFA726','#AB47BC','#78909C',
];

function clampByte(n:number){return Math.max(0,Math.min(255,Math.round(n)))}

export function normalizeHex(color:string){
  let value=(color||'').trim().replace('#','');
  if(value.length===3)value=value.split('').map(ch=>ch+ch).join('');
  if(!/^[0-9a-fA-F]{6}$/.test(value))return '#4E8EF7';
  return `#${value.toUpperCase()}`;
}

function hslHex(hue:number,saturation:number,lightness:number){
  const h=((hue%360)+360)%360;
  const c=(1-Math.abs(2*lightness-1))*saturation;
  const x=c*(1-Math.abs((h/60)%2-1));
  const m=lightness-c/2;
  let r=0,g=0,b=0;
  if(h<60)[r,g,b]=[c,x,0];
  else if(h<120)[r,g,b]=[x,c,0];
  else if(h<180)[r,g,b]=[0,c,x];
  else if(h<240)[r,g,b]=[0,x,c];
  else if(h<300)[r,g,b]=[x,0,c];
  else [r,g,b]=[c,0,x];
  return `#${[r,g,b].map(ch=>clampByte((ch+m)*255).toString(16).padStart(2,'0')).join('').toUpperCase()}`;
}

export function uniqueColor(existing:string[]){
  const used=new Set(existing.map(normalizeHex));
  const free=PALETTE.find(color=>!used.has(color));
  if(free)return free;
  for(let i=0;i<720;i++){
    const candidate=hslHex(i*137.508,0.62,0.52);
    if(!used.has(candidate))return candidate;
  }
  return hslHex(existing.length*137.508,0.62,0.52);
}

export function ensureUniqueColor(color:string,existing:string[]){
  const used=new Set(existing.map(normalizeHex));
  const candidate=normalizeHex(color);
  if(!used.has(candidate))return candidate;
  for(let hue=0;hue<360;hue+=11){
    const shifted=hslHex(hue,0.62,0.52);
    if(!used.has(shifted))return shifted;
  }
  return uniqueColor([...used]);
}
