import assert from 'node:assert/strict';
import test from 'node:test';
import {defaultExportOptions,exportHasContent,exportProjectIds,preparingExportLabel} from './exportWorkflow.ts';

test('homepage export defaults to all projects',()=>{
  const options=defaultExportOptions(null);
  assert.equal(options.scope,'all');
  assert.equal(options.projectId,null);
  assert.equal(options.format,'coco');
  assert.equal(options.includeUnannotated,true);
});

test('project-page export defaults to that project',()=>{
  const options=defaultExportOptions(12);
  assert.equal(options.scope,'project');
  assert.equal(options.projectId,12);
  assert.deepEqual(exportProjectIds(options),[12]);
});

test('all-projects scope sends a null project list so the backend merges',()=>{
  const options=defaultExportOptions(12);
  options.scope='all';
  assert.equal(exportProjectIds(options),null);
});

test('export is blocked when every annotation filter is off',()=>{
  const options=defaultExportOptions(1);
  options.includeUnannotated=false;
  options.includeAuto=false;
  options.includeManual=false;
  assert.equal(exportHasContent(options),false);
});

test('progress copy says the zip is being prepared',()=>{
  assert.match(preparingExportLabel('running',40),/Preparing the export/);
  assert.equal(preparingExportLabel('completed',100),'Export ready');
});
