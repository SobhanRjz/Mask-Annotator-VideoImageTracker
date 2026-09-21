import assert from 'node:assert/strict';
import test from 'node:test';
import type {Media} from './types.ts';
import {filterFrames} from './editorWorkflow.ts';
import {filterLibrary,firstIncompleteStill,libraryRows,libraryTabCounts,picturesComplete,stepStill,stillFrameRows,stillsOf,trackCursor,trackLastIndex,trackSeedMediaId} from './mediaLibrary.ts';

function media(partial:Partial<Media>&Pick<Media,'id'|'kind'>):Media{
  return {
    project_id:1,
    name:`${partial.kind}-${partial.id}`,
    width:64,
    height:48,
    frame_count:partial.kind==='video'?8:1,
    fps:1,
    annotation_complete:false,
    ...partial,
  };
}

const sample=[
  media({id:30,kind:'video',name:'newer.mp4',annotation_complete:true}),
  media({id:20,kind:'image',name:'b.jpg',annotation_complete:true}),
  media({id:10,kind:'image',name:'a.jpg',annotation_complete:false}),
  media({id:5,kind:'video',name:'older.mp4',annotation_complete:false}),
];

test('stills sort by id ascending',()=>{
  assert.deepEqual(stillsOf(sample).map(item=>item.id),[10,20]);
});

test('album complete only when every still is flagged',()=>{
  assert.equal(picturesComplete(sample),false);
  assert.equal(picturesComplete([media({id:1,kind:'image',annotation_complete:true})]),true);
  assert.equal(picturesComplete([]),false);
  assert.equal(picturesComplete([
    media({id:1,kind:'image',annotation_complete:true}),
    media({id:2,kind:'image',annotation_complete:false}),
  ]),false);
});

test('library rows put pictures first then videos in given order',()=>{
  const rows=libraryRows(sample);
  assert.equal(rows[0]?.kind,'pictures');
  if(rows[0]?.kind!=='pictures')return;
  assert.deepEqual(rows[0].images.map(item=>item.id),[10,20]);
  assert.equal(rows[0].complete,false);
  assert.deepEqual(rows.filter(row=>row.kind==='video').map(row=>row.kind==='video'?row.media.id:-1),[30,5]);
});

test('tabs keep all, completed, or not-complete rows',()=>{
  const rows=libraryRows(sample);
  const counts=libraryTabCounts(rows);
  assert.deepEqual(counts,{all:3,completed:1,not_annotated:2});
  assert.equal(filterLibrary(rows,'all').length,3);
  assert.deepEqual(filterLibrary(rows,'completed').map(row=>row.kind),['video']);
  assert.deepEqual(filterLibrary(rows,'not_annotated').map(row=>row.kind),['pictures','video']);
});

test('first incomplete still prefers the lowest incomplete id',()=>{
  assert.equal(firstIncompleteStill(sample)?.id,10);
  assert.equal(firstIncompleteStill([
    media({id:3,kind:'image',annotation_complete:true}),
    media({id:8,kind:'image',annotation_complete:true}),
  ])?.id,3);
  assert.equal(firstIncompleteStill([]),null);
});

test('picture rows use the same annotated/empty and defect filters as video frames',()=>{
  const stills=[
    media({id:10,kind:'image',annotation_count:0}),
    media({id:20,kind:'image',annotation_count:1}),
    media({id:30,kind:'image',annotation_count:2}),
  ];
  const rows=stillFrameRows(stills,{
    20:{frame:0,annotation_count:1,excluded:false,labels:[{annotation_id:1,id:10,name:'Crack',color:'#e45'}]},
    30:{frame:0,annotation_count:2,excluded:false,labels:[
      {annotation_id:2,id:10,name:'Crack',color:'#e45'},
      {annotation_id:3,id:20,name:'Root',color:'#4e8'},
    ]},
  });
  assert.equal(rows.length,3);
  assert.deepEqual(rows.map(row=>row.mediaId),[10,20,30]);
  assert.deepEqual(rows.map(row=>row.index),[0,1,2]);
  assert.deepEqual(filterFrames(rows,'annotated',[]).map(row=>row.mediaId),[20,30]);
  assert.deepEqual(filterFrames(rows,'unannotated',[]).map(row=>row.mediaId),[10]);
  assert.deepEqual(filterFrames(rows,'all',[20]).map(row=>row.mediaId),[30]);
});

test('playlist next and previous clamp and step by 10',()=>{
  const stills=[
    media({id:1,kind:'image'}),
    media({id:2,kind:'image'}),
    media({id:3,kind:'image'}),
    media({id:4,kind:'image'}),
    media({id:5,kind:'image'}),
  ];
  assert.equal(stepStill(stills,1,-1)?.id,1);
  assert.equal(stepStill(stills,1,1)?.id,2);
  assert.equal(stepStill(stills,5,1)?.id,5);
  assert.equal(stepStill(stills,1,10)?.id,5);
  assert.equal(stepStill(stills,5,-10)?.id,1);
  assert.equal(stepStill(stills,99,1),null);
});

test('picture tracker uses album indices and the from-still as seed media',()=>{
  const stills=[
    media({id:10,kind:'image'}),
    media({id:20,kind:'image'}),
    media({id:30,kind:'image'}),
  ];
  assert.equal(trackLastIndex('image',stills.length,1),2);
  assert.equal(trackLastIndex('video',stills.length,8),7);
  assert.equal(trackCursor('image',1,0),1);
  assert.equal(trackCursor('video',1,4),4);
  assert.equal(trackSeedMediaId('image',stills,2,10),30);
  assert.equal(trackSeedMediaId('video',stills,2,99),99);
});
