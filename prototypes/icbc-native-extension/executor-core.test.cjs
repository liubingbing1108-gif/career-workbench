const {test}=require('node:test');
const assert=require('node:assert/strict');
const {create}=require('./executor-core.js');
function fixture(){
 const state={url:'https://example.test/form',value:'',other:'keep',count:1,writes:0,adds:0,errors:[],delay:0};
 const el={},otherEl={};let replacement=el;
 const adapter={page:()=>({url:state.url}),guard(){if(state.url!=='https://example.test/form')throw Error('wrong site');},fields:()=>[{id:'field',label:'姓名',kind:'text',el:replacement,current:state.value,constraints:{maxLength:30}},{id:'other',label:'备注',kind:'text',el:otherEl,current:state.other}],sections:()=>[{sectionId:'education',label:'教育',count:state.count,canAdd:true}],errors:()=>state.errors,async write(f,value,ctx){if(state.delay)await new Promise(r=>setTimeout(r,state.delay));ctx.check();state.writes++;if(f.id==='field')state.value=value;else state.other=value;},async settle(ctx){ctx.check();},async addRecord(id,ctx){ctx.check();state.count++;state.adds++;}};
 return {state,adapter,api:create(adapter),replace:()=>replacement={}};
}
async function plan(f,extra={}){const s=(await f.api.dispatch('scan')).result;return {schemaVersion:1,requestId:'r1',snapshotId:s.snapshotId,assignments:[{fieldId:'field',value:'测试答案'}],...extra};}
async function done(f){for(let n=0;n<100;n++){const j=(await f.api.dispatch('status')).result;if(j.status!=='running')return j;await new Promise(r=>setTimeout(r,2));}throw Error('test timed out');}
test('external answer fills and preserves unspecified fields',async()=>{const f=fixture(),p=await plan(f);assert.equal((await f.api.dispatch('execute',p)).ok,true);const j=await done(f);assert.equal(j.status,'complete');assert.equal(f.state.value,'测试答案');assert.equal(f.state.other,'keep');assert.equal(j.preserved,1);});
test('unknown field rejects entire plan before any write',async()=>{const f=fixture(),p=await plan(f);p.assignments.push({fieldId:'unknown',value:'x'});const r=await f.api.dispatch('execute',p);assert.equal(r.error.code,'UNKNOWN_FIELD');assert.equal(f.state.writes,0);});
test('raw selectors and scripts are rejected',async()=>{const f=fixture(),p=await plan(f);p.assignments[0].selector='button';assert.equal((await f.api.dispatch('execute',p)).error.code,'INVALID_REQUEST');assert.equal((await f.api.dispatch('submit')).error.code,'UNSUPPORTED_METHOD');assert.equal(f.state.writes,0);});
test('existing values are preserved unless explicit unchanged overwrite',async()=>{const f=fixture();f.state.value='existing';const p=await plan(f);assert.equal((await f.api.dispatch('execute',p)).error.code,'EXISTING_VALUE');p.assignments[0].overwrite='ifUnchanged';await f.api.dispatch('execute',p);assert.equal((await done(f)).status,'complete');});
test('manual changes after scan cannot be overwritten',async()=>{const f=fixture(),p=await plan(f);f.state.value='human edit';p.assignments[0].overwrite='ifUnchanged';assert.equal((await f.api.dispatch('execute',p)).error.code,'VALUE_CHANGED');assert.equal(f.state.writes,0);});
test('replaced control invalidates old field reference',async()=>{const f=fixture(),p=await plan(f);f.replace();assert.equal((await f.api.dispatch('execute',p)).error.code,'STALE_FIELD');});
test('new scan invalidates prior plan',async()=>{const f=fixture(),p=await plan(f);await f.api.dispatch('scan');assert.equal((await f.api.dispatch('execute',p)).error.code,'STALE_SNAPSHOT');});
test('duplicate field or overlong value rejected without truncation',async()=>{const f=fixture(),p=await plan(f);p.assignments.push({...p.assignments[0]});assert.equal((await f.api.dispatch('execute',p)).error.code,'DUPLICATE_FIELD');p.assignments.pop();p.assignments[0].value='x'.repeat(31);assert.equal((await f.api.dispatch('execute',p)).error.code,'VALUE_TOO_LONG');assert.equal(f.state.writes,0);});
test('same request replays result without performing writes',async()=>{const f=fixture(),p=await plan(f);await f.api.dispatch('execute',p);await done(f);const r=await f.api.dispatch('execute',p);assert.equal(r.result.replayed,true);assert.equal(f.state.writes,1);p.assignments[0].value='changed';assert.equal((await f.api.dispatch('execute',p)).error.code,'REQUEST_ID_REUSED');});
test('concurrent commands refused; cancellation prevents next input',async()=>{const f=fixture();f.state.delay=25;const p=await plan(f);await f.api.dispatch('execute',p);const p2={...p,requestId:'r2'};assert.equal((await f.api.dispatch('execute',p2)).error.code,'BUSY');await f.api.dispatch('cancel');assert.equal((await done(f)).status,'cancelled');assert.equal(f.state.writes,0);});
test('stop proof keeps original core identity and distinguishes cancel requested from settled',async()=>{
 const f=fixture();f.state.delay=25;const snapshot=(await f.api.dispatch('scan')).result;
 assert.equal(snapshot.capabilities.stopProof,1);const p=await plan(f);await f.api.dispatch('execute',p);
 await f.api.dispatch('cancel');let state=(await f.api.dispatch('executionState')).result;
 assert.equal(state.sessionId,snapshot.sessionId);assert.equal(state.busy,true);assert.equal(state.cancelled,true);
 await done(f);state=(await f.api.dispatch('executionState')).result;assert.equal(state.busy,false);assert.equal(state.cancelled,true);assert.equal(f.state.writes,0);
 assert.notEqual((await fixture().api.dispatch('executionState')).result.sessionId,state.sessionId);
 assert.equal((await f.api.dispatch('executionState',{selector:'unsafe'})).error.code,'INVALID_REQUEST');
 f.state.url='https://other.test/';assert.equal((await f.api.dispatch('executionState')).ok,false);
});
test('ensure target counts adds only missing rows and retry does not duplicate',async()=>{const f=fixture(),s=(await f.api.dispatch('scan')).result;const p={schemaVersion:1,requestId:'rows',snapshotId:s.snapshotId,sections:[{sectionId:'education',count:3}]};await f.api.dispatch('ensureRecords',p);const j=await done(f);assert.equal(j.status,'complete');assert.equal(f.state.adds,2);assert.equal(j.snapshot.sections[0].count,3);assert.equal((await f.api.dispatch('ensureRecords',p)).result.replayed,true);assert.equal(f.state.adds,2);});
test('ensure smaller target never deletes extra existing rows',async()=>{const f=fixture();f.state.count=3;const s=(await f.api.dispatch('scan')).result;await f.api.dispatch('ensureRecords',{schemaVersion:1,requestId:'rows',snapshotId:s.snapshotId,sections:[{sectionId:'education',count:1}]});assert.equal((await done(f)).status,'complete');assert.equal(f.state.count,3);assert.equal(f.state.adds,0);});
test('uncertain add stops without blind retry',async()=>{const f=fixture();f.adapter.addRecord=async()=>{f.state.adds++;};const s=(await f.api.dispatch('scan')).result;await f.api.dispatch('ensureRecords',{schemaVersion:1,requestId:'rows',snapshotId:s.snapshotId,sections:[{sectionId:'education',count:3}]});assert.equal((await done(f)).error.code,'ADD_UNCERTAIN');assert.equal(f.state.adds,1);});
test('website validation and unplanned side effects are not success',async()=>{const f=fixture();f.state.errors=['invalid'];await f.api.dispatch('execute',await plan(f));assert.equal((await done(f)).error.code,'WEBSITE_VALIDATION');const g=fixture();g.adapter.write=async()=>{g.state.value='测试答案';g.state.other='side effect';};await g.api.dispatch('execute',await plan(g));assert.equal((await done(g)).error.code,'UNPLANNED_CHANGE');});
test('verify is read only and detects changed answer',async()=>{const f=fixture();await f.api.dispatch('execute',await plan(f));await done(f);assert.equal((await f.api.dispatch('verify',{requestId:'r1'})).result.complete,true);f.state.value='manual';assert.equal((await f.api.dispatch('verify',{requestId:'r1'})).result.complete,false);assert.equal(f.state.writes,1);});
test('unsupported field features cannot enter the action path',async()=>{const f=fixture();for(const m of ['upload','runScript','click','deleteRecord'])assert.equal((await f.api.dispatch(m)).error.code,'UNSUPPORTED_METHOD');assert.equal(f.state.writes,0);});

