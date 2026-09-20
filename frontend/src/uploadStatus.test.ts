import assert from 'node:assert/strict';
import test from 'node:test';
import {reusedMediaNotice,reusedMediaStatus} from './uploadStatus.ts';

test('fresh uploads report a generic success',()=>{
  assert.equal(reusedMediaStatus([{name:'a.mp4',kind:'video'}]),'Media uploaded');
});

test('reused video names the file and keeps its annotations',()=>{
  assert.equal(
    reusedMediaStatus([{name:'pipe.mp4',kind:'video',reused:true,annotation_count:12}]),
    'pipe.mp4 already exists. Using that video with its 12 annotations.',
  );
});

test('reused picture uses picture wording',()=>{
  assert.equal(
    reusedMediaStatus([{name:'joint.png',kind:'image',reused:true,annotation_count:1}]),
    'joint.png already exists. Using that picture with its 1 annotation.',
  );
});

test('mixed batch mentions both new files and reused ones',()=>{
  assert.equal(
    reusedMediaStatus([
      {name:'new.mp4',kind:'video'},
      {name:'old.png',kind:'image',reused:true,annotation_count:0},
    ]),
    'Media uploaded. old.png already exists. Using that picture with its 0 annotations.',
  );
});

test('fresh uploads have no reuse dialog',()=>{
  assert.equal(reusedMediaNotice([{name:'a.mp4',kind:'video'}]),null);
});

test('reused video dialog says the video exists and will keep annotations',()=>{
  assert.deepEqual(
    reusedMediaNotice([{id:4,name:'pipe.mp4',kind:'video',reused:true,annotation_count:12}]),
    {
      title:'This video already exists',
      hint:'Using pipe.mp4 with its 12 annotations.',
    },
  );
});

test('reused picture dialog says the picture exists',()=>{
  assert.deepEqual(
    reusedMediaNotice([{id:9,name:'joint.png',kind:'image',reused:true,annotation_count:1}]),
    {
      title:'This picture already exists',
      hint:'Using joint.png with its 1 annotation.',
    },
  );
});

test('duplicate rows for the same media open one dialog',()=>{
  assert.deepEqual(
    reusedMediaNotice([
      {id:4,name:'pipe.mp4',kind:'video',reused:true,annotation_count:2},
      {id:4,name:'pipe-copy.mp4',kind:'video',reused:true,annotation_count:2},
    ]),
    {
      title:'This video already exists',
      hint:'Using pipe.mp4 with its 2 annotations.',
    },
  );
});

test('mixed reused files share one dialog',()=>{
  assert.deepEqual(
    reusedMediaNotice([
      {id:1,name:'new.mp4',kind:'video'},
      {id:2,name:'old.png',kind:'image',reused:true,annotation_count:0},
      {id:3,name:'clip.mp4',kind:'video',reused:true,annotation_count:4},
    ]),
    {
      title:'These files already exist',
      hint:'Using old.png with its 0 annotations. Using clip.mp4 with its 4 annotations.',
    },
  );
});
