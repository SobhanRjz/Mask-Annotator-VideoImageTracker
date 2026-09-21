import {useEffect,useMemo,useRef,useState,type CSSProperties,type ReactNode} from 'react';
import {Navigate,Outlet,Route,Routes,useLocation,useNavigate,useParams} from 'react-router-dom';
import * as api from './api/client';
import {AnnotationCanvas,type AnnotationCanvasHandle,type MaskOverlay} from './components/AnnotationCanvas';
import {AppNav} from './components/AppNav';
import {ConfirmDialog} from './components/ConfirmDialog';
import {DashboardPage} from './components/DashboardPage';
import {DeleteProjectDialog} from './components/DeleteProjectDialog';
import {ExportDialog} from './components/ExportDialog';
import {ExtractDialog} from './components/ExtractDialog';
import {NameDialog} from './components/NameDialog';
import {NoticeDialog} from './components/NoticeDialog';
import {DoneCheck,ProjectWorkspace} from './components/ProjectWorkspace';
import {ProjectsPage} from './components/ProjectsPage';
import {SettingsPage} from './components/SettingsPage';
import {TimeChip} from './components/TimeChip';
import {mediaReady,type Annotation,type BoxPrompt,type FrameInfo,type Label,type Media,type Project,type ProjectSummary,type PromptPoint,type ToolMode,type TrackingJob} from './types';
import {annotatedFrameCount,acceptedMaskId,boxStartsNewInstance,brushBoundsToBox,brushStrokeUsesDetection,closeSessionAfterPredict,displayIndex,filterFrames,fromDisplayIndex,idsToDelete,idsToDropOnUndo,idsToTrack,keepPromptsAfterPredict,maskUrlForPrompt,mergeSelection,toggleSelection,toolAfterGeneratedMask,trackButtonLabel,trackSeedsMatchFrom,type FrameStatusFilter} from './editorWorkflow';
import {picturesComplete,stepStill,stillFrameRows,stillIndex,stillsOf,trackCursor,trackLastIndex,trackSeedMediaId} from './mediaLibrary';
import {ensureUniqueColor,uniqueColor} from './labelColor';
import {projectHref} from './projectSlug';
import {reusedMediaNotice,reusedMediaStatus} from './uploadStatus';

const loadSetting=(k:string,fallback:string)=>localStorage.getItem(k)??fallback;

export default function App(){
  return (
    <Routes>
      <Route element={<Workspace/>}>
        <Route index element={<></>}/>
        <Route path="projects" element={<Outlet/>}>
          <Route index element={<></>}/>
          <Route path=":projectSlug" element={<Outlet/>}>
            <Route path="media/:mediaId" element={<></>}/>
          </Route>
        </Route>
        <Route path="settings" element={<></>}/>
      </Route>
      <Route path="*" element={<Navigate to="/" replace/>}/>
    </Routes>
  );
}

