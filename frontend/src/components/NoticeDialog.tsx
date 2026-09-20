import {useEffect,useRef} from 'react';

export function NoticeDialog(props:{
  title:string;
  hint?:string;
  confirmLabel?:string;
  onClose:()=>void;
}){
  const confirm=useRef<HTMLButtonElement>(null);
  useEffect(()=>{confirm.current?.focus()},[]);
  return (
    <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)props.onClose()}}>
      <div
        className="modal confirm-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="notice-title"
        onKeyDown={e=>{if(e.key==='Escape'||e.key==='Enter')props.onClose()}}
      >
        <div className="confirm-mark info" aria-hidden="true">i</div>
        <h2 id="notice-title">{props.title}</h2>
        {props.hint&&<p>{props.hint}</p>}
        <div className="modal-actions">
          <button ref={confirm} type="button" className="primary" onClick={props.onClose}>
            {props.confirmLabel??'OK'}
          </button>
        </div>
      </div>
    </div>
  );
}
