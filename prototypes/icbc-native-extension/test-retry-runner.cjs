const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function fixture(stall=false,retry=false){
 let clock=0,statusCalls=0,cancelled=false,job,execs=0;
 const url='https://fictional.example/apply',fields=['a','b','c','d'].map(id=>({fieldId:id,label:id,kind:'text',sectionId:'basic',recordId:'',currentValue:retry?(id==='a'?'v-a':id==='b'?'manual':''):''}));
 const context=vm.createContext({module:{exports:{}},Date:{now:()=>clock},crypto:{randomUUID:()=>String(execs)},setTimeout:fn=>{clock+=60000;setImmediate(fn);}});
 vm.runInContext(fs.readFileSync(__dirname+'/material-runner.js','utf8'),context);
 const client={async call(method,p){
  if(method==='scan')return {ok:true,result:{page:{url},snapshotId:'snapshot',sections:[],fields:structuredClone(fields),capabilities:{}}};
  if(method==='validate')return {ok:true,result:{valid:true}};
  if(method==='execute'){execs++;job={status:'running',results:[],assignments:p.assignments};return {ok:true,result:{accepted:true}};}
  if(method==='status'){
   statusCalls++;
   if(!stall&&job.results.length<job.assignments.length){const a=job.assignments[job.results.length];fields.find(f=>f.fieldId===a.fieldId).currentValue=a.value;job.results.push({fieldId:a.fieldId,status:'filled'});}
   job.currentField={label:'field',index:job.results.length,total:job.assignments.length};
   if(job.results.length===job.assignments.length)job.status='complete';
   return {ok:true,result:job};
  }
  if(method==='verify')return {ok:true,result:{complete:true,checks:job.results.map(()=>({passed:true}))}};
  if(method==='cancel'){cancelled=true;return {ok:true,result:{stopping:true}};}
  throw Error(method);
 }};
 const reports=[],materials={url,retry,preserve_unsaved_page:true,rows:fields.map(f=>({website_id:f.fieldId,label:f.label,value:'v-'+f.fieldId}))};
 return {run:()=>context.module.exports.run(client,materials,p=>reports.push(p)),reports,fields,get cancelled(){return cancelled;},get job(){return job;}};
}
test('a progressing batch may exceed 90 seconds and reports partial writes',async()=>{const f=fixture();const r=await f.run();assert.equal(r.filled,4);assert.equal(r.verified,4);assert.equal(f.cancelled,false);assert(f.reports.some(p=>p.filled===2));});
test('a stalled field is cancelled with a recoverable retry message',async()=>{const f=fixture(true);await assert.rejects(f.run(),/长时间无进展.*可重试/);assert(f.cancelled);});
test('retry only writes missing values and preserves different manual content',async()=>{const f=fixture(false,true);const r=await f.run();assert.deepEqual(Array.from(f.job.assignments,a=>a.fieldId),['c','d']);assert.equal(f.fields[1].currentValue,'manual');assert.equal(r.verified,3);assert(r.issues.some(s=>s.includes('官网已有不同内容')));});

test('matching read-only fields are verified without being queued as writes',()=>{const {compile}=require('./material-runner.js');const url='https://fictional.example';const result=compile({url,rows:[{website_id:'degree',label:'最高学历',value:'硕士'}]},{page:{url},fields:[{fieldId:'degree',label:'最高学历',kind:'select',disabled:true,currentValue:'硕士'}],sections:[]});assert.equal(result.assignments.length,0);assert.equal(result.issues.length,0);assert.equal(result.readOnlyChecks.length,1);});

