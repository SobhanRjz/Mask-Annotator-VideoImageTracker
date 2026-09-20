import {FormEvent,useEffect,useRef,useState} from 'react';
import {slugifyProjectName} from '../projectSlug';

export function NameDialog(props:{
  title:string;
  hint?:string;
  nameLabel?:string;
  extraLabel?:string;
  extraPlaceholder?:string;
  namePlaceholder?:string;
  submitLabel:string;
  busy?:boolean;
  showSlug?:boolean;
  onCancel:()=>void;
  onSubmit:(name:string,extra:string)=>void;
}){
  const [name,setName]=useState('');
  const [extra,setExtra]=useState('');
  const input=useRef<HTMLInputElement>(null);
  useEffect(()=>{input.current?.focus()},[]);
  const submit=(e:FormEvent)=>{
    e.preventDefault();
    const n=name.trim();
    if(!n||props.busy)return;
    props.onSubmit(n,extra.trim());
  };
  return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!props.busy)props.onCancel()}}>
    <form className="modal" onSubmit={submit} onKeyDown={e=>{if(e.key==='Escape'&&!props.busy)props.onCancel()}}>
      <h2>{props.title}</h2>
      {props.hint&&<p>{props.hint}</p>}
      <label>{props.nameLabel??'Name'}
        <input ref={input} value={name} onChange={e=>setName(e.target.value)} required maxLength={120} placeholder={props.namePlaceholder??''} autoComplete="off"/>
      </label>
      {props.showSlug&&<p className="slug-preview">Lives at <code>/projects/{slugifyProjectName(name)}</code>. Names must be unique.</p>}
      {props.extraLabel&&<label>{props.extraLabel}
        <input value={extra} onChange={e=>setExtra(e.target.value)} maxLength={240} placeholder={props.extraPlaceholder??''} autoComplete="off"/>
      </label>}
      <div className="modal-actions">
        <button type="button" onClick={props.onCancel} disabled={props.busy}>Cancel</button>
        <button type="submit" className="primary" disabled={props.busy||!name.trim()}>{props.busy?'Creating…':props.submitLabel}</button>
      </div>
    </form>
  </div>;
}
