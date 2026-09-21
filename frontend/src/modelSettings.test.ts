import assert from 'node:assert/strict';
import test from 'node:test';
import {cacheLabel,modelCardDisabled,modelJobActive,modelProgressText} from './modelSettings.ts';

test('four settings labels distinguish cached checkpoints',()=>{
  assert.equal(cacheLabel(true),'Downloaded');
  assert.equal(cacheLabel(false),'Not downloaded');
});

test('a running switch shows the backend progress message',()=>{
  assert.equal(modelJobActive({id:'1',key:'large',status:'running',progress:42,message:'Downloading 42%'}),true);
  assert.equal(modelProgressText({id:'1',key:'large',status:'running',progress:42,message:'Downloading 42%'}),'Downloading 42%');
  assert.equal(modelProgressText({id:'1',key:'large',status:'queued',progress:1,message:'Waiting for tracker to finish…'}),'Waiting for tracker to finish…');
});

test('a failed switch shows the error and keeps other cards clickable',()=>{
  const job={id:'1',key:'large',status:'failed',progress:80,error:'CUDA out of memory'};
  assert.equal(modelJobActive(job),false);
  assert.equal(modelProgressText(job),'CUDA out of memory');
  assert.equal(modelCardDisabled(job,'tiny','small'),false);
});