test('saved reordered records match whole rows, not their ordinal positions',()=>{
 const {compareSaved,compile,inspectMaterials}=require('./material-runner.js'),url='https://fictional.example';
 const fields=[['row-b','company','乙'],['row-b','year','2024'],['row-a','company','甲'],['row-a','year','2025']].map(([recordId,label,currentValue],i)=>({fieldId:'f'+i,sectionId:'s',recordId,label,currentValue,context:{componentIndex:0}}));
 const snapshot={page:{url},sections:[{sectionId:'s',label:'实习'}],fields};
 const expected=[['甲','2025'],['乙','2024']].flatMap((v,record)=>['company','year'].map((label,i)=>({identity:{section:'实习',record,label,component:0},value:v[i],display:label})));
 assert(compareSaved(expected,snapshot).every(c=>c.passed));
 const rows=[{website_id:'s',label:'实习',records:[['甲','2025'],['乙','2024']].map(v=>({values:['company','year'].map((label,i)=>({website_id:label,label,value:v[i]}))}))}];
 assert.deepEqual(compile({url,rows},snapshot).assignments.map(a=>a.fieldId),['f2','f3','f0','f1']);
 assert(inspectMaterials({url,rows},snapshot).checks.every(c=>c.passed));
 // Values present in the wrong combinations must never pass by cross-row lookup.
 fields[1].currentValue='2025';fields[3].currentValue='2024';assert(compareSaved(expected,snapshot).some(c=>!c.passed));assert(inspectMaterials({url,rows},snapshot).checks.some(c=>!c.passed));
});
test('auto-parsing resume upload precedes confirmed fields and unsaved forms are never reloaded',async()=>{
 const {run}=require('./material-runner.js'),url='https://fictional.example/apply',calls=[];let value='',uploaded=false,job;
 const client={async call(method,p){calls.push(method);
  if(method==='scan')return {ok:true,result:{page:{url},snapshotId:'s',sections:[],capabilities:{upload:true,saveDraft:false},attachments:[{attachmentId:'file',label:'上传简历',autoFill:true,fileNames:uploaded?['fictional.pdf']:[]}],fields:[{fieldId:'role',label:'岗位',kind:'text',sectionId:'basic',recordId:'',currentValue:value}]}};
  if(method==='uploadAttachment'){uploaded=true;value='网站解析旧值';job={status:'complete',results:[]};return {ok:true,result:{accepted:true}};}
  if(method==='validate')return {ok:true,result:{valid:true}};
  if(method==='execute'){value=p.assignments[0].value;job={status:'complete',results:[{fieldId:'role',status:'filled'}]};return {ok:true,result:{accepted:true}};}
  if(method==='status')return {ok:true,result:job};
  if(method==='verify')return {ok:true,result:{complete:true,checks:[{passed:true}]}};
  throw Error(method);
 },async reloadAndScan(){throw Error('must never reload a form without confirmed save');}};
 const result=await run(client,{url,attachment:{id:'f',name:'fictional.pdf',base64:'eA=='},rows:[{website_id:'role',label:'岗位',value:'确认岗位'}]},async()=>{});
 assert.equal(value,'确认岗位');assert(calls.indexOf('uploadAttachment')<calls.indexOf('execute'));assert.equal(calls.filter(m=>m==='uploadAttachment').length,1);assert.equal(result.attachment_verified,true);assert.equal(result.verified,1);assert.equal(result.persistence_verified,false);
});
test('scalar IDs cannot cross repeated labels after DOM renumbering',()=>{
 const {compile}=require('./material-runner.js'),url='https://fictional.example/apply';
 const snapshot={page:{url},sections:[{sectionId:'personal',label:'个人信息'}],fields:[{fieldId:'f7',label:'手机号码',kind:'select',sectionId:'personal',currentValue:'+99'},{fieldId:'f8',label:'手机号码',kind:'text',sectionId:'personal',currentValue:'111'}]};
 const rows=[{website_id:'f8',label:'手机号码',value:'+99',target_kind:'select',target_section:'个人信息'},{website_id:'f9',label:'手机号码',value:'222',target_kind:'text',target_section:'个人信息'}];
 assert.deepEqual(compile({url,rows},snapshot).assignments.map(a=>[a.fieldId,a.value]),[['f7','+99'],['f8','222']]);
 assert.equal(compile({url,rows:rows.map(({target_kind,target_section,...r})=>r)},snapshot).assignments.length,0);
});
