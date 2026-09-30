import assert from 'node:assert/strict';
import test from 'node:test';
import {clampExtractRate,completedExtractBatchStatus,extractDialogVisible,extractionBatchFinished,mergeExtractionJobs,sourceFps} from './extractWorkflow.ts';

test('the extract dialog stays open even when a reused-file notice is showing',()=>{
  assert.equal(extractDialogVisible(1,false),true);
  assert.equal(extractDialogVisible(2,true),true);
  assert.equal(extractDialogVisible(0,true),false);
  assert.equal(extractDialogVisible(0,false),false);
});

test('extract FPS is clamped so the form cannot silently fail HTML validation',()=>{
  assert.equal(clampExtractRate(25,1),1);
  assert.equal(clampExtractRate(25,40),25);
  assert.equal(clampExtractRate(25,0),0.1);
  assert.equal(clampExtractRate(0.5,1),0.5);
  assert.equal(clampExtractRate(25,Number.NaN),1);
});

test('source fps falls back when probe data is missing',()=>{
  assert.equal(sourceFps({source_fps:25,fps:30}),25);
  assert.equal(sourceFps({fps:12}),12);
  assert.equal(sourceFps({}),25);
});

test('polling one video must not drop other videos from the extract batch',()=>{
  const current={
    1:{id:'a',media_id:1,requested_fps:1,status:'running',progress:40,frame_count:0},
    2:{id:'b',media_id:2,requested_fps:1,status:'queued',progress:0,frame_count:0},
  };
  const merged=mergeExtractionJobs(current,[{id:'a',media_id:1,requested_fps:1,status:'running',progress:70,frame_count:0}]);
  assert.equal(merged[1].progress,70);
  assert.equal(merged[2].status,'queued');
  assert.equal(extractionBatchFinished([{id:'a',media_id:1,requested_fps:1,status:'completed',progress:100,frame_count:10}],current),false);
});

test('the extract batch finishes only after every video is terminal',()=>{
  const jobs={
    1:{id:'a',media_id:1,requested_fps:1,status:'completed',progress:100,frame_count:10},
    2:{id:'b',media_id:2,requested_fps:1,status:'failed',progress:0,frame_count:0},
  };
  assert.equal(extractionBatchFinished(Object.values(jobs),jobs),true);
});

test('completed extract batch reports correct status and allows closing panel',()=>{
  const completedJobs=[
    {id:'a',media_id:1,status:'completed'},
    {id:'b',media_id:2,status:'completed'},
  ];
  assert.equal(completedExtractBatchStatus(completedJobs),'Extraction complete');

  const failedJobs=[
    {id:'a',media_id:1,status:'completed'},
    {id:'b',media_id:2,status:'failed'},
  ];
  assert.equal(completedExtractBatchStatus(failedJobs),'Some videos could not be extracted');

  // Once finished and queue is cleared, the dialog is hidden
  assert.equal(extractDialogVisible(0),false);
});
