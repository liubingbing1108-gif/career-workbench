/* Fictional data only. No server, browser, remote call or business mutation. */
const test = require('node:test');
const assert = require('node:assert/strict');
const contract = require('./web/integration.js');

const job = {id: 'fictional-role-1', company: '虚构公司', role: '虚构分析岗位', url: 'https://example.com/apply', application_status: '未投递', recruitment_stage: '', preference_order: '1', requires_preference: true, source_table: '虚构来源', source_record_id: 'fictional-source', timeline: [{label: '约一面日期', day: '2026-10-20'}]};

test('embedded mode exclusively prefixes management API requests', () => {
  assert.equal(contract.apiPath('/api/bootstrap', '?embedded=1'), '/management/api/bootstrap');
  assert.equal(contract.apiPath('/api/jobs/fictional', '?embedded=1'), '/management/api/jobs/fictional');
  assert.equal(contract.apiPath('/api/bootstrap', ''), '/api/bootstrap');
  assert.equal(contract.apiPath('/api/bootstrap', '?embedded=0'), '/api/bootstrap');
  assert.throws(() => contract.apiPath('https://example.com/api/jobs', '?embedded=1'));
});

test('readonly candidates cannot launch before confirmed intake', () => {
  assert.throws(() => contract.preparePayload(job,true), /先确认录入/);
});

test('local job handoff preserves confirmed status and custom recruitment stage', () => {
  const payload = contract.preparePayload({...job, application_status: '已投递', recruitment_stage: '四面'}, false);
  assert.equal(payload.job.application_status, '已投递');
  assert.equal(payload.job.recruitment_stage, '四面');
  assert.equal(payload.job.readonly, false);
});

test('missing roles, unsplit summary roles and unsafe links cannot prepare', () => {
  for (const patch of [{role: ''}, {company: ''}, {role: '岗位甲、岗位乙', role_summary: true}, {url: 'javascript:alert(1)'}]) {
    assert.equal(contract.canPrepare({...job, ...patch}), false);
    assert.throws(() => contract.preparePayload({...job, ...patch}));
  }
  assert.equal(contract.canPrepare({...job, role_summary: true, role: '人工补齐的具体岗位'}), true);
});

test('a chosen company and role can start official lookup without a supplied URL', () => {
  assert.equal(contract.canPrepare({...job,url:''}),true);
  assert.equal(contract.preparePayload({...job,url:''}).job.apply_url,'');
});

test('standalone page gives a clear integration message without cross-port navigation', () => {
  const host = {location: {origin: 'http://127.0.0.1:8770'}};
  host.parent = host;
  assert.throws(() => contract.postPrepare(job, false, host), /统一网站/);
});

test('summary counts local application facts', () => {
  const rows=[{...job,application_status:'已投递'},job];
  assert.deepEqual(contract.listStats(rows,false),[['投递事项',2],['计划投递',1],['已投递',1]]);
});

test('successful deletion notifies only its same-origin product host', () => {
  const calls = [], host = {location: {origin: 'http://127.0.0.1:8768'}, parent: {postMessage: (...args) => calls.push(args)}};
  contract.postDeleted(job.id, host);
  assert.deepEqual(calls, [[{type: 'workbench:deleted', job_id: job.id}, host.location.origin]]);
  host.parent = host;
  contract.postDeleted(job.id, host);
  assert.equal(calls.length, 1);
});

test('pending identity is blocked while HTTP sources can be inspected before HTTPS destination lookup', () => {
  assert.equal(contract.canPrepare({...job,needs_review:true}),false);
  assert.equal(contract.canPrepare({...job,url:'http://example.com/apply'}),true);
});
