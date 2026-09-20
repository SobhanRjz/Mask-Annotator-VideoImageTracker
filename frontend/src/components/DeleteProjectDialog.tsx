import {FormEvent,useEffect,useRef,useState} from 'react';
import {typedNameMatches} from '../projectSlug';
import {TrashIcon} from './TrashIcon';

export function DeleteProjectDialog(props:{
  name:string;
  busy?:boolean;
  busyLabel?:string;
  onCancel:()=>void;
  onConfirm:(downloadBackup:boolean)=>void;
}){
  const [typed,setTyped]=useState('');
  const [copied,setCopied]=useState(false);
  const [backup,setBackup]=useState(true);
  const input=useRef<HTMLInputElement>(null);
  useEffect(()=>{input.current?.focus()},[]);
  const matches=typedNameMatches(typed,props.name);
  const copyName=async()=>{
    const text=props.name;
    try{
      await navigator.clipboard.writeText(text);
    }catch{
      const range=document.createRange();
      const node=document.getElementById('delete-project-name');
      if(!node)return;
      range.selectNodeContents(node);
      const selection=window.getSelection();
      selection?.removeAllRanges();
      selection?.addRange(range);
    }
    setCopied(true);
    input.current?.focus();
    window.setTimeout(()=>setCopied(false),1600);
  };
  const submit=(e:FormEvent)=>{
    e.preventDefault();
    if(!matches||props.busy)return;
    props.onConfirm(backup);
  };
  return (
    <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!props.busy)props.onCancel()}}>
      <form
        className="modal confirm-modal confirm-typed"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-project-title"
        onSubmit={submit}
        onKeyDown={e=>{if(e.key==='Escape'&&!props.busy)props.onCancel()}}
      >
        <div className="confirm-mark" aria-hidden="true"><TrashIcon size={22}/></div>
        <h2 id="delete-project-title">Delete this project?</h2>
        <p>This permanently removes media, masks, and labels. Download a recovery backup first so you can import the project later.</p>
        <label className="confirm-backup">
          <input type="checkbox" checked={backup} onChange={e=>setBackup(e.target.checked)} disabled={props.busy}/>
          <span>Download recovery backup (media, masks, excluded frames, and labels)</span>
        </label>
        <div className="confirm-name">
          <strong id="delete-project-name">{props.name}</strong>
          <button type="button" className="ghost" onClick={()=>{void copyName()}} disabled={props.busy}>
            {copied?'Copied':'Copy'}
          </button>
        </div>
        <label>Project name
          <input
            ref={input}
            value={typed}
            onChange={e=>setTyped(e.target.value)}
            placeholder="Paste or type the name"
            autoComplete="off"
            spellCheck={false}
            disabled={props.busy}
          />
        </label>
        <div className="modal-actions">
          <button type="button" onClick={props.onCancel} disabled={props.busy}>Cancel</button>
          <button type="submit" className="danger" disabled={props.busy||!matches}>
            {props.busy?(props.busyLabel??'Deleting…'):(backup?'Save backup and delete':'Delete')}
          </button>
        </div>
      </form>
    </div>
  );
}
