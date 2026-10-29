const test=require('node:test'),assert=require('node:assert/strict');
const {run}=require('./material-runner.js');
function fixture(manual=false,moved=false){
 const url='https://fictional.example/apply',writes=[],calls=[];
 let fields=[{fieldId:'f1',label:'姓名',kind:'text',sectionId:'s',recordId:'r',currentValue:manual?'本人后来编辑':'旧值'},{fieldId:'f2',label:'年份',kind:'text',sectionId:'s',recordId:'r',currentValue:moved?'2026':'2025'},{fieldId:'f3',label:'独立字段',kind:'text',sectionId:'s',recordId:'',currentValue:'原值'}],job;
 const client={async call(method,p){calls.push(method);if(method==='scan')return {ok:true,result:{page:{url},snapshotId:'s1',capabilities:{correctionRetry:1},sections:[],fields:structuredClone(fields),validation:[]}};
 if(method==='validate')return {ok:true,result:{valid:true}};
 if(method==='execute'){writes.push(...p.assignments);for(const a of p.assignments){assert.equal(a.expectedCurrentValue,fields.find(f=>f.fieldId===a.fieldId).currentValue);fields.find(f=>f.fieldId===a.fieldId).currentValue=a.value;}job={status:'complete',results:p.assignments.map(a=>({fieldId:a.fieldId,status:'filled'}))};return {ok:true,result:{accepted:true}};}
 if(method==='status')return {ok:true,result:job};throw Error('Unexpected '+method);},async reloadAndScan(){throw Error('must preserve page');}};
 const materials={url,rows:[],corrections:[{issue_id:'issue1',website_id:'name',field_id:'f1',label:'姓名',section_id:'s',record_id:'r',record_fields:[{field_id:'f1',label:'姓名',value:'旧值'},{field_id:'f2',label:'年份',value:'2025'}],expected_current:'旧值',value:'更正',source_ref:{field_id:'name',entry_id:'person'}},{issue_id:'issue2',website_id:'x',field_id:'f3',label:'独立字段',section_id:'s',record_id:'',record_fields:[],expected_current:'原值',value:'新值',source_ref:{field_id:'x'}}]};
 return {go:()=>run(client,materials,async()=>{}),writes,calls,fields,client};
}
test('correction writes only confirmed fields with an old-value guard and never reloads/uploads/adds records',async()=>{const f=fixture(),r=await f.go();assert.equal(r.verified,2);assert.deepEqual(f.writes.map(a=>a.fieldId),['f1','f3']);assert(f.calls.every(x=>['scan','validate','execute','status'].includes(x)));assert.equal(r.saved,false);});
test('manual change pauses only its field, independent correction still executes',async()=>{const f=fixture(true),r=await f.go();assert.deepEqual(f.writes.map(a=>a.fieldId),['f3']);assert.equal(f.fields[0].currentValue,'本人后来编辑');assert.equal(r.correction_results[0].state,'conflict');});
test('changed record identity blocks ordinal reuse',async()=>{const f=fixture(false,true),r=await f.go();assert.deepEqual(f.writes.map(a=>a.fieldId),['f3']);assert.equal(r.verified,1);});
test('unknown execution outcome stops the batch and waits for a terminal acknowledgement',async()=>{
 const f=fixture(),original=f.client.call;let cancelled=false,attempts=0;
 f.client.call=async(method,args)=>{if(method==='execute'){attempts++;throw Error('reply lost');}if(method==='cancel'){cancelled=true;return {ok:true,result:{}};}if(method==='status')return {ok:true,result:{status:'cancelled'}};return original(method,args);};
 await assert.rejects(f.go(),/reply lost/);assert.equal(attempts,1);assert.equal(cancelled,true);
});
test('lost stop acknowledgement is explicit and cannot start the next correction',async()=>{
 const f=fixture(),original=f.client.call;let attempts=0;
 f.client.call=async(method,args)=>{if(method==='execute'){attempts++;throw Error('reply lost');}if(method==='cancel')return {ok:true,result:{}};if(method==='status')throw Error('disconnected');return original(method,args);};
 await assert.rejects(f.go(),error=>error.stopUnconfirmed===true);assert.equal(attempts,1);
});
