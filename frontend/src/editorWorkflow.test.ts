import assert from 'node:assert/strict';
import test from 'node:test';
import {acceptedMaskId,annotatedFrameCount,boxStartsNewInstance,brushBoundsToBox,brushStrokeUsesDetection,clampMenuPos,clickOutsideUnfocuses,closeSessionAfterPredict,displayIndex,escapeUnfocusesMasks,filterFrames,fitScale,fromDisplayIndex,idsToDelete,idsToDropOnUndo,idsToTrack,keepPromptsAfterPredict,maskUrlForPrompt,mergeSelection,paintOverlayCopy,panBy,parseTrackPatch,selectDragStartsBox,selectDragStartsMarquee,selectEmptyRelease,toggleSelection,toolAfterGeneratedMask,trackButtonLabel,trackSeedsMatchFrom} from './editorWorkflow.ts';

test('a generated mask stays on the same prompt tool',()=>{
  assert.equal(toolAfterGeneratedMask('positive'),'positive');
  assert.equal(toolAfterGeneratedMask('box'),'box');
  assert.equal(toolAfterGeneratedMask('brush'),'brush');
  assert.equal(toolAfterGeneratedMask('negative'),'negative');
});

test('large frames fit inside the annotation viewport at 100 percent zoom',()=>{
  assert.equal(fitScale(1920,1080,1200,700,18),0.60625);
  assert.equal(fitScale(3840,2160,1200,700,18),0.303125);
  assert.equal(fitScale(640,480,1200,700,18),1);
});

test('later clicks keep earlier positive and negative points on the mask',()=>{
  assert.equal(keepPromptsAfterPredict(),true);
  assert.equal(closeSessionAfterPredict(),false);
});

test('a follow-up click does not resend the last overlay when positives already define the object',()=>{
  const overlay='data:image/png;base64,mask';
  assert.equal(maskUrlForPrompt([{x:1,y:1,positive:true}],null,overlay,false),null);
  assert.equal(maskUrlForPrompt([{x:1,y:1,positive:true},{x:2,y:2,positive:false}],null,overlay,false),null);
});

test('a negative-only refine still sends the current mask so SAM2 can cut instead of replace',()=>{
  const overlay='data:image/png;base64,mask';
  assert.equal(maskUrlForPrompt([{x:8,y:9,positive:false}],null,overlay,false),overlay);
  assert.equal(maskUrlForPrompt([],null,overlay,false),overlay);
  assert.equal(maskUrlForPrompt([{x:8,y:9,positive:false}],null,overlay,true),null);
});

test('a rectangle on an unfinished mask merges instead of starting a new annotation',()=>{
  assert.equal(boxStartsNewInstance(true,false),false);
});

test('a rectangle after the mask is accepted starts a new annotation',()=>{
  assert.equal(boxStartsNewInstance(true,true),true);
});

test('the first rectangle on an empty canvas is the current annotation, not a replacement',()=>{
  assert.equal(boxStartsNewInstance(false,false),false);
  assert.equal(boxStartsNewInstance(false,true),false);
});

test('undo drops annotations that were created after the restored snapshot',()=>{
  assert.deepEqual(idsToDropOnUndo([5,9],[5,9,12]),[12]);
  assert.deepEqual(idsToDropOnUndo([5,9],[5,9]),[]);
  assert.deepEqual(idsToDropOnUndo([],[7]),[7]);
});

test('select never starts a new detection rectangle',()=>{
  assert.equal(selectDragStartsBox(false),false);
  assert.equal(selectDragStartsBox(true),false);
  assert.equal(selectDragStartsMarquee(),true);
});

test('a click on empty canvas unfocuses; a drag is a selection marquee',()=>{
  assert.equal(selectEmptyRelease(2,2),'unfocus');
  assert.equal(selectEmptyRelease(40,28),'marquee');
});

test('shift-marquee adds ids; a plain marquee replaces the set',()=>{
  assert.deepEqual(mergeSelection([1,2],[3,4],false),[3,4]);
  assert.deepEqual(mergeSelection([1,2],[2,3],true),[1,2,3]);
});

test('delete uses the multi-selection, or the focused mask when nothing else is selected',()=>{
  assert.deepEqual(idsToDelete([4,9],2),[4,9]);
  assert.deepEqual(idsToDelete([],7),[7]);
  assert.deepEqual(idsToDelete([],null),[]);
});

test('still seeds must sit on the from picture at frame 0',()=>{
  const seeds=[{media_id:20,frame:0},{media_id:20,frame:0}];
  assert.equal(trackSeedsMatchFrom('image',seeds,1,20),true);
  assert.equal(trackSeedsMatchFrom('image',seeds,1,10),false);
  assert.equal(trackSeedsMatchFrom('image',[{media_id:20,frame:2}],1,20),false);
  assert.equal(trackSeedsMatchFrom('video',[{media_id:9,frame:4}],4,9),true);
  assert.equal(trackSeedsMatchFrom('video',[{media_id:9,frame:0}],4,9),false);
});

