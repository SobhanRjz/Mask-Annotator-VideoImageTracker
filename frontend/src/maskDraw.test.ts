import assert from 'node:assert/strict';
import test from 'node:test';
import {MASK_FILL_ALPHA,alphaIntersectsBox,maskCentroid,overlayFillAlpha,overlayOutlineAlpha,overlayTone,unionMaskAlpha} from './maskDraw.ts';

test('mask centroid sits inside occupied pixels',()=>{
  const width=4,height=4;
  const data=new Uint8ClampedArray(width*height*4);
  const paint=(x:number,y:number)=>{const i=(y*width+x)*4;data[i+3]=255};
  paint(2,1);paint(3,1);paint(2,2);paint(3,2);
  const c=maskCentroid(data,width,height);
  assert.ok(c);
  assert.equal(c.x,2.5);
  assert.equal(c.y,1.5);
});

test('empty mask has no centroid',()=>{
  const data=new Uint8ClampedArray(4*4*4);
  assert.equal(maskCentroid(data,4,4),null);
});

test('focused and idle fills stay transparent enough to show the frame',()=>{
  assert.ok(overlayFillAlpha('idle')<=.18);
  assert.ok(overlayFillAlpha('focused')<=.24);
  assert.ok(MASK_FILL_ALPHA<=.24);
  assert.ok(overlayFillAlpha('idle')<overlayFillAlpha('focused'));
});

test('selected masks are a middle tone between idle and focused',()=>{
  assert.ok(overlayFillAlpha('idle')<overlayFillAlpha('selected'));
  assert.ok(overlayFillAlpha('selected')<=overlayFillAlpha('focused'));
  assert.equal(overlayTone(2,2,[2,4]),'focused');
  assert.equal(overlayTone(4,2,[2,4]),'selected');
  assert.equal(overlayTone(9,2,[2,4]),'idle');
});

test('focused and idle masks keep a strong white ring around a see-through fill',()=>{
  assert.ok(overlayOutlineAlpha('idle')>=.8);
  assert.ok(overlayOutlineAlpha('focused')>=.9);
  assert.ok(overlayOutlineAlpha('idle')<=overlayOutlineAlpha('focused'));
});

test('a marquee hits a mask when any occupied pixel sits in the box',()=>{
  const width=8,height=8;
  const data=new Uint8ClampedArray(width*height*4);
  data[(3*width+3)*4+3]=255;
  assert.equal(alphaIntersectsBox(data,width,height,{x0:2,y0:2,x1:5,y1:5}),true);
  assert.equal(alphaIntersectsBox(data,width,height,{x0:5,y0:5,x1:7,y1:7}),false);
});

test('extra rectangle pixels are unioned with the current mask',()=>{
  const a=new Uint8ClampedArray(8);
  const b=new Uint8ClampedArray(8);
  a[3]=255;
  b[7]=200;
  const merged=unionMaskAlpha(a,b);
  assert.equal(merged[3],255);
  assert.equal(merged[7],255);
  assert.equal(merged[0],255);
  assert.equal(merged[4],255);
});