function Workspace(){
  const canvas=useRef<AnnotationCanvasHandle|null>(null);
  const navigate=useNavigate();
  const location=useLocation();
  const {projectSlug,mediaId:mediaIdParam}=useParams();
  const mediaId=mediaIdParam?Number(mediaIdParam):null;

  const [projects,setProjects]=useState<ProjectSummary[]>([]);
  const [project,setProject]=useState<Project|null>(null);
  const [media,setMedia]=useState<Media|null>(null);
  const [frame,setFrame]=useState(0);
  const [frames,setFrames]=useState<FrameInfo[]>([]);
  const [selected,setSelected]=useState<Annotation|null>(null);
  const [labelId,setLabelId]=useState<number|null>(null);
  const [tool,setTool]=useState<ToolMode>('select');
  const [brushSize,setBrushSize]=useState(15);
  const [zoom,setZoom]=useState(1);
  const [points,setPoints]=useState<PromptPoint[]>([]);
  const [box,setBox]=useState<BoxPrompt|null>(null);
  const [promptId,setPromptId]=useState<string|null>(null);
  const promptIdRef=useRef<string|null>(null);
  const saveInFlight=useRef<Promise<Annotation|null>|null>(null);
  const [promptBusy,setPromptBusy]=useState(false);
  const [dirty,setDirty]=useState(false);
  const [autoSave,setAutoSave]=useState(loadSetting('autosave','true')==='true');
  const [autoSaveSec,setAutoSaveSec]=useState(Number(loadSetting('autosaveSec','3'))||3);
  const [saveState,setSaveState]=useState('Saved');
  const [trackFrom,setTrackFrom]=useState(0);
  const [target,setTarget]=useState(0);
  const [trackStep,setTrackStep]=useState(1);
  const [replaceAuto,setReplaceAuto]=useState(true);
  const [trackJob,setTrackJob]=useState<TrackingJob|null>(null);
  const [status,setStatus]=useState('Ready');
  const [error,setError]=useState<string|null>(null);
  const [busy,setBusy]=useState(false);
  const [showProjectForm,setShowProjectForm]=useState(false);
  const [showExport,setShowExport]=useState(false);
  const [extractQueue,setExtractQueue]=useState<Media[]>([]);
  const [boot,setBoot]=useState<'loading'|'waiting'|'ready'>('loading');
  const [overlays,setOverlays]=useState<MaskOverlay[]>([]);
  const [selectedIds,setSelectedIds]=useState<number[]>([]);
  const [finishedIds,setFinishedIds]=useState<number[]>([]);
  const [frameAnns,setFrameAnns]=useState<Annotation[]>([]);
  const [spent,setSpent]=useState(0);
  const [canUndo,setCanUndo]=useState(false);
  const [canRedo,setCanRedo]=useState(false);
  const [pendingDelete,setPendingDelete]=useState<
    | {kind:'annotations';ids:number[];title:string;hint:string}
    | {kind:'project';ref:string|number;name:string}
    | {kind:'stills';count:number}
    | null
  >(null);
  const [deleteBusy,setDeleteBusy]=useState(false);
  const [deleteBusyLabel,setDeleteBusyLabel]=useState('Deleting…');
  const [reusedNotice,setReusedNotice]=useState<{title:string;hint:string}|null>(null);
  const [frameStatus,setFrameStatus]=useState<FrameStatusFilter>('all');
  const [frameLabelIds,setFrameLabelIds]=useState<number[]>([]);
  const [stillFrames,setStillFrames]=useState<Record<number,FrameInfo>>({});
  const pendingStillEdit=useRef<number|null>(null);
  const historyPast=useRef<{mask:string|null;labelId:number|null;selected:Annotation|null;points:PromptPoint[];box:BoxPrompt|null;annIds:number[]}[]>([]);
  const historyFuture=useRef<{mask:string|null;labelId:number|null;selected:Annotation|null;points:PromptPoint[];box:BoxPrompt|null;annIds:number[]}[]>([]);
  const editorRef=useRef({labelId:null as number|null,selected:null as Annotation|null,points:[] as PromptPoint[],box:null as BoxPrompt|null});
  const annIdsRef=useRef<number[]>([]);
  const promptGen=useRef(0);

  const view=mediaId!=null?(media?'annotate':'loading'):projectSlug?(project?'project':'loading'):location.pathname.startsWith('/projects')?'projects':location.pathname.startsWith('/settings')?'settings':'dashboard';
  const lastFrame=Math.max(0,(media?.frame_count??1)-1);
  const stills=useMemo(()=>stillsOf(project?.media??[]),[project?.media]);
  const stillPos=media?stillIndex(stills,media.id):-1;
  const isStill=media?.kind==='image';
  const lastTrack=trackLastIndex(media?.kind??'video',stills.length,media?.frame_count??1);
  const trackPos=trackCursor(media?.kind??'video',stillPos,frame);
  const stillsDone=picturesComplete(stills);
  const trackSeedIds=idsToTrack(selectedIds,selected?.id??null,frameAnns.map(item=>item.id));
  const stillRows=useMemo(()=>stillFrameRows(stills,stillFrames),[stills,stillFrames]);
  const filteredFrames=useMemo(()=>filterFrames(frames,frameStatus,frameLabelIds),[frames,frameStatus,frameLabelIds]);
  const filteredStills=useMemo(()=>filterFrames(stillRows,frameStatus,frameLabelIds),[stillRows,frameStatus,frameLabelIds]);
  const filtersOn=frameStatus!=='all'||frameLabelIds.length>0;
  const filterScope=media?.kind==='image'?'stills':media?.id??null;
  editorRef.current={labelId,selected,points,box};
  annIdsRef.current=frameAnns.map(item=>item.id);

  const takeSnap=()=>{
    const ids=new Set(annIdsRef.current);
    if(editorRef.current.selected)ids.add(editorRef.current.selected.id);
    return {mask:canvas.current?.exportPng()??null,annIds:[...ids],...editorRef.current};
  };
  const pushHistory=()=>{
    historyPast.current=[...historyPast.current.slice(-24),takeSnap()];
    historyFuture.current=[];
    setCanUndo(true);setCanRedo(false);
  };
  const applySnap=async(snap:ReturnType<typeof takeSnap>)=>{
    await canvas.current?.loadMaskDataUrl(snap.mask);
    setLabelId(snap.labelId);setSelected(snap.selected);setPoints(snap.points);setBox(snap.box);
    setDirty(true);setSaveState('Unsaved changes');
  };
  const dropNewAnnotations=async(beforeIds:number[], afterIds:number[])=>{
    const drop=idsToDropOnUndo(beforeIds,afterIds);
    if(!drop.length)return [];
    setOverlays(items=>items.filter(item=>!drop.includes(item.id)));
    setFrameAnns(items=>items.filter(item=>!drop.includes(item.id)));
    setSelectedIds(ids=>ids.filter(id=>!drop.includes(id)));
    setFinishedIds(ids=>ids.filter(id=>!drop.includes(id)));
    annIdsRef.current=annIdsRef.current.filter(id=>!drop.includes(id));
    for(const id of drop)await api.deleteAnnotation(id).catch(()=>{});
    historyPast.current=historyPast.current.map(snap=>({
      ...snap,
      selected:snap.selected&&drop.includes(snap.selected.id)?null:snap.selected,
      annIds:snap.annIds.filter(id=>!drop.includes(id)),
    }));
    historyFuture.current=historyFuture.current.map(snap=>({
      ...snap,
      selected:snap.selected&&drop.includes(snap.selected.id)?null:snap.selected,
      annIds:snap.annIds.filter(id=>!drop.includes(id)),
    }));
    if(media)await refreshWorkspace(media.id,frame);
    return drop;
  };
  const undoEdit=async()=>{
    if(!historyPast.current.length)return;
    promptGen.current+=1;
    const current=takeSnap();
    historyFuture.current=[...historyFuture.current,current];
    const prev=historyPast.current.pop()!;
    setCanUndo(historyPast.current.length>0);setCanRedo(true);
    await applySnap(prev);
    await dropNewAnnotations(prev.annIds,current.annIds);
  };
  const redoEdit=async()=>{
    if(!historyFuture.current.length)return;
    promptGen.current+=1;
    const current=takeSnap();
    historyPast.current=[...historyPast.current,current];
    const next=historyFuture.current.pop()!;
    setCanUndo(true);setCanRedo(historyFuture.current.length>0);
    await applySnap(next);
    await dropNewAnnotations(next.annIds,current.annIds);
  };
  const resetHistory=()=>{historyPast.current=[];historyFuture.current=[];setCanUndo(false);setCanRedo(false)};

  const refreshProjects=async()=>setProjects(await api.listProjects());

  useEffect(()=>{
    let stop=false;
    let id=0;
    const load=async()=>{
      try{
        const list=await api.listProjects();
        if(stop)return true;
        setProjects(list);setBoot('ready');setError(null);return true;
      }catch(e){
        if(stop)return false;
        setBoot('waiting');setError(e instanceof Error?e.message:String(e));return false;
      }
    };
    const tick=async()=>{if(await load())window.clearInterval(id)};
    tick();
    id=window.setInterval(tick,2000);
    return()=>{stop=true;window.clearInterval(id)};
  },[]);

  useEffect(()=>{
    localStorage.setItem('autosave',String(autoSave));
    localStorage.setItem('autosaveSec',String(autoSaveSec));
  },[autoSave,autoSaveSec]);

  const refreshProject=async(ref:string|number)=>{
    const next=await api.getProject(ref);
    setProject(next);
    if(labelId===null||!next.labels.some(x=>x.id===labelId))setLabelId(next.labels[0]?.id??null);
    return next;
  };

  useEffect(()=>{
    if(boot!=='ready')return;
    if(!projectSlug){
      setProject(null);
      setMedia(null);
      return;
    }
    if(project&&(project.slug===projectSlug||String(project.id)===projectSlug))return;
    let stop=false;
    setBusy(true);
    api.getProject(projectSlug).then(next=>{
      if(stop)return;
      setProject(next);
      setLabelId(current=>current===null||!next.labels.some(x=>x.id===current)?next.labels[0]?.id??null:current);
    }).catch(e=>{
      setError(e instanceof Error?e.message:String(e));
      navigate('/projects',{replace:true});
    }).finally(()=>setBusy(false));
    return()=>{stop=true};
  },[boot,projectSlug,navigate,project?.id,project?.slug]);

  useEffect(()=>{
    if(!project||!projectSlug)return;
    if(project.slug&&project.slug!==projectSlug){
      navigate(projectHref(project,mediaId!=null?`/media/${mediaId}`:''),{replace:true});
    }
  },[project,projectSlug,mediaId,navigate]);

  const closePromptSession=async()=>{
    const id=promptIdRef.current;
    if(!id)return;
    promptIdRef.current=null;
    setPromptId(null);
    await api.closePrompt(id).catch(()=>{});
  };

  const refreshStillFrames=async(items:typeof stills)=>{
    const entries=await Promise.all(items.map(async item=>{
      const list=await api.getFrames(item.id,0,Math.max(1,item.frame_count||1));
      return [item.id,list[0]??{frame:0,annotation_count:item.annotation_count??0,excluded:false,labels:[]}] as const;
    }));
    setStillFrames(Object.fromEntries(entries));
    return entries;
  };

  const refreshWorkspace=async(mid:number,_current=frame)=>{
    const album=stills.some(item=>item.id===mid);
    if(album){
      const entries=await refreshStillFrames(stills);
      const current=entries.find(([id])=>id===mid);
      if(current)setFrames([current[1]]);
      return;
    }
    const count=media?.id===mid?media.frame_count:20000;
    setFrames(await api.getFrames(mid,0,Math.max(1,count)));
  };

  const resetEditor=()=>{
    setSelected(null);
    setSelectedIds([]);
    setPoints([]);
    setBox(null);
    canvas.current?.clearMask();
    setDirty(false);
    resetHistory();
  };

  const openMedia=async(item:Media,startFrame=0)=>{
    await closePromptSession();
    const safe=Math.max(0,Math.min(startFrame,Math.max(0,item.frame_count-1)));
    setMedia(item);
    setFrame(safe);
    if(item.kind==='image'){
      const album=stillsOf(project?.media??[]);
      const pos=Math.max(0,stillIndex(album,item.id));
      setTrackFrom(pos);
      setTarget(Math.max(0,album.length-1));
    }else{
      setTrackFrom(safe);
      setTarget(Math.max(0,item.frame_count-1));
    }
    resetEditor();
    setTimeout(()=>refreshWorkspace(item.id,safe).catch(e=>setError(String(e))),0);
  };

  useEffect(()=>{
    if(!project)return;
    if(mediaId==null){
      setMedia(null);
      return;
    }
    const found=project.media.find(item=>item.id===mediaId);
    if(!found){
      setError('Media not found');
      navigate(projectHref(project),{replace:true});
      return;
    }
    if(!mediaReady(found)){
      setExtractQueue(queue=>queue.some(item=>item.id===found.id)?queue:[found,...queue]);
      navigate(projectHref(project),{replace:true});
      return;
    }
    const startFrame=Number(new URLSearchParams(location.search).get('frame')||0);
    if(media?.id!==found.id)void openMedia(found,Number.isFinite(startFrame)?startFrame:0);
  },[project,mediaId,media?.id,navigate,location.search]);

  const gotoFrame=async(nextFrame:number)=>{
    if(!media)return;
    await closePromptSession();
    const n=Math.max(0,Math.min(nextFrame,Math.max(0,media.frame_count-1)));
    setFrame(n);
    setTrackFrom(n);
    resetEditor();
  };

  const gotoStillAt=(index:number)=>{
    if(!project||!media||media.kind!=='image')return;
    const next=stills[Math.max(0,Math.min(index,Math.max(0,stills.length-1)))];
    if(next&&next.id!==media.id)navigate(projectHref(project,`/media/${next.id}`));
  };

  const gotoStill=(delta:number)=>{
    if(!project||!media||media.kind!=='image')return;
    const next=stepStill(stills,media.id,delta);
    if(next&&next.id!==media.id)navigate(projectHref(project,`/media/${next.id}`));
  };

  const ensurePrompt=async(annotationId?:number|null)=>{
    if(!media)throw new Error('No media');
    if(promptIdRef.current)return promptIdRef.current;
    const aid=annotationId===undefined?selected?.id??null:annotationId;
    const session=await api.createPrompt(media.id,frame,aid);
    promptIdRef.current=session.session_id;
    setPromptId(session.session_id);
    return session.session_id;
  };

  const runPrompt=async(nextPoints:PromptPoint[],nextBox:BoxPrompt|null,replaceId?:number|null,maskDataUrl?:string|null,merge=false)=>{
    const gen=promptGen.current+1;
    promptGen.current=gen;
    pushHistory();
    setPromptBusy(true);setError(null);
    try{
      const sid=await ensurePrompt(replaceId===undefined?undefined:replaceId);
      const blob=await api.predictPrompt(sid,nextPoints,nextBox,maskUrlForPrompt(nextPoints,nextBox,maskDataUrl,merge));
      if(gen!==promptGen.current)return;
      if(merge)await canvas.current?.mergeMaskBlob(blob);
      else await canvas.current?.loadMaskBlob(blob);
      setDirty(true);setSaveState('Unsaved changes');setStatus('SAM2 mask updated');
      if(closeSessionAfterPredict())await closePromptSession();
      if(!keepPromptsAfterPredict()){setPoints([]);setBox(null)}
      setTool(toolAfterGeneratedMask(tool));
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
      if(maskDataUrl){setDirty(true);setSaveState('Unsaved changes')}
    }
    finally{setPromptBusy(false)}
  };

  const addPoint=async(point:PromptPoint)=>{const next=[...points,point];setPoints(next);await runPrompt(next,box,undefined,canvas.current?.exportMaskDataUrl())};
  const setPromptBox=async(nextBox:BoxPrompt)=>{
    const hasCurrent=Boolean(selected)||Boolean(canvas.current?.exportMaskDataUrl());
    const accepted=selected!=null&&finishedIds.includes(selected.id);
    if(boxStartsNewInstance(hasCurrent,accepted)){
      if(dirty)await saveCurrent(true);
      await closePromptSession();
      setSelected(null);
      setPoints([]);
      canvas.current?.clearMask();
      setDirty(false);
      setBox(nextBox);
      await runPrompt([],nextBox,null);
      return;
    }
    setBox(nextBox);
    await runPrompt(points,nextBox,null,null,hasCurrent);
  };

  const finishBrushDetect=async()=>{
    if(brushStrokeUsesDetection(Boolean(selected))!=='detect')return;
    const data=canvas.current?.exportMaskDataUrl();
    if(!data)return;
    const box=brushBoundsToBox(canvas.current?.exportBounds()??null);
    setPromptBusy(true);
    await closePromptSession();
    await runPrompt([],box,null,data);
  };

  const selectAnnotation=async(ann:Annotation,nextTool:ToolMode='select')=>{
    if(!media)return;
    if(ann.frame!==frame)await gotoFrame(ann.frame);
    if(selected?.id!==ann.id)pushHistory();
    await closePromptSession();
    setSelected(ann);setLabelId(ann.label_id);setPoints([]);setBox(null);
    const blob=await api.getMaskBlob(ann.id);
    await canvas.current?.loadMaskBlob(blob);
    setTool(nextTool);setDirty(false);setSaveState('Saved');
  };

  const clearEditor=async()=>{
    if(dirty)await saveCurrent(true);
    await closePromptSession();
    setSelected(null);
    setPoints([]);
    setBox(null);
    canvas.current?.clearMask();
    setDirty(false);
  };

  const unfocusMask=async()=>{
    await clearEditor();
    setSelectedIds([]);
    setTool('select');
  };

  const finishMask=async()=>{
    let id=selected?.id??null;
    if(dirty){
      const ann=await saveCurrent(true);
      id=acceptedMaskId(id,ann?.id);
    }
    if(id==null){
      await unfocusMask();
      return;
    }
    const done=!finishedIds.includes(id);
    setFinishedIds(done?[...finishedIds,id]:finishedIds.filter(item=>item!==id));
    if(done)setTool('select');
  };

  const pickMask=async(id:number,additive:boolean)=>{
    const ann=frameAnns.find(item=>item.id===id);
    if(!ann)return;
    if(additive){
      const next=toggleSelection(selectedIds,id);
      setSelectedIds(next);
      if(next.includes(id))await selectAnnotation(ann,'select');
      else if(next.length===1){
        const other=frameAnns.find(item=>item.id===next[0]);
        if(other)await selectAnnotation(other,'select');
        else await clearEditor();
      }else await clearEditor();
      return;
    }
    setSelectedIds([id]);
    await selectAnnotation(ann,'select');
  };

  const pickMasks=async(ids:number[],additive:boolean)=>{
    const next=mergeSelection(selectedIds,ids,additive);
    setSelectedIds(next);
    if(next.length===1){
      const ann=frameAnns.find(item=>item.id===next[0]);
      if(ann)await selectAnnotation(ann,'select');
      return;
    }
    await clearEditor();
  };

  const newMask=async()=>{
    pushHistory();
    await closePromptSession();
    setSelected(null);
    setSelectedIds([]);
    setPoints([]);
    setBox(null);
    canvas.current?.clearMask();
    setDirty(false);
    setTool('positive');
    setSaveState('New mask');
  };

  const changeClass=async(id:number)=>{
    if(id===labelId)return;
    pushHistory();
    setLabelId(id);
    setDirty(true);
    setSaveState('Unsaved changes');
  };

  const saveCurrent=async(silent=false,replaceId?:number|null)=>{
    if(saveInFlight.current)return saveInFlight.current;
    const run=(async()=>{
      if(!media||!labelId)return null;
      const data=canvas.current?.exportMaskDataUrl();
      if(!data){if(!silent)setError('No mask to save');return null}
      setSaveState('Saving…');
      try{
        const ann=await api.saveMask({mediaId:media.id,frame,labelId,maskDataUrl:data,replaceId:replaceId===undefined?selected?.id:replaceId,source:'manual'});
        setSelected(ann);setSelectedIds([ann.id]);setDirty(false);setSaveState(`Saved ${new Date().toLocaleTimeString()}`);
        annIdsRef.current=[...new Set([...annIdsRef.current,ann.id])];
        await refreshWorkspace(media.id,frame);
        if(!silent)setStatus('Annotation saved');
        return ann;
      }catch(e){setSaveState('Save failed');if(!silent)setError(String(e));return null}
    })();
    saveInFlight.current=run;
    try{return await run}
    finally{saveInFlight.current=null}
  };

  useEffect(()=>{
    if(!autoSave||view!=='annotate')return;
    const ms=Math.max(1,autoSaveSec)*1000;
    const id=window.setInterval(()=>{if(dirty&&!promptBusy&&!busy)saveCurrent(true)},ms);
    return()=>clearInterval(id);
  },[autoSave,autoSaveSec,dirty,promptBusy,busy,view,media,labelId,selected,frame]);

  useEffect(()=>{
    if(!media){setOverlays([]);setFrameAnns([]);return}
    let stop=false;
    const urls:string[]=[];
    api.listAnnotations(media.id,frame).then(async anns=>{
      if(!stop)setFrameAnns(anns);
      const items:MaskOverlay[]=[];
      for(const ann of anns){
        const blob=await api.getMaskBlob(ann.id);
        const url=URL.createObjectURL(blob);
        urls.push(url);
        items.push({id:ann.id,color:ann.label_color,url,name:ann.label_name});
      }
      if(!stop)setOverlays(items);
    }).catch(()=>{if(!stop)setOverlays([])});
    return()=>{stop=true;urls.forEach(url=>URL.revokeObjectURL(url))};
  },[media?.id,frame,frames]);

  useEffect(()=>{setSpent(media?.annotation_seconds??0)},[media?.id]);
  useEffect(()=>{setFrameStatus('all');setFrameLabelIds([])},[project?.id,filterScope]);

  useEffect(()=>{
    if(view!=='annotate'||!media)return;
    let lastAct=Date.now();
    let lastTick=Date.now();
    let pending=0;
    const bump=()=>{lastAct=Date.now()};
    window.addEventListener('pointerdown',bump);
    window.addEventListener('keydown',bump);
    const id=window.setInterval(()=>{
      const now=Date.now();
      const active=!document.hidden&&now-lastAct<60000;
      if(active){
        const delta=(now-lastTick)/1000;
        pending+=delta;
        setSpent(value=>value+delta);
      }
      lastTick=now;
      if(pending>=5){
        const add=Math.min(30,Math.round(pending));
        pending-=add;
        api.addAnnotationTime(media.id,add).then(result=>{
          setSpent(result.annotation_seconds+pending);
          setMedia(current=>current&&current.id===media.id?{...current,annotation_seconds:result.annotation_seconds}:current);
          setProject(current=>current?{
            ...current,
            annotation_seconds:result.project_annotation_seconds,
            media:current.media.map(item=>item.id===media.id?{...item,annotation_seconds:result.annotation_seconds}:item),
          }:current);
        }).catch(()=>{});
      }
    },1000);
    return()=>{
      window.clearInterval(id);
      window.removeEventListener('pointerdown',bump);
      window.removeEventListener('keydown',bump);
      if(pending>=1)api.addAnnotationTime(media.id,Math.min(30,Math.round(pending))).catch(()=>{});
    };
  },[view,media?.id]);

  const startTrack=async()=>{
    if(!media){setError('Save or select a seed annotation first');return}
    const from=Math.max(0,Math.min(trackFrom,lastTrack));
    const to=Math.max(0,Math.min(target,lastTrack));
    if(from===to){setError(isStill?'To picture must differ from From picture':'To frame must differ from From frame');return}
    const seedMediaId=trackSeedMediaId(media.kind,stills,from,media.id);
    const seedFrame=isStill?0:from;
    const chosen=idsToTrack(selectedIds,selected?.id??null,[]);
    let frameIds=frameAnns.map(item=>item.id);
    if(!chosen.length&&from!==trackPos){
      try{frameIds=(await api.listAnnotations(seedMediaId,seedFrame)).map(item=>item.id)}
      catch(e){setError(String(e));return}
    }
    const seedIds=idsToTrack(selectedIds,selected?.id??null,frameIds);
    if(!seedIds.length){setError('Save or select a seed annotation first');return}
    const seedAnns=seedIds.map(id=>frameAnns.find(item=>item.id===id)||(selected?.id===id?selected:null)).filter((item):item is Annotation=>item!=null);
    if(seedAnns.length&&!trackSeedsMatchFrom(media.kind,seedAnns,from,seedMediaId)){setError(isStill?'From picture must match the saved seed mask':'From frame must match the saved seed mask');return}
    try{
      const job=await api.startTracking({mediaId:seedMediaId,annotationIds:seedIds,startFrame:from,endFrame:to,frameStep:trackStep,replace:replaceAuto});
      setTrackJob(job);
      const n=seedIds.length;
      const unit=isStill?'picture':'frame';
      setStatus(n>1?`Tracking ${n} masks from ${displayIndex(from)} to ${displayIndex(to)}, saving every ${trackStep} ${unit}${trackStep===1?'':'s'}…`:`Tracking from ${displayIndex(from)} to ${displayIndex(to)}, saving every ${trackStep} ${unit}${trackStep===1?'':'s'}…`);
    }catch(e){setError(String(e))}
  };

  useEffect(()=>{
    if(!trackJob||['completed','failed','cancelled'].includes(trackJob.status))return;
    const id=window.setInterval(async()=>{
      try{
        const job=await api.trackingStatus(trackJob.id);
        setTrackJob(job);
        if(['completed','failed','cancelled'].includes(job.status)){
          window.clearInterval(id);
          if(media)await refreshWorkspace(media.id,frame);
          setStatus(job.status==='completed'?`Tracking complete · ${job.created_annotations.length} masks saved`:job.status==='cancelled'?`Stopped · ${job.created_annotations.length} masks saved`:job.status);
        }
      }catch(e){setError(String(e))}
    },700);
    return()=>clearInterval(id);
  },[trackJob?.id,trackJob?.status,media?.id,frame]);

  const submitNewProject=async(name:string,description:string)=>{
    setBusy(true);setError(null);
    try{
      const created=await api.createProject(name,description);
      await refreshProjects();
      setShowProjectForm(false);
      setProject(created);
      navigate(projectHref(created));
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };

  const upload=async(files:FileList|null)=>{
    if(!project||!files?.length)return;
    setBusy(true);
    try{
      const uploaded=await api.uploadMedia(project.id,Array.from(files));
      await refreshProject(project.id);
      const pending=uploaded.filter(item=>item.kind==='video'&&!mediaReady(item)&&!item.reused);
      if(pending.length)setExtractQueue(queue=>[...queue,...pending]);
      const reused=uploaded.some(item=>item.reused);
      if(pending.length&&!reused)setStatus('Choose how many frames to extract per second');
      else if(pending.length)setStatus(`${reusedMediaStatus(uploaded)} Choose extract rate for new videos.`);
      else setStatus(reusedMediaStatus(uploaded));
      const notice=reusedMediaNotice(uploaded);
      if(notice)setReusedNotice(notice);
    }catch(e){setError(String(e))}
    finally{setBusy(false)}
  };

  const runExtract=async(framesPerSecond:number)=>{
    const current=extractQueue[0];
    if(!current||!project)return;
    setBusy(true);setError(null);
    try{
      await api.extractMedia(current.id,framesPerSecond);
      await refreshProject(project.id);
      setExtractQueue(queue=>queue.slice(1));
      setStatus(`Extracted frames from ${current.name}`);
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };

  const newLabel=async()=>{
    if(!project)return;
    const name=window.prompt('New defect label');
    if(!name)return;
    const color=uniqueColor(project.labels.map(label=>label.color));
    await api.addLabel(project.id,name,color);
    await refreshProject(project.id);
  };

  const changeLabelColor=async(lid:number,color:string)=>{
    if(!project)return;
    const others=project.labels.filter(label=>label.id!==lid).map(label=>label.color);
    try{
      await api.updateLabel(project.id,lid,{color:ensureUniqueColor(color,others)});
      await refreshProject(project.id);
    }catch(e){setError(String(e))}
  };

  const requestDeleteAnnotations=(ids:number[])=>{
    const unique=[...new Set(ids)];
    if(!unique.length)return;
    const n=unique.length;
    setPendingDelete({
      kind:'annotations',
      ids:unique,
      title:n===1?'Delete annotation':`Delete ${n} annotations`,
      hint:n===1?'This mask will be removed from the current frame.':`${n} selected masks will be removed from this frame.`,
    });
  };

  const requestDeleteProject=(item:{id:number;slug?:string|null;name:string})=>{
    setDeleteBusyLabel('Deleting…');
    setPendingDelete({
      kind:'project',
      ref:item.slug||item.id,
      name:item.name,
    });
  };

  const importBackup=async(file:File|null)=>{
    if(!file)return;
    setBusy(true);setError(null);
    try{
      const restored=await api.importProjectBackup(file);
      await refreshProjects();
      setProject(restored);
      navigate(projectHref(restored));
      setStatus(`Recovered ${restored.name}`);
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setBusy(false)}
  };

  const confirmPendingDelete=async(downloadBackup=false)=>{
    if(!pendingDelete||deleteBusy)return;
    setDeleteBusy(true);
    try{
      if(pendingDelete.kind==='project'){
        if(downloadBackup){
          setDeleteBusyLabel('Saving backup…');
          await api.downloadProjectBackup(pendingDelete.ref,`${pendingDelete.name}-backup.zip`);
        }
        setDeleteBusyLabel('Deleting…');
        await api.deleteProject(pendingDelete.ref);
        setPendingDelete(null);
        setProject(null);
        await refreshProjects();
        navigate('/projects');
        return;
      }
      if(pendingDelete.kind==='stills'){
        if(!project)return;
        const count=pendingDelete.count;
        await api.deleteProjectImages(project.id);
        setPendingDelete(null);
        await refreshProject(project.slug||project.id);
        setStatus(count===1?'Still deleted':`${count} stills deleted`);
        return;
      }
      const ids=pendingDelete.ids;
      for(const id of ids)await api.deleteAnnotation(id);
      const hitSelected=selected!=null&&ids.includes(selected.id);
      const nextIds=selectedIds.filter(id=>!ids.includes(id));
      setSelectedIds(nextIds);
      setFinishedIds(current=>current.filter(id=>!ids.includes(id)));
      if(hitSelected||nextIds.length===0){
        await closePromptSession();
        setSelected(null);
        setPoints([]);
        setBox(null);
        canvas.current?.clearMask();
        setDirty(false);
      }else if(nextIds.length===1){
        const remaining=frameAnns.find(item=>item.id===nextIds[0]);
        if(remaining)await selectAnnotation(remaining,'select');
      }
      if(media)await refreshWorkspace(media.id,frame);
      setPendingDelete(null);
      setStatus(ids.length===1?'Annotation deleted':`${ids.length} annotations deleted`);
    }catch(e){setError(e instanceof Error?e.message:String(e))}
    finally{setDeleteBusy(false)}
  };

  const deleteAnnotationById=(id:number)=>{requestDeleteAnnotations([id])};

  const deleteCurrentAnnotation=()=>{
    requestDeleteAnnotations(idsToDelete(selectedIds,selected?.id??null));
  };

  const excludeListedFrame=async(targetMediaId:number,frameNum:number,alsoDelete=false)=>{
    await api.excludeFrame(targetMediaId,frameNum,true,alsoDelete);
    if(alsoDelete&&targetMediaId===media?.id&&frameNum===frame)await newMask();
    await refreshWorkspace(targetMediaId,frameNum);
    setStatus(alsoDelete?'Frame excluded and annotations deleted':'Frame excluded from dataset/export');
  };

  const restoreListedFrame=async(targetMediaId:number,frameNum:number)=>{
    await api.excludeFrame(targetMediaId,frameNum,false,false);
    await refreshWorkspace(targetMediaId,frameNum);
  };

  const editFrameAnnotation=async(frameNum:number,annotationId:number)=>{
    if(!media)return;
    if(frameNum!==frame)await gotoFrame(frameNum);
    const anns=await api.listAnnotations(media.id,frameNum);
    const ann=anns.find(item=>item.id===annotationId);
    if(!ann)return;
    await closePromptSession();
    setSelected(ann);setLabelId(ann.label_id);setPoints([]);setBox(null);setSelectedIds([ann.id]);
    const blob=await api.getMaskBlob(ann.id);
    await canvas.current?.loadMaskBlob(blob);
    setTool('brush');setDirty(false);setSaveState('Saved');
  };

  const editListedAnnotation=async(targetMediaId:number,frameNum:number,annotationId:number)=>{
    if(!project)return;
    if(media?.id!==targetMediaId){
      pendingStillEdit.current=annotationId;
      navigate(projectHref(project,`/media/${targetMediaId}`));
      return;
    }
    await editFrameAnnotation(frameNum,annotationId);
  };

  useEffect(()=>{
    if(!media)return;
    const pending=pendingStillEdit.current;
    if(pending==null)return;
    pendingStillEdit.current=null;
    void editFrameAnnotation(0,pending);
  },[media?.id]);

  const stopTrack=async()=>{
    if(!trackJob)return;
    await api.cancelTracking(trackJob.id);
    setStatus('Stopping tracker and saving masks…');
  };

  useEffect(()=>{
    if(view!=='annotate'||!media)return;
    const onKey=(e:KeyboardEvent)=>{
      const el=e.target as HTMLElement|null;
      if(el&&(el.tagName==='INPUT'||el.tagName==='SELECT'||el.tagName==='TEXTAREA'||el.isContentEditable||el.closest('.frame-filters')))return;
      if(pendingDelete)return;
      if(e.key==='ArrowRight'){e.preventDefault();if(media.kind==='image')gotoStill(e.shiftKey?10:1);else void gotoFrame(frame+(e.shiftKey?10:1));return}
      if(e.key==='ArrowLeft'){e.preventDefault();if(media.kind==='image')gotoStill(e.shiftKey?-10:-1);else void gotoFrame(frame-(e.shiftKey?10:1));return}
      if(e.key==='z'&&(e.ctrlKey||e.metaKey)){e.preventDefault();if(e.shiftKey)redoEdit();else undoEdit();return}
      if((e.key==='y'||e.key==='Y')&&(e.ctrlKey||e.metaKey)){e.preventDefault();redoEdit();return}
      if(e.key==='v'||e.key==='V'){setTool('select');return}
      if(e.key==='1'||e.key==='p'||e.key==='P'||e.key==='+'){setTool('positive');return}
      if(e.key==='2'||e.key==='-'||e.key==='_'){setTool('negative');return}
      if(e.key==='b'||e.key==='B'){setTool('box');return}
      if(e.key==='w'||e.key==='W'){setTool('brush');return}
      if(e.key==='e'||e.key==='E'){setTool('erase');return}
      if(e.key==='h'||e.key==='H'){setTool('pan');return}
      if(e.key==='['){setBrushSize(size=>Math.max(1,size-2));return}
      if(e.key===']'){setBrushSize(size=>Math.min(80,size+2));return}
      if(e.key==='s'||e.key==='S'){e.preventDefault();saveCurrent(false);return}
      if(e.key==='m'||e.key==='M'){newMask();return}
      if(e.key==='x'||e.key==='X'){void excludeListedFrame(media.id,frame,e.shiftKey);return}
      if(e.key==='Delete'||e.key==='Backspace'){
        const ids=idsToDelete(selectedIds,selected?.id??null);
        if(ids.length){e.preventDefault();deleteCurrentAnnotation()}
        return;
      }
      if(e.key==='Escape'){e.preventDefault();void unfocusMask();return}
    };
    window.addEventListener('keydown',onKey);
    return()=>window.removeEventListener('keydown',onKey);
  },[view,media,frame,selected,selectedIds,pendingDelete,lastFrame,dirty,stills,project]);

  const requestAnnotate=async(item:Media)=>{
    if(!project)return;
    if(!mediaReady(item)){
      setExtractQueue(queue=>queue.some(x=>x.id===item.id)?queue:[item,...queue]);
      return;
    }
    navigate(projectHref(project,`/media/${item.id}`));
  };

  const setVideoComplete=async(item:Media,complete:boolean)=>{
    if(!project)return;
    setProject(current=>current?{...current,media:current.media.map(row=>row.id===item.id?{...row,annotation_complete:complete}:row)}:current);
    try{
      await api.setMediaComplete(item.id,complete);
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
      await refreshProject(project.slug||project.id);
    }
  };

  const setPicturesComplete=async(complete:boolean)=>{
    if(!project)return;
    setProject(current=>current?{...current,media:current.media.map(row=>row.kind==='image'?{...row,annotation_complete:complete}:row)}:current);
    try{
      await api.setProjectImagesComplete(project.id,complete);
    }catch(e){
      setError(e instanceof Error?e.message:String(e));
      await refreshProject(project.slug||project.id);
    }
  };

  const extractCurrent=extractQueue[0]??null;

  const dialogs=<>
    {showProjectForm&&<NameDialog title="New project" hint="Give this inspection a unique name. It becomes the project URL." nameLabel="Project name" namePlaceholder="e.g. Riverside trunk – 12 Sep 2026" extraLabel="Description (optional)" extraPlaceholder="Inspection location, crew, or notes" submitLabel="Create project" busy={busy} showSlug onCancel={()=>setShowProjectForm(false)} onSubmit={submitNewProject}/>}
    {extractCurrent&&!reusedNotice&&<ExtractDialog media={extractCurrent} remaining={extractQueue.length} busy={busy} onCancel={()=>setExtractQueue(queue=>queue.slice(1))} onExtract={runExtract}/>}
    {reusedNotice&&<NoticeDialog title={reusedNotice.title} hint={reusedNotice.hint} onClose={()=>setReusedNotice(null)}/>}
    {showExport&&<ExportDialog projects={projects} defaultProjectId={project?.id??null} onClose={()=>setShowExport(false)}/>}
    {pendingDelete?.kind==='annotations'&&<ConfirmDialog title={pendingDelete.title} hint={pendingDelete.hint} busy={deleteBusy} onCancel={()=>{if(!deleteBusy)setPendingDelete(null)}} onConfirm={()=>{void confirmPendingDelete()}}/>}
    {pendingDelete?.kind==='stills'&&<ConfirmDialog title={pendingDelete.count===1?'Delete still?':`Delete ${pendingDelete.count} stills?`} hint="Annotations on those files will be removed. Videos are kept." busy={deleteBusy} onCancel={()=>{if(!deleteBusy)setPendingDelete(null)}} onConfirm={()=>{void confirmPendingDelete()}}/>}
    {pendingDelete?.kind==='project'&&<DeleteProjectDialog name={pendingDelete.name} busy={deleteBusy} busyLabel={deleteBusyLabel} onCancel={()=>{if(!deleteBusy)setPendingDelete(null)}} onConfirm={downloadBackup=>{void confirmPendingDelete(downloadBackup)}}/>}
    {error&&boot==='ready'&&<Toast text={error} close={()=>setError(null)}/>}
    <Outlet/>
  </>;

  if(view==='dashboard')return <div className="page-shell product-shell">
    <AppNav onExport={()=>setShowExport(true)} exportDisabled={boot!=='ready'||!projects.length}/>
    <DashboardPage/>
    {dialogs}
  </div>;

  if(view==='settings')return <div className="page-shell product-shell">
    <AppNav onExport={()=>setShowExport(true)} exportDisabled={boot!=='ready'||!projects.length}/>
    <SettingsPage/>
    {dialogs}
  </div>;

  if(view==='projects')return <div className="page-shell product-shell">
    <AppNav onExport={()=>setShowExport(true)} exportDisabled={boot!=='ready'||!projects.length}/>
    <ProjectsPage projects={projects} boot={boot} busy={busy} onCreate={()=>setShowProjectForm(true)} onImport={importBackup} onOpen={item=>navigate(projectHref(item))} onDelete={requestDeleteProject}/>
    {dialogs}
  </div>;

  if(view==='project'&&project)return <div className="page-shell product-shell">
    <AppNav onExport={()=>setShowExport(true)} trailing={<label className="primary upload-button">Upload media<input type="file" multiple accept="video/*,image/*" onChange={e=>upload(e.target.files)}/></label>}/>
    <ProjectWorkspace
      project={project}
      onUpload={upload}
      onAnnotate={item=>{void requestAnnotate(item)}}
      onExtract={item=>setExtractQueue(queue=>queue.some(x=>x.id===item.id)?queue:[item,...queue])}
      onDeleteMedia={async item=>{
        if(confirm(`Delete ${item.name} and all its annotations?`)){
          await api.deleteMedia(item.id);
          await refreshProject(project.slug||project.id);
        }
      }}
      onDeletePictures={()=>setPendingDelete({kind:'stills',count:stillsOf(project.media).length})}
      onSetVideoComplete={(item,complete)=>{void setVideoComplete(item,complete)}}
      onSetPicturesComplete={complete=>{void setPicturesComplete(complete)}}
      onAddLabel={newLabel}
      onLabelColor={(id,color)=>void changeLabelColor(id,color)}
      onDeleteLabel={async label=>{
        if(confirm(`Delete ${label.name}?`)){
          try{await api.deleteLabel(project.id,label.id);await refreshProject(project.slug||project.id)}
          catch(e){setError(String(e))}
        }
      }}
      onDeleteProject={()=>requestDeleteProject(project)}
    />
    {dialogs}
  </div>;

  if(view==='annotate'&&project&&media)return <div className="annotator">
    <header className="annotator-header">
      <div className="header-left">
        <button className="icon-btn" onClick={()=>{navigate(projectHref(project));refreshProject(project.slug||project.id)}}>←</button>
        <div className="media-title">
          <strong>{media.name}</strong>
          <span>{isStill?`${project.name} · Pictures · ${stillPos+1} of ${stills.length}`:`${project.name} · ${media.kind} · ${media.frame_count} frames`}</span>
        </div>
      </div>
      <div className="header-actions">
        {isStill&&<DoneCheck checked={stillsDone} onChange={value=>{void setPicturesComplete(value)}}/>}
        <TimeChip seconds={spent} live/>
        <button className="button" onClick={()=>setShowExport(true)}>Export</button>
        <div className="save-status"><span className={dirty?'dot dirty':'dot'}/>{saveState}</div>
      </div>
    </header>
    <div className="annotation-layout">
      <aside className="left-rail">
        <div className="rail-section frame-rail">
          <div className="frame-rail-head">
            <div className="rail-heading">
              <strong>{isStill?'Pictures':'Frames'}</strong>
              <span className="frame-count-stat">{isStill
                ? <><b>{filtersOn?filteredStills.length:annotatedFrameCount(stillRows)}</b> / {stillRows.length}</>
                : <><b>{filtersOn?filteredFrames.length:annotatedFrameCount(frames)}</b> / {frames.length}</>}</span>
            </div>
            <FrameFilters
              status={frameStatus}
              labelIds={frameLabelIds}
              labels={project.labels}
              onStatus={setFrameStatus}
              onLabels={setFrameLabelIds}
            />
          </div>
          <div className="frame-list">
            {isStill
              ? <>
            {filteredStills.length===0&&<div className="frame-empty">{filtersOn?'No pictures match these filters':'No pictures yet'}</div>}
            {filteredStills.map(row=>(
              <FrameThumb
                key={row.mediaId}
                mediaId={row.mediaId}
                item={row}
                indexLabel={row.index}
                active={row.mediaId===media.id}
                onOpen={()=>navigate(projectHref(project,`/media/${row.mediaId}`))}
                onExclude={alsoDelete=>{void excludeListedFrame(row.mediaId,row.frame,alsoDelete)}}
                onRestore={()=>{void restoreListedFrame(row.mediaId,row.frame)}}
                onEdit={id=>{void editListedAnnotation(row.mediaId,row.frame,id)}}
                onDeleteAnn={deleteAnnotationById}
              />
            ))}
              </>
              : <>
            {filteredFrames.length===0&&<div className="frame-empty">{filtersOn?'No frames match these filters':'No frames yet'}</div>}
            {filteredFrames.map(item=>(
              <FrameThumb
                key={item.frame}
                mediaId={media.id}
                item={item}
                active={item.frame===frame}
                onOpen={()=>gotoFrame(item.frame)}
                onExclude={alsoDelete=>{void excludeListedFrame(media.id,item.frame,alsoDelete)}}
                onRestore={()=>{void restoreListedFrame(media.id,item.frame)}}
                onEdit={id=>{void editListedAnnotation(media.id,item.frame,id)}}
                onDeleteAnn={deleteAnnotationById}
              />
            ))}
              </>}
          </div>
        </div>
      </aside>
      <main className="editor">
        <div className="toolbar">
          <div className="toolbar-cluster">
            <Tool active={tool==='select'} onClick={()=>setTool('select')} label="Select · V" tone="select"><SelectIcon/></Tool>
            <Tool active={tool==='positive'} onClick={()=>setTool('positive')} label="Point · 1" tone="positive"><PointIcon/></Tool>
            <Tool active={tool==='negative'} onClick={()=>setTool('negative')} label="Exclude · 2" tone="negative"><ExcludeIcon/></Tool>
            <Tool active={tool==='box'} onClick={()=>setTool('box')} label="Box · B" tone="box"><BoxIcon/></Tool>
            <Tool active={tool==='brush'} onClick={()=>setTool('brush')} label="Brush · W" tone="brush"><BrushIcon/></Tool>
            <Tool active={tool==='erase'} onClick={()=>setTool('erase')} label="Eraser · E" tone="erase"><EraserIcon/></Tool>
            {(tool==='brush'||tool==='erase')&&<div className="brush-control">
              <input type="range" min="1" max="80" value={brushSize} onChange={e=>setBrushSize(Number(e.target.value))} aria-label="Brush size"/>
              <b>{brushSize}</b>
            </div>}
            <Tool active={tool==='pan'} onClick={()=>setTool('pan')} label="Hand · H" tone="pan"><HandIcon/></Tool>
            <button className="tool tone-history" onClick={undoEdit} disabled={!canUndo} title="Undo · Ctrl+Z" aria-label="Undo"><UndoIcon/></button>
            <button className="tool tone-history" onClick={redoEdit} disabled={!canRedo} title="Redo · Ctrl+Y" aria-label="Redo"><RedoIcon/></button>
            <div className="zoom-control">
              <button className="tool" onClick={()=>setZoom(z=>Math.max(.4,z-.1))} title="Zoom out" aria-label="Zoom out">−</button>
              <span>{Math.round(zoom*100)}%</span>
              <button className="tool" onClick={()=>setZoom(z=>Math.min(2.5,z+.1))} title="Zoom in" aria-label="Zoom in">+</button>
            </div>
          </div>
        </div>
        <div className="canvas-wrap">
          <AnnotationCanvas ref={canvas} imageUrl={api.frameUrl(media.id,frame)} points={points} box={box} tool={tool} brushSize={brushSize} zoom={zoom} disabled={promptBusy} overlays={overlays} focusedId={selected?.id??null} selectedIds={selectedIds} finished={selected!=null&&finishedIds.includes(selected.id)} finishedIds={finishedIds} labels={project.labels} labelId={labelId} showLabelMenu={dirty||!!selected} onPoint={addPoint} onBox={setPromptBox} onDirty={()=>{if(tool==='brush'&&!selected)return;setDirty(true);setSaveState('Unsaved changes')}} onBeforeEdit={pushHistory} onBrushStroke={()=>{void finishBrushDetect()}} onSelect={(id,additive)=>{void pickMask(id,additive)}} onSelectIds={(ids,additive)=>{void pickMasks(ids,additive)}} onUnfocus={()=>{void unfocusMask()}} onLabelId={changeClass} onFinish={()=>{void finishMask()}}/>
        </div>
        <div className="editor-footer">
          <div className={`editor-chrome${isStill?' stills-chrome':''}`}>
            <div className="transport">
              <button type="button" onClick={()=>isStill?gotoStill(-10):void gotoFrame(frame-10)} disabled={isStill?stillPos<=0:frame<=0} title={isStill?'Previous 10 · Shift+←':'Previous 10 · Shift+←'} aria-label="Jump back 10">‹‹</button>
              <button type="button" className="transport-step" onClick={()=>isStill?gotoStill(-1):void gotoFrame(frame-1)} disabled={isStill?stillPos<=0:frame<=0} title={isStill?'Previous · ←':'Previous · ←'} aria-label="Previous">‹</button>
            </div>
            {isStill
              ? <div className="timeline" style={{'--timeline-progress':`${stills.length>1?stillPos/Math.max(1,stills.length-1)*100:0}%`} as CSSProperties}>
                  <div className="timeline-track">
                    {stillRows.filter(item=>item.annotation_count>0).map(item=>(
                      <i key={item.mediaId} className={`timeline-mark${item.mediaId===media.id?' current':''}`} style={{left:`${stills.length>1?item.index/Math.max(1,stills.length-1)*100:0}%`}} title={`Picture ${displayIndex(item.index)}`}/>
                    ))}
                    <input type="range" min={1} max={Math.max(1,stills.length)} value={displayIndex(Math.max(0,stillPos))} onChange={e=>gotoStillAt(fromDisplayIndex(Number(e.target.value)))} aria-label="Pictures"/>
                  </div>
                </div>
              : <div className="timeline" style={{'--timeline-progress':`${lastFrame?frame/lastFrame*100:0}%`} as CSSProperties}>
                  <div className="timeline-track">
                    {frames.filter(item=>item.annotation_count>0).map(item=>(
                      <i key={item.frame} className={`timeline-mark${item.frame===frame?' current':''}`} style={{left:`${lastFrame?item.frame/lastFrame*100:0}%`}} title={`Frame ${displayIndex(item.frame)}`}/>
                    ))}
                    <input type="range" min={0} max={lastFrame} value={frame} onChange={e=>gotoFrame(Number(e.target.value))} aria-label="Timeline"/>
                  </div>
                </div>}
            <div className="transport">
              <button type="button" className="transport-step" onClick={()=>isStill?gotoStill(1):void gotoFrame(frame+1)} disabled={isStill?stillPos>=stills.length-1:frame>=lastFrame} title="Next · →" aria-label="Next">›</button>
              <button type="button" onClick={()=>isStill?gotoStill(10):void gotoFrame(frame+10)} disabled={isStill?stillPos>=stills.length-1:frame>=lastFrame} title="Next 10 · Shift+→" aria-label="Jump forward 10">››</button>
            </div>
            {isStill
              ? <span className="chrome-count">{displayIndex(Math.max(0,stillPos))}<small>/</small>{stills.length}</span>
              : <>
                  <label className="frame-jump">
                    <span>Frame</span>
                    <input type="number" value={displayIndex(frame)} min={1} max={displayIndex(lastFrame)} onChange={e=>setFrame(fromDisplayIndex(Number(e.target.value)))} onKeyDown={e=>{if(e.key==='Enter')gotoFrame(frame)}}/>
                    <span className="frame-total">/ {displayIndex(lastFrame)}</span>
                  </label>
                  <span className="timeline-time">{media.fps?`${(frame/media.fps).toFixed(2)}s`:`${displayIndex(frame)}`}</span>
                </>}
          </div>
        </div>
      </main>
      <aside className="right-rail">
        <section className="rail-card tracker-card">
          <div className="tracker-head">
            <span className="tracker-mark" aria-hidden="true">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="3"/>
                <path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21"/>
                <path d="m5.6 5.6 1.8 1.8M16.6 16.6l1.8 1.8M18.4 5.6 16.6 7.4M7.4 16.6 5.6 18.4"/>
              </svg>
            </span>
            <div>
              <h3>SAM2 tracker</h3>
              <p>{isStill?'Follow selected masks through the pictures':'Follow selected masks through the video'}</p>
            </div>
          </div>
          <div className="track-fields two">
            <label>From<input type="number" min={1} max={displayIndex(lastTrack)} value={displayIndex(trackFrom)} onChange={e=>setTrackFrom(fromDisplayIndex(Number(e.target.value)))} onKeyDown={e=>{if(e.key==='Enter'){if(isStill)gotoStillAt(trackFrom);else gotoFrame(trackFrom)}}}/></label>
            <label>To<input type="number" min={1} max={displayIndex(lastTrack)} value={displayIndex(target)} onChange={e=>setTarget(fromDisplayIndex(Number(e.target.value)))}/></label>
          </div>
          <div className="tracker-meta">
            <label className="track-step">Save every<input type="number" min={1} max={60} value={trackStep} onChange={e=>setTrackStep(Math.max(1,Number(e.target.value)))}/></label>
            <label className="switch-row"><input type="checkbox" checked={replaceAuto} onChange={e=>setReplaceAuto(e.target.checked)}/><span>Replace auto</span></label>
          </div>
          <button className="primary wide" onClick={startTrack} disabled={trackJob?.status==='running'||(Math.max(0,Math.min(trackFrom,lastTrack))===trackPos&&!trackSeedIds.length)}>{trackButtonLabel(trackSeedIds.length)}</button>
          {trackJob&&<div className="job">
            <div><strong>{trackJob.status==='cancelled'?'stopped':trackJob.status}</strong><span>{trackJob.progress}%</span></div>
            <div className="progress"><i style={{width:`${trackJob.progress}%`}}/></div>
            <small>{isStill?'Picture':'Frame'} {trackJob.current_frame==null?'–':displayIndex(trackJob.current_frame)} · saved {trackJob.created_annotations.length}</small>
            {trackJob.status==='running'&&<button className="danger wide" onClick={stopTrack}>Stop and save</button>}
            {trackJob.error&&<p className="error-inline">{trackJob.error}</p>}
          </div>}
        </section>
        <section className="rail-card">
          <div className="section-title compact"><h3>Current mask</h3></div>
          <div className="current-class">
            <i style={{background:project.labels.find(label=>label.id===labelId)?.color??'#4e8ef7'}}/>
            <strong>{project.labels.find(label=>label.id===labelId)?.name??'No class'}</strong>
          </div>
          <div className="label-picker">
            {project.labels.map(label=>(
              <button type="button" key={label.id} className={`label-row-btn ${labelId===label.id?'active':''}`} onClick={()=>changeClass(label.id)}>
                <span className="label-bar" style={{background:label.color}}/>
                <span>{label.name}</span>
              </button>
            ))}
            <button type="button" className="label-row-btn add" onClick={newLabel}>+ Add class</button>
          </div>
          <div className="action-row">
            <button className="primary" onClick={()=>saveCurrent(false)} disabled={busy||promptBusy}>Save mask</button>
            <button className="danger" onClick={deleteCurrentAnnotation} disabled={!selected&&!selectedIds.length}>
              {selectedIds.length>1?`Delete ${selectedIds.length}`:'Delete'}
            </button>
          </div>
        </section>
        <section className="rail-card">
          <h3>Export project</h3>
          <button className="primary wide" onClick={()=>setShowExport(true)}>Export…</button>
          <p className="muted">COCO, YOLO-seg, Pascal VOC, or a native backup. You can merge every project from the dashboard.</p>
        </section>
      </aside>
    </div>
    <footer className="statusbar">
      <span>{promptBusy?'SAM2 predicting…':status}</span>
      <span>{isStill?'← → pictures · Esc unfocus · V select · 1 add · 2 cut · tick to finish':'← → frames · Esc unfocus · V select · 1 add · 2 cut · tick to finish'}</span>
    </footer>
    {dialogs}
  </div>;

  return <div className="page-shell product-shell">
    <AppNav onExport={()=>setShowExport(true)} exportDisabled={boot!=='ready'||!projects.length}/>
    <div className="empty-state"><h2>Loading</h2><p>Opening this page…</p></div>
    {dialogs}
  </div>;
}

function Tool({active,onClick,label,children,tone}:{active:boolean;onClick:()=>void;label:string;children:ReactNode;tone?:string}){
  return <button type="button" className={`tool${active?' active':''}${tone?` tone-${tone}`:''}`} onClick={onClick} title={label} aria-label={label} aria-pressed={active}>{children}</button>;
}

function ToolSvg({children}:{children:ReactNode}){
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{children}</svg>;
}
function SelectIcon(){
  return <ToolSvg><path d="M5 3.5 9.2 20l2.2-6.4L18 11.6z"/><path d="m11.4 13.6 5.8 6.2"/></ToolSvg>;
}
function PointIcon(){
  return <ToolSvg><circle cx="12" cy="12" r="7.5"/><path d="M12 8.5v7M8.5 12h7"/></ToolSvg>;
}
function ExcludeIcon(){
  return <ToolSvg><circle cx="12" cy="12" r="7.5"/><path d="M8.5 12h7"/></ToolSvg>;
}
function BoxIcon(){
  return <ToolSvg><rect x="5" y="6" width="14" height="12" rx="2"/></ToolSvg>;
}
function BrushIcon(){
  return <ToolSvg><path d="M14.5 4.5 19 9l-8.2 8.2c-.7.7-1.6 1.1-2.6 1.2l-3.2.3.3-3.2c.1-1 .5-1.9 1.2-2.6z"/><path d="m16.2 6.2 1.6 1.6"/></ToolSvg>;
}
function EraserIcon(){
  return <ToolSvg><path d="m7 15 8.5-8.5a2.1 2.1 0 0 1 3 3L10 18H7z"/><path d="M6 20h12"/></ToolSvg>;
}
function HandIcon(){
  return <ToolSvg><path d="M8 11.5V7.2a1.4 1.4 0 0 1 2.8 0V11"/><path d="M10.8 10.5V6.4a1.4 1.4 0 0 1 2.8 0V11"/><path d="M13.6 10.2V7.6a1.4 1.4 0 0 1 2.8 0V13c0 3.1-2.1 5.2-5.2 5.2h-.4C7.7 18.2 6 16 6 13.2V11"/></ToolSvg>;
}

function UndoIcon(){
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 15 3 9l6-6"/><path d="M3 9h12a6 6 0 0 1 0 12h-3"/></svg>;
}
function RedoIcon(){
  return <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m15 15 6-6-6-6"/><path d="M21 9H9a6 6 0 0 0 0 12h3"/></svg>;
}
function TrashIcon(){
  return <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><polyline points="3 6 5 6 21 6"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/></svg>;
}
function CheckIcon(){
  return <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>;
}

function FrameFilters(props:{
  status:FrameStatusFilter;
  labelIds:number[];
  labels:Label[];
  onStatus:(status:FrameStatusFilter)=>void;
  onLabels:(ids:number[])=>void;
}){
  const root=useRef<HTMLDivElement>(null);
  const [open,setOpen]=useState(false);
  const picked=props.labels.filter(label=>props.labelIds.includes(label.id));
  const summary=picked.length===0?'All types':picked.length===1?picked[0].name:`${picked.length} types`;
  useEffect(()=>{
    if(!open)return;
    const onDoc=(e:PointerEvent)=>{if(!root.current?.contains(e.target as Node))setOpen(false)};
    const onKey=(e:KeyboardEvent)=>{if(e.key==='Escape'){e.preventDefault();e.stopPropagation();setOpen(false)}};
    document.addEventListener('pointerdown',onDoc);
    window.addEventListener('keydown',onKey,true);
    return()=>{document.removeEventListener('pointerdown',onDoc);window.removeEventListener('keydown',onKey,true)};
  },[open]);
  return <div className="frame-filters" ref={root}>
    <div className="filter-seg" role="group" aria-label="Annotation status">
      {([['all','All'],['annotated','Annotated'],['unannotated','Empty']] as const).map(([value,label])=>(
        <button type="button" key={value} className={props.status===value?'active':''} aria-pressed={props.status===value} onClick={()=>props.onStatus(value)}>{label}</button>
      ))}
    </div>
    <div className="filter-type">
      <span>Defect</span>
      <button type="button" className={`filter-type-btn${open?' open':''}${picked.length?' active':''}`} aria-haspopup="listbox" aria-expanded={open} aria-label="Defect type" onClick={()=>setOpen(value=>!value)}>
        <span className="filter-type-dots">
          {picked.slice(0,3).map(label=>(
            <i key={label.id} style={{background:label.color}}/>
          ))}
        </span>
        <span className="filter-type-summary">{summary}</span>
      </button>
      {open&&<div className="filter-type-menu" role="listbox" aria-multiselectable="true" aria-label="Defect types">
        {props.labels.length===0&&<p className="filter-type-empty">No defect labels yet</p>}
        {props.labels.map(label=>{
          const checked=props.labelIds.includes(label.id);
          return <button type="button" key={label.id} role="option" aria-selected={checked} className={`filter-type-option${checked?' checked':''}`} onClick={()=>props.onLabels(toggleSelection(props.labelIds,label.id))}>
            <span className={`filter-check${checked?' on':''}`}>{checked&&<CheckIcon/>}</span>
            <i style={{background:label.color}}/>
            <span>{label.name}</span>
          </button>;
        })}
        {picked.length>0&&<button type="button" className="filter-type-clear" onClick={()=>props.onLabels([])}>Clear types</button>}
      </div>}
    </div>
  </div>;
}

function FrameThumb(props:{
  mediaId:number;
  item:FrameInfo;
  indexLabel?:number;
  active:boolean;
  onOpen:()=>void;
  onExclude:(alsoDelete:boolean)=>void;
  onRestore:()=>void;
  onEdit:(id:number)=>void;
  onDeleteAnn:(id:number)=>void;
}){
  const ref=useRef<HTMLDivElement>(null);
  const [show,setShow]=useState(props.active);
  useEffect(()=>{
    const el=ref.current;
    if(!el)return;
    const root=el.closest('.frame-list');
    const io=new IntersectionObserver(entries=>{
      if(entries[0]?.isIntersecting)setShow(true);
    },{root:root instanceof Element?root:null,rootMargin:'280px'});
    io.observe(el);
    return()=>io.disconnect();
  },[]);
  useEffect(()=>{
    if(!props.active)return;
    setShow(true);
    ref.current?.scrollIntoView({block:'nearest'});
  },[props.active]);
  const labels=props.item.labels??[];
  return <div ref={ref} className={`frame-thumb ${props.active?'active':''} ${props.item.excluded?'excluded':''}`}>
    <button type="button" className="frame-open" onClick={props.onOpen}>
      {show?<img src={api.frameUrl(props.mediaId,props.item.frame,180)} alt=""/>:<span className="frame-ph"/>}
    </button>
    <span className="frame-index">{displayIndex(props.indexLabel??props.item.frame)}</span>
    {props.item.excluded
      ? <button type="button" className="thumb-action restore" title="Restore frame" onClick={props.onRestore}>↩</button>
      : <button type="button" className="thumb-action delete" title="Exclude frame. Shift-click also deletes annotations." onClick={e=>{e.stopPropagation();props.onExclude(e.shiftKey)}}><TrashIcon/></button>}
    {labels.length>0&&<div className="frame-tags">
      {labels.map(lab=>(
        <span key={lab.annotation_id} className="frame-tag" style={{background:lab.color}}>
          <button type="button" title={`Edit ${lab.name}`} onClick={()=>props.onEdit(lab.annotation_id)}>{lab.name}</button>
          <button type="button" className="tag-x" title="Delete annotation" onClick={()=>props.onDeleteAnn(lab.annotation_id)}>×</button>
        </span>
      ))}
    </div>}
  </div>;
}

function Toast({text,close}:{text:string;close:()=>void}){
  return <div className="toast"><strong>Error</strong><span>{text}</span><button onClick={close}>×</button></div>;
}
