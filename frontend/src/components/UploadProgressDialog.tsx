export type UploadProgressRow={
  name:string;
  loaded:number;
  total:number;
  status:'queued'|'uploading'|'complete'|'failed';
  error?:string;
};

function percent(row:UploadProgressRow){
  if(row.status==='complete')return 100;
  if(!row.total)return 0;
  return Math.max(0,Math.min(100,Math.round(row.loaded/row.total*100)));
}

export function UploadProgressDialog(props:{
  rows:UploadProgressRow[];
  onClose:()=>void;
}){
  const done=props.rows.every(row=>row.status==='complete'||row.status==='failed');
  return <div className="modal-backdrop">
    <div className="modal upload-progress-modal" role="dialog" aria-modal="true" aria-labelledby="upload-title">
      <h2 id="upload-title">Uploading media</h2>
      <p>Keep this window open while the selected videos and images are copied into the project.</p>
      <div className="upload-progress-list">
        {props.rows.map(row=><div className="upload-progress-row" key={row.name}>
          <div className="upload-progress-heading">
            <strong title={row.name}>{row.name}</strong>
            <span>{row.status==='failed'?'Failed':row.status==='complete'?'Complete':`${percent(row)}%`}</span>
          </div>
          <div className="progress"><i style={{width:`${percent(row)}%`}}/></div>
          {row.error&&<small className="error-inline">{row.error}</small>}
        </div>)}
      </div>
      <div className="modal-actions">
        <button type="button" onClick={props.onClose} disabled={!done}>{done?'Close':'Uploading…'}</button>
      </div>
    </div>
  </div>;
}
