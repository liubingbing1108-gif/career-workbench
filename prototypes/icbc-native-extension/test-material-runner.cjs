const assert=require('node:assert/strict');
const {compile,run,compareSaved,identify}=require('./material-runner.js');
const url='https://example.com/apply';
const field=(id,value='')=>({fieldId:id,label:({name:"姓名",email:"邮箱",country:"国籍"}[id]||id),kind:'text',sectionId:'basic',recordId:'',required:false,disabled:false,currentValue:value});
const material={url,title:'虚构岗位',attachment:{name:'fictional.pdf'},rows:[{website_id:'name',label:'姓名',value:'虚构姓名'},{website_id:'email',label:'邮箱',value:'fictional@example.invalid'}]};
let passes=0;
async function check(name,fn){await fn();passes++;console.log('PASS '+name);}
function fake(fail=false,manual=false){
 let snapshot={page:{url},snapshotId:'s1',sections:[],fields:[field('name'),field('email')]},job,execs=[];
 return {execs,async call(method,payload){
  if(method==='scan')return {ok:true,result:structuredClone(snapshot)};
  if(method==='validate')return {ok:true,result:{valid:true}};
  if(method==='execute'){
   execs.push(payload);
   if(fail&&execs.length===1){job={status:'failed',results:[],error:{code:'ACTION_FAILED',message:'虚构控件失败'}};if(manual)snapshot.fields[1].currentValue='人工新值';}
   else{for(const a of payload.assignments)snapshot.fields.find(f=>f.fieldId===a.fieldId).currentValue=a.value;job={status:'complete',results:payload.assignments.map(a=>({fieldId:a.fieldId,status:'filled'}))};}
   return {ok:true,result:{accepted:true}};
  }
  if(method==='status')return {ok:true,result:job};
  if(method==='verify')return job.status==='complete'?{ok:true,result:{complete:true,checks:job.results.map(r=>({fieldId:r.fieldId,passed:true}))}}:{ok:false,error:{message:'没有该已完成的填写任务'}};
  throw Error('Unexpected method '+method);
 }};
}
(async()=>{
 await check('binds concrete record fields and leaves attachments for handoff',()=>{
  const snapshot={page:{url},sections:[{sectionId:'education',count:2}],fields:[field('education[0].school'),field('education[1].school')]};
  const result=compile({url,attachment:material.attachment,rows:[{website_id:'education',label:'教育',records:[{values:[{website_id:'education[].school',label:'学校',value:'虚构学校'}]}]}]},snapshot);
  assert.equal(result.assignments[0].fieldId,'education[0].school');assert.equal(result.assignments.length,1);assert(result.issues.some(x=>x.includes('多出 1')));assert(result.issues.some(x=>x.includes('附件')));
 });
 await check('wrong page and ambiguous field cannot be written',()=>{
  assert.throws(()=>compile(material,{page:{url:'https://wrong.example'},fields:[],sections:[]}));
  const result=compile(material,{page:{url},fields:[field('name'),field('name')],sections:[]});assert.equal(result.assignments.length,0);
 });
 await check('flat generic IDs resolve within exact section and record and reject ambiguity',()=>{
  const rows=[{website_id:'education',label:'教育',records:[{values:[{website_id:'flat-1',label:'学校',value:'甲学校'}]},{values:[{website_id:'flat-1',label:'学校',value:'乙学校'}]}]}];
  const fields=[{...field('flat-1'),label:'学校',sectionId:'education',recordId:'row-a'},
                {...field('flat-2'),label:'学校',sectionId:'education',recordId:'row-b'},
                {...field('other'),label:'学校',sectionId:'work',recordId:'row-a'}];
  const s={page:{url},sections:[{sectionId:'education',count:2}],fields};
  assert.deepEqual(compile({url,rows},s).assignments.map(a=>a.fieldId),['flat-1','flat-2']);
  fields.push({...fields[1],fieldId:'duplicate'});
  const r=compile({url,rows},s);assert.equal(r.assignments.length,1);assert(r.issues.some(i=>i.includes('没有唯一')));
 });
 await check('uses validate execute verify protocol and never submits',async()=>{
  const client=fake(),reports=[];const result=await run(client,material,r=>reports.push(r));assert.equal(result.filled,2);assert.equal(result.verified,2);assert.equal(reports.at(-1).status,'needs_attention');assert.equal(client.execs[0].assignments[0].overwrite,'ifUnchanged');
 });
 await check('failed independent input does not prevent remaining input',async()=>{
  const client=fake(true);const result=await run(client,material,async()=>{});assert.equal(client.execs.length,2);assert.deepEqual(client.execs[1].assignments.map(a=>a.fieldId),['email']);assert.equal(result.verified,1);
 });
 await check('rescan does not overwrite a manual change',async()=>{
  const client=fake(true,true);const result=await run(client,material,async()=>{});assert.equal(client.execs.length,1);assert(result.issues.some(x=>x.includes('扫描后已被修改')));
 });
 await check('partial failed plan preserves counts and independently checks all remaining DOM values',async()=>{
  let snapshot={page:{url},snapshotId:'s1',sections:[],fields:[field('name'),field('email'),field('country')]},job;
  const executed=[],verifiedRequests=[],reports=[];
  const client={async call(method,payload){
   if(method==='scan')return {ok:true,result:structuredClone(snapshot)};
   if(method==='validate')return {ok:true,result:{valid:true}};
   if(method==='execute'){
    executed.push(payload);
    const accepted=executed.length===1?payload.assignments.slice(0,1):payload.assignments;
    for(const a of accepted)snapshot.fields.find(f=>f.fieldId===a.fieldId).currentValue=a.value;
    job={status:executed.length===1?'failed':'complete',results:accepted.map(a=>({fieldId:a.fieldId,status:'filled'})),error:{code:'ACTION_FAILED',message:'虚构下拉选项不匹配'}};
    return {ok:true,result:{accepted:true}};
   }
   if(method==='status')return {ok:true,result:job};
   if(method==='verify'){
    verifiedRequests.push(payload.requestId);
    assert.equal(job.status,'complete','failed plans cannot be verified');
    return {ok:true,result:{complete:true,checks:job.results.map(r=>({fieldId:r.fieldId,passed:true}))}};
   }
   throw Error('Unexpected method '+method);
  }};
  const result=await run(client,{url,rows:[...material.rows,{website_id:'country',label:'国籍',value:'虚构国籍'}]},r=>reports.push(structuredClone(r)));
  assert.deepEqual(executed[1].assignments.map(a=>a.fieldId),['country']);
  assert.deepEqual(verifiedRequests,[executed[1].requestId]);
  assert.equal(result.filled,2);assert.equal(result.verified,2);
  assert(result.issues.includes('虚构下拉选项不匹配'));
  assert.equal(reports.find(r=>r.filled===1).verified,0);
 });
 await check('protocol verification error is retained while a fresh DOM comparison still runs',async()=>{
  const base=fake(),reports=[];
  const client={call(method,payload){return method==='verify'?{ok:false,error:{message:'页面已切换'}}:base.call(method,payload);}};
  const result=await run(client,material,r=>reports.push(structuredClone(r)));
  assert.equal(base.execs.length,1);assert.equal(result.filled,2);assert.equal(result.verified,2);
  assert(result.issues.some(x=>x.includes('页面已切换')));assert.equal(reports.at(-1).filled,2);
 });
 await check('confirmed original attachment and standalone draft save use the same executor protocol',async()=>{
  let snapshot={page:{url},snapshotId:'s1',sections:[],fields:[field('name'),field('email')],capabilities:{upload:true,saveDraft:true},attachments:[{attachmentId:'resume',label:'简历附件',fileNames:[]}]},job;
  const calls=[],reports=[];
  const client={async reloadAndScan(){return structuredClone(snapshot);},async call(method,p){calls.push(method);
   if(method==='scan')return {ok:true,result:structuredClone(snapshot)};
   if(method==='validate')return {ok:true,result:{valid:true}};
   if(method==='execute'){for(const a of p.assignments)snapshot.fields.find(f=>f.fieldId===a.fieldId).currentValue=a.value;job={status:'complete',results:p.assignments.map(a=>({fieldId:a.fieldId,status:'filled'}))};return {ok:true,result:{accepted:true}};}
   if(method==='verify')return {ok:true,result:{complete:true,checks:job.results.map(r=>({passed:true}))}};
   if(method==='status')return {ok:true,result:job};
   if(method==='uploadAttachment'){assert.equal(p.base64,'ZmFrZQ==');assert.equal(p.fileName,'fictional.pdf');snapshot.attachments[0].fileNames=[p.fileName];job={status:'complete',results:[]};return {ok:true,result:{accepted:true}};}
   if(method==='saveDraft'){job={status:'complete',saved:true,results:[]};return {ok:true,result:{accepted:true}};}
   throw Error('unexpected '+method);
  }};
  const result=await run(client,{...material,attachment:{id:'selected-file',name:'fictional.pdf',base64:'ZmFrZQ==',mime_type:'application/pdf'}},r=>reports.push(r));
  assert.equal(result.verified,2);assert.equal(result.saved,true);assert.equal(result.attachment_verified,true);
  assert(!result.issues.some(i=>i.startsWith('简历附件')));assert(calls.indexOf('uploadAttachment')<calls.indexOf('saveDraft'));assert(!calls.includes('submit'));
  assert.equal(reports.at(-1).saved,true);
 });
 await check('saving cannot leave a stale successful verification count',async()=>{
  const base=fake();let afterSave=false;
  const client={async call(method,p){
   if(method==='saveDraft'){afterSave=true;return {ok:true,result:{accepted:true}};}
   if(method==='status'&&afterSave)return {ok:true,result:{status:'complete',saved:true,results:[]}};
   const r=await base.call(method,p);
   if(method==='scan'){r.result.capabilities={saveDraft:true};if(afterSave)r.result.fields[0].currentValue='';}
   return r;
  }};
  const result=await run(client,material,async()=>{});assert.equal(result.saved,false);assert.equal(result.verified,1);assert(result.issues.some(i=>i.includes('官网没有保留')));
 });
 await check('saved values are compared by section record and label after IDs change',()=>{
  const before={sections:[{sectionId:'old',label:'教育经历'}],fields:[{...field('a','学校甲'),label:'学校',sectionId:'old',recordId:'old-row-1'},{...field('b','学校乙'),label:'学校',sectionId:'old',recordId:'old-row-2'}]};
  const expected=before.fields.map(f=>({identity:identify(before,f),value:f.currentValue,display:f.label}));
  const after={sections:[{sectionId:'new',label:'教育经历'}],fields:before.fields.map((f,i)=>({...f,fieldId:'new-'+i,sectionId:'new',recordId:'new-row-'+i}))};
  assert(compareSaved(expected,after).every(c=>c.passed));
  after.fields[1].currentValue='';assert.deepEqual(compareSaved(expected,after).map(c=>c.passed),[true,false]);
 });
 await check('draft acknowledgement cannot hide content lost after reopening',async()=>{
  const base=fake();let saved=false;
  const client={async reloadAndScan(){const r=await base.call('scan');r.result.fields[0].currentValue='';return r.result;},async call(method,p){
   if(method==='saveDraft'){saved=true;return {ok:true,result:{accepted:true}};}
   if(method==='status'&&saved)return {ok:true,result:{status:'complete',saved:true,results:[]}};
   const r=await base.call(method,p);if(method==='scan')r.result.capabilities={saveDraft:true};return r;
  }};
  const result=await run(client,{...material,attachment:null},async()=>{});
  assert.equal(result.save_acknowledged,true);assert.equal(result.persistence_verified,true);assert.equal(result.persisted,1);assert.equal(result.expected_count,2);assert.equal(result.saved,false);
  assert(result.issues.some(i=>i.includes('重新打开官网后内容为空或不同')));
 });
 console.log(JSON.stringify({passed:passes}));
})().catch(e=>{console.error(e);process.exitCode=1;});
