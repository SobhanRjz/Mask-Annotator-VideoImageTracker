export function formatSpent(seconds:number){
  const total=Math.max(0,Math.round(seconds||0));
  const h=Math.floor(total/3600);
  const m=Math.floor((total%3600)/60);
  const s=total%60;
  if(h>0)return `${h}h ${m}m`;
  if(m>0)return `${m}m ${s}s`;
  return `${s}s`;
}

export function formatClock(seconds:number){
  const total=Math.max(0,Math.round(seconds||0));
  const h=Math.floor(total/3600);
  const m=Math.floor((total%3600)/60);
  const s=total%60;
  if(h>0)return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
}

export function TimeChip(props:{seconds:number;live?:boolean;compact?:boolean}){
  const label=props.live?formatClock(props.seconds):formatSpent(props.seconds);
  return <span className={`time-chip${props.live?' live':''}${props.compact?' compact':''}`} title="Time spent annotating">
    {props.live&&<i className="time-pulse"/>}
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2"><circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/></svg>
    <b>{label}</b>
  </span>;
}
