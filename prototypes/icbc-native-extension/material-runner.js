/* Upper-layer material handoff. All browser actions use the existing protocol. */
(() => {
 'use strict';
 const normal=id=>id.replace(/\[\d+\]/g,'[]');
 const unwrap=r=>{if(!r.ok)throw Error(r.error?.message||'执行器失败');return r.result;};
 function compile(materials,snapshot){
  if(snapshot.page.url!==materials.url)throw Error('官网链接与确认的材料不一致');
  const assignments=[],issues=[];
  const add=(id,value,source,label,strictLabel=false)=>{
   if(value===''||value===null||value===undefined)return;
   let matches=snapshot.fields.filter(f=>f.fieldId===id||(id.includes('[]')&&normal(f.fieldId)===id));
   if(strictLabel&&matches.length===1&&matches[0].label!==label)matches=[];
   if(!matches.length)matches=snapshot.fields.filter(f=>f.label===label);
   if(matches.length!==1){issues.push(label+'：当前控件未接通，需本人处理');return;}
   const field=matches[0];
   if(field.disabled||field.kind==='unsupported'){issues.push(label+'：'+(field.blockedReason||'官网当前不可编辑'));return;}
   assignments.push({fieldId:field.fieldId,value,overwrite:'ifUnchanged',sourceRef:JSON.stringify(source||{})});
  };
  for(const row of materials.rows){
   if(row.follow_up)issues.push(row.follow_up);
   if(row.records){
    const section=findSection(snapshot,row);
    if(section?.count>row.records.length)issues.push(row.label+'：官网多出 '+(section.count-row.records.length)+' 条既有记录，需本人检查/删除');
    row.records.forEach((record,index)=>record.values.forEach(v=>{
     let candidates=snapshot.fields.filter(f=>normal(f.fieldId)===v.website_id&&f.fieldId.includes('['+index+']'));
     // Generic adapters return stable flat IDs plus record IDs. Resolve a child
     // only within the selected record and section, with one exact field label.
     if(!candidates.length){
      const members=snapshot.fields.filter(f=>f.sectionId===section?.sectionId);
      const records=[...new Set(members.map(f=>f.recordId).filter(Boolean))];
      candidates=members.filter(f=>f.recordId===records[index]&&f.label===v.label);
     }
     if(!v.value)return;
     if(candidates.length!==1){issues.push(row.label+'第 '+(index+1)+' 条 '+v.label+'：当前没有唯一对应控件');return;}
     add(candidates[0].fieldId,v.value,v.source_ref,row.label+' '+v.label);
    }));
   }else add(row.website_id,row.value,row.source_ref,row.label,true);
  }
  if(materials.attachment&&!snapshot.capabilities?.upload)issues.push('简历附件：请上传已选择的原文件“'+materials.attachment.name+'”；当前控件没有已接通的附件驱动');
  return {assignments,issues};
 }
 const findSection=(snapshot,row)=>snapshot.sections.find(s=>s.sectionId===row.website_id&&s.label===row.label)||snapshot.sections.filter(s=>s.label===row.label).length===1&&snapshot.sections.find(s=>s.label===row.label)||snapshot.sections.find(s=>s.sectionId===row.website_id&&!s.label);
 function identify(snapshot,f){
  const members=snapshot.fields.filter(x=>x.sectionId===f.sectionId),records=[...new Set(members.map(x=>x.recordId).filter(Boolean))];
  return {label:f.label,section:snapshot.sections.find(s=>s.sectionId===f.sectionId)?.label||f.context?.section||'',record:f.recordId?records.indexOf(f.recordId):-1,component:f.context?.componentIndex??null};
 }
 function compareSaved(expected,snapshot){
  return expected.map(e=>{const matches=snapshot.fields.filter(f=>JSON.stringify(identify(snapshot,f))===JSON.stringify(e.identity));return {label:e.display,passed:matches.length===1&&JSON.stringify(matches[0].currentValue)===JSON.stringify(e.value)};});
 }
 async function readDates(client,snapshot){
  // New education/internship rows have empty date controls; inspect them too.
  const tried=new Set();
  while(true){const field=snapshot.fields.find(f=>!f.disabled&&f.kind==='unsupported'&&f.context?.driver==='phoenix-calendar'&&!tried.has(f.fieldId));if(!field)break;tried.add(field.fieldId);
   await client.call('readDateFormat',{snapshotId:snapshot.snapshotId,fieldId:field.fieldId});snapshot=unwrap(await client.call('scan'));
  }return snapshot;
 }
 async function run(client,materials,report,shouldStop=()=>false){
  let filled=0,verified=0,issues=[],saved=false,save_acknowledged=false,persistence_verified=false,persisted=0,attachment_verified=false,phase='connecting';
  const send=report;report=progress=>send({phase,...progress});
  const call=async(method,payload={})=>unwrap(await client.call(method,payload));
  const wait=async requestId=>{
   const start=Date.now();
   while(Date.now()-start<90000){
    if(shouldStop()){await call('cancel');throw Error('已停止后续填写，请检查官网保留内容');}
    const job=await call('status',{requestId});if(!job)throw Error('执行器任务已丢失，请重新扫描');
    if(job.status!=='running')return job;
    await report({status:'running',filled,verified,issues,message:job.currentField?'正在填写：'+job.currentField.label+'（'+job.currentField.index+'/'+job.currentField.total+'）':job.progress||({connecting:'正在读取官网表单',filling:'正在填写资料',saving:'正在处理附件与保存',verifying:'正在回读检查'}[phase]||'正在处理本次申请')});
    await new Promise(r=>setTimeout(r,200));
   }
   await call('cancel');throw Error('执行超时，已停止后续动作');
  };
  let snapshot=await call('scan');if(snapshot.page.url!==materials.url)throw Error('招聘页面已切换');
  const baseline=new Map(snapshot.fields.map(f=>[f.fieldId,JSON.stringify(f.currentValue)]));
  const rememberNew=()=>{for(const f of snapshot.fields)if(!baseline.has(f.fieldId))baseline.set(f.fieldId,JSON.stringify(f.currentValue));};
  // Only create record counts selected in the confirmed material, using fresh scans.
  for(const row of materials.rows.filter(r=>r.records?.length)){
   if(shouldStop())throw Error('已停止');
   const section=findSection(snapshot,row);
   if(!section||section.count>=row.records.length)continue;
   if(!section.canAdd){issues.push(row.label+'无法自动新增');continue;}
   const requestId=crypto.randomUUID();
   try{
    await call('ensureRecords',{schemaVersion:1,requestId,snapshotId:snapshot.snapshotId,sections:[{sectionId:section.sectionId,count:row.records.length}]});
    const job=await wait(requestId);if(job.status!=='complete')issues.push(row.label+'新增未完成：'+(job.error?.message||job.status));
    snapshot=await call('scan');rememberNew();
   }catch(e){issues.push(row.label+'新增遇到阻碍：'+e.message);snapshot=await call('scan');rememberNew();}
  }
  snapshot=await readDates(client,snapshot);
  phase='filling';
  const built=compile(materials,snapshot);issues.push(...built.issues);
  const expected=built.assignments.map(a=>{const f=snapshot.fields.find(f=>f.fieldId===a.fieldId),identity=identify(snapshot,f);return {value:a.value,identity,display:[identity.section,identity.record>=0?'第 '+(identity.record+1)+' 条':'',identity.label].filter(Boolean).join(' · ')};});
  let pending=built.assignments;
  while(pending.length){
   if(shouldStop())throw Error('已停止后续填写');
   pending=pending.filter(a=>{const f=snapshot.fields.find(f=>f.fieldId===a.fieldId);if(!f||JSON.stringify(f.currentValue)!==baseline.get(a.fieldId)){issues.push((f?.label||a.fieldId)+'：扫描后已被修改，保留官网内容');return false;}return true;});
   if(!pending.length)break;
   const requestId=crypto.randomUUID(),plan={schemaVersion:1,requestId,snapshotId:snapshot.snapshotId,assignments:pending};
   // Validate each item independently so one unsupported input does not prevent others.
   const accepted=[];
   for(const a of pending){try{await call('validate',{...plan,assignments:[a]});accepted.push(a);}catch(e){issues.push((snapshot.fields.find(f=>f.fieldId===a.fieldId)?.label||a.fieldId)+'：'+e.message);}}
   pending=accepted;if(!pending.length)break;
   await call('execute',{...plan,assignments:pending});
   const job=await wait(requestId),done=new Set(job.results.filter(r=>r.fieldId).map(r=>r.fieldId));
   filled+=job.results.filter(r=>r.status==='filled').length;
   // verify only accepts a completed plan. Preserve partial execution counts
   // before any later scan or protocol error, without calling them verified.
   await report({status:'running',filled,verified,issues,message:'已填写 '+filled+' 项，正在检查执行结果。'});
   if(job.status==='complete'){
    try{
     const check=await call('verify',{requestId});verified+=check.checks.filter(c=>c.passed).length;
     if(!check.complete)issues.push('部分字段回读不一致，需要检查官网反馈');
    }catch(e){issues.push('填写后的独立回读未完成：'+e.message);break;}
   }
   pending=pending.filter(a=>!done.has(a.fieldId));
   if(job.status==='cancelled')throw Error('已停止后续动作');
   if(job.status!=='complete'){
    issues.push(job.error?.message||'部分字段填写失败');
    if(['VALUE_CHANGED','UNPLANNED_CHANGE','STALE_SNAPSHOT','STALE_FIELD'].includes(job.error?.code))break;
    // The first remaining field failed; do not retry it or infer its answer.
    pending=pending.slice(1);
   }
   if(job.status==='complete')pending=[];
   snapshot=await call('scan');
   await report({status:'running',filled,verified,issues,message:'已回读 '+verified+' 项，继续处理其余独立字段。'});
  }
  snapshot=await call('scan');
  if(shouldStop())throw Error('已停止后续填写');
  phase='saving';await report({status:'running',filled,verified,issues,message:'正在处理所选附件与官网草稿'});
  if(materials.attachment&&snapshot.capabilities?.upload){
   const file=materials.attachment,candidates=(snapshot.attachments||[]).filter(a=>/简历|résumé|resume/i.test(a.label));
   if(candidates.length!==1)issues.push('简历附件：没有唯一对应的上传入口');
   else if(!file.base64)issues.push('简历附件：没有接收到已选择的原文件');
   else try{
    const requestId=crypto.randomUUID();
    await call('uploadAttachment',{schemaVersion:1,requestId,snapshotId:snapshot.snapshotId,attachmentId:candidates[0].attachmentId,fileName:file.name,mimeType:file.mime_type||'application/octet-stream',base64:file.base64,sourceRef:file.id});
    const job=await wait(requestId);if(job.status!=='complete')throw Error(job.error?.message||job.status);
    snapshot=await call('scan');attachment_verified=(snapshot.attachments||[]).some(a=>a.attachmentId===candidates[0].attachmentId&&a.fileNames.length===1&&a.fileNames[0]===file.name);
    if(!attachment_verified)issues.push('简历附件：上传后的文件名回读未通过');
   }catch(e){issues.push('简历附件：'+e.message);snapshot=await call('scan');}
  }
  if(shouldStop())throw Error('已停止后续填写');
  if(snapshot.capabilities?.saveDraft)try{
   const requestId=crypto.randomUUID();await call('saveDraft',{schemaVersion:1,requestId,snapshotId:snapshot.snapshotId});
   const job=await wait(requestId);save_acknowledged=job.status==='complete'&&job.saved===true;if(!save_acknowledged)issues.push('草稿暂存未确认：'+(job.error?.message||job.status));
   snapshot=await call('scan');
  }catch(e){issues.push('草稿暂存未确认：'+e.message);}
  snapshot=await call('scan');
  phase='verifying';await report({status:'running',filled,verified,saved:false,save_acknowledged,attachment_verified,issues,message:'正在核对官网内容是否真正保存'});
  const checks=compareSaved(expected,snapshot);verified=checks.filter(c=>c.passed).length;
  for(const c of checks.filter(c=>!c.passed))issues.push(c.label+'：官网没有保留这项内容，请重新填写。');
  if(save_acknowledged&&client.reloadAndScan){
   try{
    if(shouldStop())throw Error('已停止');
    await report({status:'running',filled,verified,saved:false,save_acknowledged,attachment_verified,issues,message:'官网已回应暂存，正在重新打开同一页面检查内容是否保留'});
    snapshot=await client.reloadAndScan(materials.url);
    const stored=compareSaved(expected,snapshot);persisted=stored.filter(c=>c.passed).length;persistence_verified=true;
    attachment_verified=!materials.attachment?false:(snapshot.attachments||[]).some(a=>a.fileNames?.length===1&&a.fileNames[0]===materials.attachment.name);
    saved=expected.length>0&&persisted===expected.length&&(!materials.attachment||attachment_verified);
    for(const c of stored.filter(c=>!c.passed))issues.push(c.label+'：重新打开官网后内容为空或不同，尚未保存成功。');
    if(materials.attachment&&!attachment_verified)issues.push('简历附件：重新打开官网后未看到所选文件，请重新上传。');
   }catch(e){issues.push('保存检查未完成：'+e.message+'。请保留官网页面。');}
  }else issues.push(save_acknowledged?'官网回应暂存，但尚未重新打开核对，不能确认内容已保存。':'尚未保存到官网。请在官网点击“暂存”或“保存”，确认成功后再离开。');
  for(const f of snapshot.fields.filter(f=>f.required&&!f.currentValue&&!f.disabled))issues.push(f.label+'：官网仍需补充。');
  issues=[...new Set(issues)];
  const message=saved?'已重新打开官网，'+persisted+' 项内容仍在，草稿保存已确认。':persistence_verified?'重新打开官网后仅保留 '+persisted+' / '+expected.length+' 项，请处理下方未保存内容。':'已核对 '+verified+' 项，尚未确认官网保存。';
  const result={filled,verified,saved,save_acknowledged,persistence_verified,persisted,expected_count:expected.length,attachment_verified,issues};
  await report({status:'needs_attention',phase:'review',...result,message});
  return result;
 }
 const api={compile,run,compareSaved,identify};
 if(typeof module!=='undefined')module.exports=api;else globalThis.JobFillMaterials=api;
})();
