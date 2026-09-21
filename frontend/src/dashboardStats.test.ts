import assert from 'node:assert/strict';
import test from 'node:test';
import {annotationPace,continueHref,defectShare,defectTotal,heatmapForFilter,remainingFrames} from './dashboardStats.ts';

test('continue goes to the first unfinished frame of the latest project',()=>{
  assert.equal(continueHref({project_id:4,project_slug:'harbor-main',media_id:9,frame:12}),'/projects/harbor-main/media/9?frame=12');
  assert.equal(continueHref({project_id:4,project_slug:'harbor-main',media_id:9,frame:0}),'/projects/harbor-main/media/9');
  assert.equal(continueHref({project_id:4,project_slug:null,media_id:null,frame:null}),'/projects/4');
  assert.equal(continueHref(null),'/projects');
});

test('defect mix shows count share of all saved annotations',()=>{
  assert.equal(defectTotal([128,25,20]),173);
  assert.equal(defectShare(128,173),74);
  assert.equal(defectShare(25,173),14);
  assert.equal(defectShare(0,0),0);
});

test('heatmap filter uses the all-grid or a class-specific grid',()=>{
  const all={width:2,height:1,values:[[1,0]]};
  const root={width:2,height:1,values:[[0,1]]};
  const report={heatmap:all,heatmaps:{Root:root}};
  assert.deepEqual(heatmapForFilter(report,'all').values,[[1,0]]);
  assert.deepEqual(heatmapForFilter(report,'Root').values,[[0,1]]);
  assert.deepEqual(heatmapForFilter(report,'Broken').values,[[0,0]]);
});

test('workload insight never reports negative remaining frames',()=>{
  assert.equal(remainingFrames(120,47),73);
  assert.equal(remainingFrames(12,18),0);
  assert.equal(remainingFrames(0,0),0);
});

test('annotation pace reports completed frames per active hour',()=>{
  assert.equal(annotationPace(75,5400),50);
  assert.equal(annotationPace(4,0),0);
  assert.equal(annotationPace(0,3600),0);
});
