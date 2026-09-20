import type {ExportFormat} from './types';

export type ExportOptions={
  scope:'all'|'project';
  projectId:number|null;
  format:ExportFormat;
  includeUnannotated:boolean;
  includeAuto:boolean;
  includeManual:boolean;
};

export function defaultExportOptions(projectId:number|null):ExportOptions{
  return {
    scope:projectId==null?'all':'project',
    projectId,
    format:'coco',
    includeUnannotated:true,
    includeAuto:true,
    includeManual:true,
  };
}

export function exportHasContent(options:ExportOptions){
  return options.includeUnannotated||options.includeAuto||options.includeManual;
}

export function exportProjectIds(options:ExportOptions){
  if(options.scope==='all')return null;
  return options.projectId==null?null:[options.projectId];
}

export function preparingExportLabel(status:string,progress:number,message?:string){
  if(status==='completed')return 'Export ready';
  if(status==='failed')return 'Export failed';
  if(status==='cancelled')return 'Export cancelled';
  return message||`Preparing the export… ${Math.max(0,Math.min(100,progress))}%`;
}
