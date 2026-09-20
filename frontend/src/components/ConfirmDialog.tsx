import {useEffect,useRef} from 'react';

import {TrashIcon} from './TrashIcon';

export function ConfirmDialog(props:{
  title:string;
  hint?:string;
  confirmLabel?:string;
  cancelLabel?:string;
  busy?:boolean;
  onCancel:()=>void;
  onConfirm:()=>void;
}){
  const confirm=useRef<HTMLButtonElement>(null);
  useEffect(()=>{confirm.current?.focus()},[]);
  return (
    <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!props.busy)props.onCancel()}}>
      <div
        className="modal confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        onKeyDown={e=>{if(e.key==='Escape'&&!props.busy)props.onCancel()}}
      >
        <div className="confirm-mark" aria-hidden="true"><TrashIcon size={22}/></div>
        <h2 id="confirm-title">{props.title}</h2>
        {props.hint&&<p>{props.hint}</p>}
        <div className="modal-actions">
          <button type="button" onClick={props.onCancel} disabled={props.busy}>{props.cancelLabel??'Cancel'}</button>
          <button ref={confirm} type="button" className="danger" onClick={props.onConfirm} disabled={props.busy}>
            {props.busy?'Deleting…':(props.confirmLabel??'Delete')}
          </button>
        </div>
      </div>
    </div>
  );
}
