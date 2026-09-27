import {useEffect,useRef,useState} from 'react';
import * as api from '../api/client';
import {ensureUniqueColor,uniqueColor} from '../labelColor';
import type {DefectCatalog,DefectLabel} from '../types';

type DraftLabel=DefectLabel&{key:string};

function sameLabels(left:DefectLabel[],right:DefectLabel[]){
  if(left.length!==right.length)return false;
  return left.every((item,index)=>item.name===right[index].name&&item.color.toUpperCase()===right[index].color.toUpperCase());
}

export function DefectLabelEditor(props:{ready:boolean}){
  const keyRef=useRef(0);
  const [saved,setSaved]=useState<DefectCatalog|null>(null);
  const [rows,setRows]=useState<DraftLabel[]>([]);
  const [notice,setNotice]=useState<string|null>(null);
  const [error,setError]=useState<string|null>(null);
  const [saving,setSaving]=useState(false);
  const nextKey=()=>`label-${keyRef.current++}`;
  const apply=(catalog:DefectCatalog)=>{
    setSaved(catalog);
    setRows(catalog.labels.map(label=>({...label,key:nextKey()})));
  };

  useEffect(()=>{
    if(!props.ready)return;
    let cancel=false;
    api.getDefectLabels().then(catalog=>{
      if(cancel)return;
      apply(catalog);
      setError(null);
    }).catch(reason=>{
      if(!cancel)setError(reason instanceof Error?reason.message:String(reason));
    });
    return()=>{cancel=true};
  },[props.ready]);

  const dirty=saved!=null&&!sameLabels(rows.map(({name,color})=>({name,color})),saved.labels);
  const update=(key:string,patch:Partial<DefectLabel>)=>{
    setNotice(null);
    setRows(current=>current.map(row=>row.key===key?{...row,...patch}:row));
  };

  const save=async(labels:DefectLabel[])=>{
    const blank=labels.some(label=>!label.name.trim());
    if(blank){
      setNotice('Each defect label needs a name.');
      return;
    }
    const names=labels.map(label=>label.name.trim().toLowerCase());
    if(new Set(names).size!==names.length){
      setNotice('Label names must be unique.');
      return;
    }
    setSaving(true);setError(null);setNotice(null);
    try{
      const catalog=await api.saveDefectLabels(labels.map(label=>({name:label.name.trim(),color:label.color})));
      apply(catalog);
      setNotice(catalog.custom?'Saved. New projects copy this set.':'Using the built-in labels for new projects.');
    }catch(reason){
      setError(reason instanceof Error?reason.message:String(reason));
    }finally{setSaving(false)}
  };

  return <section className="catalog-labels">
    <div className="section-title">
      <div>
        <div className="panel-kicker">SHARED LABELS</div>
        <h2>Defect labels</h2>
        <p>{saved?.custom
          ? 'New projects copy this set. A project keeps the labels it was created with, and those names and colors are not edited inside the project.'
          : 'New projects use this built-in set until you save your own. Names and colors are not edited inside a project.'}</p>
      </div>
      <div className="catalog-label-actions">
        <button type="button" onClick={()=>setRows(current=>[...current,{key:nextKey(),name:'',color:uniqueColor(current.map(row=>row.color))}])} disabled={!props.ready||saving}>+ Add</button>
        {saved?.custom&&<button type="button" onClick={()=>{
          if(confirm('New projects will use the built-in defect labels. Projects already created stay as they are.'))void save([]);
        }} disabled={saving}>Built-in defaults</button>}
        <button type="button" className="primary" onClick={()=>void save(rows)} disabled={!props.ready||saving||!dirty}>Save</button>
      </div>
    </div>
    <div className="catalog-label-list">
      {rows.map(row=>(
        <div className="catalog-label-row" key={row.key}>
          <label className="swatch" title="Label color">
            <input type="color" aria-label={`${row.name||'New label'} color`} value={row.color.toLowerCase()} onChange={event=>{
              const color=ensureUniqueColor(event.target.value,rows.filter(item=>item.key!==row.key).map(item=>item.color));
              update(row.key,{color});
            }}/>
          </label>
          <input type="text" aria-label="Defect label name" value={row.name} placeholder="Label name" onChange={event=>update(row.key,{name:event.target.value})}/>
          <button type="button" className="ghost danger-text" aria-label={`Remove ${row.name||'label'}`} onClick={()=>setRows(current=>current.filter(item=>item.key!==row.key))}>×</button>
        </div>
      ))}
    </div>
    {notice&&<p className="catalog-label-note">{notice}</p>}
    {error&&<p className="catalog-label-note error">{error}</p>}
  </section>;
}
