import assert from 'node:assert/strict';
import test from 'node:test';
import {coveragePercent,formatProjectDate,projectBadge,projectHref,slugifyProjectName,typedNameMatches} from './projectSlug.ts';

test('project URLs use the unique name slug, not the numeric id',()=>{
  assert.equal(projectHref({id:12,slug:'riverside-trunk'}),'/projects/riverside-trunk');
  assert.equal(projectHref({id:12,slug:'riverside-trunk'},'/media/9'),'/projects/riverside-trunk/media/9');
});

test('numeric ids remain a fallback for legacy rows',()=>{
  assert.equal(projectHref({id:4}),'/projects/4');
});

test('human project names become URL slugs',()=>{
  assert.equal(slugifyProjectName('Site A – North interceptor'),'site-a-north-interceptor');
  assert.equal(slugifyProjectName('   '),'project');
});

test('coverage is annotated frames over extracted frames',()=>{
  assert.equal(coveragePercent(3,11),27.3);
  assert.equal(coveragePercent(0,0),0);
});

test('project delete requires the exact displayed name',()=>{
  assert.equal(typedNameMatches('Riverside trunk','Riverside trunk'),true);
  assert.equal(typedNameMatches('  Riverside trunk  ','Riverside trunk'),true);
  assert.equal(typedNameMatches('riverside trunk','Riverside trunk'),false);
  assert.equal(typedNameMatches('Riverside','Riverside trunk'),false);
  assert.equal(typedNameMatches('','Riverside trunk'),false);
});

test('project cards show day month and year on the mask badge',()=>{
  assert.equal(formatProjectDate('2026-09-30 08:15:00'),'30 Sep 2026');
  assert.equal(formatProjectDate('2026-01-03T12:00:00Z'),'3 Jan 2026');
  assert.equal(projectBadge(12,'2026-09-30 08:15:00'),'12 masks · 30 Sep 2026');
  assert.equal(projectBadge(1,'2026-09-30 08:15:00'),'1 mask · 30 Sep 2026');
  assert.equal(projectBadge(0,'2026-09-30 08:15:00'),'0 masks · 30 Sep 2026');
});