test('draft save is explicitly requested and deduplicated; unsupported site rejects',async()=>{const f=fixture();let saves=0;f.adapter.saveDraft=async()=>saves++;const s=(await f.api.dispatch('scan')).result;const p={schemaVersion:1,requestId:'save',snapshotId:s.snapshotId};await f.api.dispatch('saveDraft',p);assert.equal((await done(f)).saved,true);await f.api.dispatch('saveDraft',p);assert.equal(saves,1);const g=fixture(),gs=(await g.api.dispatch('scan')).result;assert.equal((await g.api.dispatch('saveDraft',{...p,snapshotId:gs.snapshotId})).error.code,'UNSUPPORTED');});

test('checkbox accepts booleans and does not treat existing false as permission to overwrite',async()=>{
 const f=fixture();f.state.value=false;const original=f.adapter.fields;
 f.adapter.fields=()=>original().map(x=>x.id==='field'?{...x,kind:'checkbox'}:x);
 const p=await plan(f);p.assignments[0].value='true';assert.equal((await f.api.dispatch('execute',p)).error.code,'INVALID_VALUE');
 p.assignments[0].value=true;assert.equal((await f.api.dispatch('execute',p)).error.code,'EXISTING_VALUE');
 p.assignments[0].overwrite='ifUnchanged';await f.api.dispatch('execute',p);assert.equal((await done(f)).status,'complete');assert.equal(f.state.value,true);
});
test('readOptions is scoped to a fresh field and never writes',async()=>{
 const f=fixture();f.adapter.readOptions=async()=>({state:'visible-options',items:['甲','乙'],complete:false});const p=await plan(f);
 assert.deepEqual((await f.api.dispatch('readOptions',{snapshotId:p.snapshotId,fieldId:'field'})).result.items,['甲','乙']);
 f.state.value='user edit';assert.equal((await f.api.dispatch('readOptions',{snapshotId:p.snapshotId,fieldId:'field'})).error.code,'VALUE_CHANGED');assert.equal(f.state.writes,0);
});
test('option reading locks concurrent commands and releases lock after failure',async()=>{
 const f=fixture();let rejectRead;f.adapter.readOptions=()=>new Promise((_,reject)=>rejectRead=reject);const p=await plan(f);
 const reading=f.api.dispatch('readOptions',{snapshotId:p.snapshotId,fieldId:'field'});
 assert.equal((await f.api.dispatch('scan')).error.code,'BUSY');assert.equal((await f.api.dispatch('execute',p)).error.code,'BUSY');
 rejectRead(Error('menu timeout'));assert.equal((await reading).ok,false);assert.equal((await f.api.dispatch('scan')).ok,true);
});
test('date format inspection is scoped and read only, and protects edits after scan',async()=>{
 const f=fixture();f.adapter.readDateFormat=async()=>({kind:'month',format:'YYYY-MM',writesPerformed:0});const p=await plan(f);
 assert.equal((await f.api.dispatch('readDateFormat',{snapshotId:p.snapshotId,fieldId:'field'})).result.kind,'month');
 assert.equal(f.state.writes,0);f.state.value='manual edit';
 assert.equal((await f.api.dispatch('readDateFormat',{snapshotId:p.snapshotId,fieldId:'field'})).error.code,'VALUE_CHANGED');
});
test('autocomplete requires committed selection even when its displayed text already matches',async()=>{
 const f=fixture();f.adapter.needsCommit=()=>true;f.state.value='chosen';const p=await plan(f,{assignments:[{fieldId:'field',value:'chosen'}]});
 await f.api.dispatch('execute',p);await done(f);assert.equal(f.state.writes,1);
});
test('attachment upload is snapshot-scoped, uses original bytes and deduplicates requests',async()=>{
 const f=fixture(),input={};let uploads=0,names=[];
 f.adapter.attachments=()=>[{attachmentId:'resume',label:'简历附件',fileNames:[...names],input}];
 f.adapter.uploadAttachment=async(a,file)=>{uploads++;assert.equal(file.base64,'ZmFrZQ==');names=[file.fileName];return {status:'attachment-uploaded',fileName:file.fileName};};
 const s=(await f.api.dispatch('scan')).result;
 assert(!JSON.stringify(s).includes('"input"'));assert.equal(s.capabilities.upload,true);
 const p={schemaVersion:1,requestId:'upload',snapshotId:s.snapshotId,attachmentId:'resume',fileName:'fictional.pdf',mimeType:'application/pdf',base64:'ZmFrZQ=='};
 assert.equal((await f.api.dispatch('uploadAttachment',{...p,attachmentId:'wrong'})).error.code,'UNKNOWN_FIELD');
 assert.equal((await f.api.dispatch('uploadAttachment',{...p,fileName:'../file.pdf'})).error.code,'INVALID_REQUEST');
 await f.api.dispatch('uploadAttachment',p);assert.equal((await done(f)).status,'complete');
 await f.api.dispatch('uploadAttachment',p);assert.equal(uploads,1);
 const fresh=(await f.api.dispatch('scan')).result;names=['manual.pdf'];
 await f.api.dispatch('uploadAttachment',{...p,requestId:'changed',snapshotId:fresh.snapshotId});assert.equal((await done(f)).error.code,'VALUE_CHANGED');assert.equal(uploads,1);
});
test('adapter rejection is checked before any assignment is written',async()=>{
 const f=fixture();f.adapter.validate=(field,value)=>{if(value==='bad option')throw Error('not an option');};const p=await plan(f);
 p.assignments.push({fieldId:'other',value:'bad option',overwrite:'ifUnchanged'});assert.equal((await f.api.dispatch('execute',p)).ok,false);assert.equal(f.state.writes,0);
});
test('side effects never count as preserved fields and timings include preflight separately',async()=>{
 const f=fixture();f.adapter.write=async()=>{f.state.value='测试答案';f.state.other='side effect';};const p=await plan(f);await f.api.dispatch('execute',p);const j=await done(f);
 assert.equal(j.error.code,'UNPLANNED_CHANGE');assert.equal(j.preserved,0);assert.equal(j.totalMs,j.elapsedMs+j.preflightMs);assert.equal(typeof (await f.api.dispatch('scan')).result.scanElapsedMs,'number');
});

test('optional dates can be restored to blank while required dates cannot',async()=>{
 const f=fixture();f.state.value='2024-08-16';const original=f.adapter.fields;let required=false;
 f.adapter.fields=()=>original().map(x=>x.id==='field'?{...x,kind:'date',required}:x);
 const p=await plan(f);p.assignments=[{fieldId:'field',value:'',overwrite:'ifUnchanged'}];await f.api.dispatch('execute',p);assert.equal((await done(f)).status,'complete');assert.equal(f.state.value,'');
 required=true;const p2=await plan(f,{requestId:'required-date'});p2.assignments=[{fieldId:'field',value:''}];assert.equal((await f.api.dispatch('execute',p2)).error.code,'MISSING_VALUE');
});