test('track uses the selection, the focused mask, or every mask on the from frame',()=>{
  assert.deepEqual(idsToTrack([4,9],2,[4,9,11]),[4,9]);
  assert.deepEqual(idsToTrack([],7,[7,11]),[7]);
  assert.deepEqual(idsToTrack([],null,[3,8,12]),[3,8,12]);
  assert.deepEqual(idsToTrack([],null,[]),[]);
});

test('the tracker button names one mask or a count',()=>{
  assert.equal(trackButtonLabel(0),'Track from this mask');
  assert.equal(trackButtonLabel(1),'Track from this mask');
  assert.equal(trackButtonLabel(3),'Track 3 masks');
});

test('the frames heading counts annotated frames against the full set',()=>{
  assert.equal(annotatedFrameCount([{annotation_count:0},{annotation_count:2},{annotation_count:1},{annotation_count:0}]),2);
  assert.equal(annotatedFrameCount([]),0);
});

const sampleFrames=[
  {frame:0,annotation_count:0,labels:[]},
  {frame:1,annotation_count:1,labels:[{id:10}]},
  {frame:2,annotation_count:2,labels:[{id:10},{id:20}]},
  {frame:3,annotation_count:1,labels:[{id:20}]},
];

test('frame status filter keeps all, annotated, or empty frames',()=>{
  assert.deepEqual(filterFrames(sampleFrames,'all',[]).map(item=>item.frame),[0,1,2,3]);
  assert.deepEqual(filterFrames(sampleFrames,'annotated',[]).map(item=>item.frame),[1,2,3]);
  assert.deepEqual(filterFrames(sampleFrames,'unannotated',[]).map(item=>item.frame),[0]);
});

test('defect type filter keeps frames that include any selected label',()=>{
  assert.deepEqual(filterFrames(sampleFrames,'all',[10]).map(item=>item.frame),[1,2]);
  assert.deepEqual(filterFrames(sampleFrames,'all',[20]).map(item=>item.frame),[2,3]);
  assert.deepEqual(filterFrames(sampleFrames,'all',[10,20]).map(item=>item.frame),[1,2,3]);
  assert.deepEqual(filterFrames(sampleFrames,'annotated',[10]).map(item=>item.frame),[1,2]);
  assert.deepEqual(filterFrames(sampleFrames,'unannotated',[10]).map(item=>item.frame),[]);
});

test('shift-click toggles one id in the selection',()=>{
  assert.deepEqual(toggleSelection([1,2],3),[1,2,3]);
  assert.deepEqual(toggleSelection([1,2],2),[1]);
});

test('a new brush stroke uses SAM2 detection like box and points',()=>{
  assert.equal(brushStrokeUsesDetection(false),'detect');
});

test('brush on a focused mask stays a local paint edit',()=>{
  assert.equal(brushStrokeUsesDetection(true),'paint');
});

test('escape unfocuses every mask instead of only clearing prompts',()=>{
  assert.equal(escapeUnfocusesMasks(),true);
});

test('hand tool pans by the pointer delta from the drag origin',()=>{
  assert.deepEqual(panBy({x:10,y:4},{x:100,y:50},{x:130,y:40}),{x:40,y:-6});
});

test('a finished brush stroke becomes the same SAM2 box as the rectangle tool',()=>{
  assert.deepEqual(brushBoundsToBox({x:10,y:20,w:40,h:28}),[10,20,50,48]);
  assert.equal(brushBoundsToBox({x:1,y:1,w:2,h:2}),null);
});

test('frame lists and jump fields show 1-based numbers',()=>{
  assert.equal(displayIndex(0),1);
  assert.equal(displayIndex(9),10);
  assert.equal(fromDisplayIndex(1),0);
  assert.equal(fromDisplayIndex(10),9);
  assert.equal(fromDisplayIndex(0),0);
});

test('the mask class bar stays inside the canvas wrap while dragging',()=>{
  assert.deepEqual(clampMenuPos(12,20,400,300,160,44),{left:12,top:20});
  assert.deepEqual(clampMenuPos(-40,-10,400,300,160,44),{left:8,top:8});
  assert.deepEqual(clampMenuPos(390,280,400,300,160,44),{left:232,top:248});
});

test('accepting a new detection uses the saved id even when selected is still null',()=>{
  assert.equal(acceptedMaskId(null,41),41);
  assert.equal(acceptedMaskId(7,7),7);
  assert.equal(acceptedMaskId(7,undefined),7);
});

test('a focused overlay is not painted again on top of the live mask',()=>{
  assert.equal(paintOverlayCopy(9,9),false);
  assert.equal(paintOverlayCopy(9,3),true);
  assert.equal(paintOverlayCopy(9,null),true);
});

test('eraser keeps painting the selected mask when the stroke starts outside it',()=>{
  assert.equal(clickOutsideUnfocuses('erase'),false);
  assert.equal(clickOutsideUnfocuses('brush'),true);
  assert.equal(clickOutsideUnfocuses('select'),true);
});

test('tracking patch size stays in a safe GPU range',()=>{
  assert.equal(parseTrackPatch(16),16);
  assert.equal(parseTrackPatch(1),2);
  assert.equal(parseTrackPatch(400),128);
  assert.equal(parseTrackPatch('nope'),16);
});
