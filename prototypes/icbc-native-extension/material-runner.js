/* Upper-layer material handoff. All browser actions use the existing protocol. */
(() => {
 'use strict';
 const normal=id=>id.replace(/\[\d+\]/g,'[]');
 const unwrap=r=>{if(!r.ok)throw Error(r.error?.message||'执行器失败');return r.result;};
 function compile(materials,snapshot){
  if(snapshot.page.url!==materials.url)throw Error('官网链接与确认的材料不一致');
  const assignments=[],issues=[],readOnlyChecks=[];
  const add=(id,value,source,label,strictLabel=false,target={})=>{
   if(value===''||value===null||value===undefined)return;
   let matches=snapshot.fields.filter(f=>f.fieldId===id||(id.includes('[]')&&normal(f.fieldId)===id));
   if(strictLabel&&matches.length===1&&matches[0].label!==label)matches=[];
   if(!matches.length)matches=snapshot.fields.filter(f=>f.label===label);
   if(strictLabel){
    const sameLabel=snapshot.fields.filter(f=>f.label===label&&(!target.target_section||identify(snapshot,f).section===target.target_section));
    const kind=k=>['select','autocomplete','multiselect'].includes(k)?'choice':['email','tel','textarea','number'].includes(k)?'text':k;
    if(target.target_kind)matches=sameLabel.filter(f=>kind(f.kind)===kind(target.target_kind));
    else if(sameLabel.length>1)matches=[];
   }
   if(matches.length!==1){issues.push(label+'：当前控件未接通，需本人处理');return;}
   const field=matches[0];
   if(field.kind==='multiselect'&&!Array.isArray(value))value=[value];
   if(field.disabled||field.kind==='unsupported'){readOnlyChecks.push({fieldId:field.fieldId,value});if(JSON.stringify(field.currentValue)!==JSON.stringify(value))issues.push(label+'：官网只读内容与本次材料不同，请核对');return;}
   assignments.push({fieldId:field.fieldId,value,overwrite:'ifUnchanged',sourceRef:JSON.stringify(source||{})});
  };
  for(const row of materials.rows){
   if(row.follow_up)issues.push(row.follow_up);
   if(row.records){
    const section=findSection(snapshot,row);
    if(section?.count>row.records.length)issues.push(row.label+'：官网多出 '+(section.count-row.records.length)+' 条既有记录，需本人检查/删除');
    const recordOrder=matchMaterialRecords(snapshot,row,section);
    row.records.forEach((record,index)=>record.values.forEach(v=>{
     const ordinal=snapshot.fields.some(f=>f.sectionId===section?.sectionId&&f.recordId)?recordOrder[index]:index;
     let candidates=snapshot.fields.filter(f=>normal(f.fieldId)===v.website_id&&f.fieldId.includes('['+ordinal+']'));
     // Generic adapters return stable flat IDs plus record IDs. Resolve a child
     // only within the selected record and section, with one exact field label.
     if(!candidates.length){
      const members=snapshot.fields.filter(f=>f.sectionId===section?.sectionId);
      const records=[...new Set(members.map(f=>f.recordId).filter(Boolean))];
      candidates=members.filter(f=>f.recordId===records[recordOrder[index]]&&f.label===v.label);
     }
     if(!v.value)return;
     if(candidates.length!==1){issues.push(row.label+'第 '+(index+1)+' 条 '+v.label+'：当前没有唯一对应控件');return;}
     add(candidates[0].fieldId,v.value,v.source_ref,row.label+' '+v.label);
    }));
   }else add(row.website_id,row.value,row.source_ref,row.label,true,row);
  }
  if(materials.attachment&&!snapshot.capabilities?.upload)issues.push('简历附件：请上传已选择的原文件“'+materials.attachment.name+'”；当前控件没有已接通的附件驱动');
  return {assignments,issues,readOnlyChecks};
 }
 const findSection=(snapshot,row)=>snapshot.sections.find(s=>s.sectionId===row.website_id&&s.label===row.label)||snapshot.sections.filter(s=>s.label===row.label).length===1&&snapshot.sections.find(s=>s.label===row.label)||snapshot.sections.find(s=>s.sectionId===row.website_id&&!s.label);
 function identify(snapshot,f){
  const members=snapshot.fields.filter(x=>x.sectionId===f.sectionId),records=[...new Set(members.map(x=>x.recordId).filter(Boolean))];
  return {label:f.label,section:snapshot.sections.find(s=>s.sectionId===f.sectionId)?.label||f.context?.section||'',record:f.recordId?records.indexOf(f.recordId):-1,component:f.context?.componentIndex??null};
 }
 // A website may reorder saved rows. Bind complete records before comparing
 // fields; never combine the school from one row with dates from another.
 function bindRecords(groups,actual,agrees){
  const assigned=new Map(),used=new Set();
  for(const [key,values] of groups){const candidates=actual.filter(n=>!used.has(n)&&agrees(values,n));if(candidates.length){assigned.set(key,candidates[0]);used.add(candidates[0]);}}
  for(const [key] of groups)if(!assigned.has(key)&&actual.includes(key)&&!used.has(key)){assigned.set(key,key);used.add(key);}
  return assigned;
 }
 function matchMaterialRecords(snapshot,row,section){
  const members=snapshot.fields.filter(f=>f.sectionId===section?.sectionId),records=[...new Set(members.map(f=>f.recordId).filter(Boolean))];
  const groups=new Map(row.records.map((r,i)=>[i,r.values.filter(v=>v.value!==''&&v.value!=null)]));
  const bound=bindRecords(groups,records.map((_,i)=>i),(values,n)=>values.length>0&&values.every(v=>{const found=members.filter(f=>f.recordId===records[n]&&f.label===v.label);return found.length===1&&JSON.stringify(found[0].currentValue)===JSON.stringify(v.value);}));
  return row.records.map((_,i)=>bound.get(i));
 }
 const sameIdentity=(a,b)=>a.label===b.label&&a.section===b.section&&a.record===b.record&&a.component===b.component;
 function compareSaved(expected,snapshot){
  const actual=snapshot.fields.map(f=>({field:f,identity:identify(snapshot,f)})),bindings=new Map();
  for(const section of new Set(expected.filter(e=>e.identity.record>=0).map(e=>e.identity.section))){
   const groups=new Map();for(const e of expected.filter(e=>e.identity.section===section&&e.identity.record>=0)){if(!groups.has(e.identity.record))groups.set(e.identity.record,[]);groups.get(e.identity.record).push(e);}
   const candidates=[...new Set(actual.filter(a=>a.identity.section===section&&a.identity.record>=0).map(a=>a.identity.record))];
   const matching=(e,n)=>actual.filter(a=>sameIdentity(a.identity,{...e.identity,record:n}));
   bindings.set(section,bindRecords(groups,candidates,(values,n)=>values.every(e=>{const found=matching(e,n);return found.length===1&&JSON.stringify(found[0].field.currentValue)===JSON.stringify(e.value);})));
  }
  return expected.map(e=>{const identity={...e.identity};if(identity.record>=0)identity.record=bindings.get(identity.section)?.get(identity.record);const matches=actual.filter(a=>sameIdentity(a.identity,identity));return {label:e.display,passed:matches.length===1&&JSON.stringify(matches[0].field.currentValue)===JSON.stringify(e.value)};});
 }
 function inspectMaterials(materials,snapshot){
  if(materials.url!==snapshot.page.url)throw Error('核对页面与已确认材料不一致');
  const checks=[];
  for(const row of materials.rows){
   const section=findSection(snapshot,row),members=snapshot.fields.filter(f=>f.sectionId===section?.sectionId),records=[...new Set(members.map(f=>f.recordId).filter(Boolean))];
   const recordOrder=row.records?matchMaterialRecords(snapshot,row,section):[];
   const check=(label,value,index)=>{if(!value)return;const found=index===null?snapshot.fields.filter(f=>f.label===label):members.filter(f=>f.recordId===records[recordOrder[index]]&&f.label===label);checks.push({label:row.label+' · '+(index===null?'':index+1+' · ')+label,passed:found.length===1&&JSON.stringify(found[0].currentValue)===JSON.stringify(value)});};
   if(row.records)row.records.forEach((r,i)=>r.values.forEach(v=>check(v.label,v.value,i)));else check(row.label,row.value,null);
  }
  const attachment=materials.attachment&&(snapshot.attachments||[]).some(a=>a.fileNames?.length===1&&a.fileNames[0]===materials.attachment.name);
  return {checks,attachment_verified:!!attachment};
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
   const start=Date.now(),baseFilled=filled;let changed=start,signature='';
   while(Date.now()-start<1200000){
    if(shouldStop()){await call('cancel');throw Error('已停止后续填写，请检查官网保留内容');}
    const job=await call('status',{requestId});if(!job)throw Error('执行器任务已丢失，请重新扫描');
    if(job.status!=='running')return job;
    const progress=JSON.stringify([job.results?.length,job.currentField,job.progress]);
    if(progress!==signature){signature=progress;changed=Date.now();}
    await report({status:'running',filled:baseFilled+(job.results||[]).filter(r=>r.status==='filled').length,verified,issues,message:job.currentField?'正在填写：'+job.currentField.label+'（'+job.currentField.index+'/'+job.currentField.total+'）':job.progress||({connecting:'正在读取官网表单',filling:'正在填写资料',saving:'正在处理附件与保存',verifying:'正在回读检查'}[phase]||'正在处理本次申请')});
    if(Date.now()-changed>=120000)break;
    await new Promise(r=>setTimeout(r,200));
   }
   await call('cancel');throw Error('官网控件长时间无进展，已停止；已填内容保留，可重试填写');
  };
  let snapshot=await call('scan');if(snapshot.page.url!==materials.url)throw Error('招聘页面已切换');
  if(materials.verification_only){
   const checked=inspectMaterials(materials,snapshot),count=checked.checks.filter(c=>c.passed).length;
   const persisted=materials.after_reopen?count:0,persistence_verified=materials.after_reopen===true;
   const result={filled:0,verified:count,expected_count:checked.checks.length,persisted,persistence_verified,saved:persistence_verified&&count===checked.checks.length&&(!materials.attachment||checked.attachment_verified),attachment_verified:checked.attachment_verified,draft_supported:!!snapshot.capabilities?.saveDraft,save_acknowledged:false,issues:checked.checks.filter(c=>!c.passed).map(c=>c.label+'：当前页面为空或不同')};
   if(materials.attachment&&!checked.attachment_verified)result.issues.push('当前页面没有已确认的简历附件');
   await report({status:'needs_attention',phase:'review',...result,message:(persistence_verified?'重新打开后':'当前官网')+'核对 '+count+' / '+checked.checks.length+' 项。未填写、上传或提交。'});return result;
  }
  const autoParseAttachment=(snapshot.attachments||[]).filter(a=>a.autoFill&&/简历|résumé|resume/i.test(a.label));
  if(materials.attachment&&autoParseAttachment.length===1){
   const file=materials.attachment,a=autoParseAttachment[0];phase='saving';
   await report({status:'running',filled,verified,issues,message:'正在上传所选简历并等待网站解析，随后填写确认材料'});
   if(client.saveLocalDraft)await client.saveLocalDraft(snapshot);
   if(!file.base64)throw Error('简历附件：没有接收到已选择的原文件');
   const requestId=crypto.randomUUID();await call('uploadAttachment',{schemaVersion:1,requestId,snapshotId:snapshot.snapshotId,attachmentId:a.attachmentId,fileName:file.name,mimeType:file.mime_type||'application/octet-stream',base64:file.base64,sourceRef:file.id});
   const uploaded=await wait(requestId);if(uploaded.status!=='complete')throw Error('简历附件：'+(uploaded.error?.message||uploaded.status));
   snapshot=await call('scan');attachment_verified=(snapshot.attachments||[]).some(a=>a.fileNames?.length===1&&a.fileNames[0]===file.name);
   if(!attachment_verified)throw Error('上传后未能核对所选原件');
  }
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
  const expected=[...built.assignments,...built.readOnlyChecks].map(a=>{const f=snapshot.fields.find(f=>f.fieldId===a.fieldId),identity=identify(snapshot,f);return {value:a.value,identity,display:[identity.section,identity.record>=0?'第 '+(identity.record+1)+' 条':'',identity.label].filter(Boolean).join(' · ')};});
  let pending=built.assignments.filter(a=>{
   if(!materials.retry)return true;
   const value=snapshot.fields.find(f=>f.fieldId===a.fieldId)?.currentValue;
   if(JSON.stringify(value)===JSON.stringify(a.value))return false;
   if(value!==''&&value!==null&&value!==undefined){issues.push((snapshot.fields.find(f=>f.fieldId===a.fieldId)?.label||a.fieldId)+'：官网已有不同内容，重试时保留，请核对');return false;}
   return true;
  });
  while(pending.length){
   if(shouldStop())throw Error('已停止后续填写');
   pending=pending.filter(a=>{const f=snapshot.fields.find(f=>f.fieldId===a.fieldId);if(!f||JSON.stringify(f.currentValue)!==baseline.get(a.fieldId)){issues.push((f?.label||a.fieldId)+'：扫描后已被修改，保留官网内容');return false;}return true;});
   if(!pending.length)break;
   const requestId=crypto.randomUUID(),plan={schemaVersion:1,requestId,snapshotId:snapshot.snapshotId,assignments:pending};
   // Validate each item independently so one unsupported input does not prevent others.
   const accepted=[];
   try{await call('validate',plan);accepted.push(...pending);}
   catch{for(const a of pending){try{await call('validate',{...plan,assignments:[a]});accepted.push(a);}catch(e){issues.push((snapshot.fields.find(f=>f.fieldId===a.fieldId)?.label||a.fieldId)+'：'+e.message);}}}
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
  if(materials.attachment&&snapshot.capabilities?.upload&&!attachment_verified){
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
  for(const c of checks.filter(c=>!c.passed))issues.push(c.label+'：当前页面内容为空或与本次材料不同。');
  // Absence of a save button is not evidence of autosave. Never reload an
  // unsaved form merely because its DOM currently matches the materials.
  // Protect this page's current answers before any persistence check reloads it.
  if(client.saveLocalDraft)try{await client.saveLocalDraft(snapshot);}catch(error){issues.push('本机草稿备份失败：'+error.message);}
  if(save_acknowledged&&client.reloadAndScan){
   try{
    if(shouldStop())throw Error('已停止');
    await report({status:'running',filled,verified,saved:false,save_acknowledged,attachment_verified,issues,message:save_acknowledged?'官网已回应暂存，正在重新打开同一页面检查内容是否保留':'此页面没有暂存按钮，正在重新打开同页核对是否自动保留内容'});
    snapshot=await client.reloadAndScan(materials.url);
    const stored=compareSaved(expected,snapshot);persisted=stored.filter(c=>c.passed).length;persistence_verified=true;
    attachment_verified=!materials.attachment?false:(snapshot.attachments||[]).some(a=>a.fileNames?.length===1&&a.fileNames[0]===materials.attachment.name);
    saved=expected.length>0&&persisted===expected.length&&(!materials.attachment||attachment_verified);
    for(const c of stored.filter(c=>!c.passed))issues.push(c.label+'：重新打开官网后内容为空或不同，尚未保存成功。');
    if(materials.attachment&&!attachment_verified)issues.push('简历附件：重新打开官网后未看到所选文件，请重新上传。');
   }catch(e){issues.push('保存检查未完成：'+e.message+'。请保留官网页面。');}
  }else issues.push(save_acknowledged?'官网回应暂存，但尚未重新打开核对，不能确认内容已保存。':snapshot.capabilities?.saveDraft?'尚未保存到官网。请在官网点击“暂存”或“保存”，确认成功后再离开。':materials.preserve_unsaved_page?'此官网没有草稿保存，重新打开会丢失内容；请保留当前页面并由本人提交。':'此页面没有草稿保存按钮；当前输入已保留，请保持页面并由本人提交。');
  for(const f of snapshot.fields.filter(f=>f.required&&!f.currentValue&&!f.disabled))issues.push(f.label+'：官网仍需补充。');
  issues=[...new Set(issues)];
  const message=materials.preserve_unsaved_page?'已恢复并核对 '+verified+' / '+expected.length+' 项'+(attachment_verified?'及所选附件':'')+'。此官网页没有草稿保存，请保留当前页面'+(verified===expected.length&&(!materials.attachment||attachment_verified)?'供你本人提交。':'并处理下方未完成项。'):saved?'已重新打开官网，'+persisted+' 项内容及所选附件仍在。':persistence_verified?'重新打开官网后仅保留 '+persisted+' / '+expected.length+' 项，请处理下方未保存内容。':'已核对 '+verified+' 项，尚未确认官网保存。';
  const result={filled,verified,saved,save_acknowledged,persistence_verified,persisted,expected_count:expected.length,attachment_verified,draft_supported:!!snapshot.capabilities?.saveDraft,issues};
  await report({status:'needs_attention',phase:'review',...result,message});
  return result;
 }
 const api={compile,run,compareSaved,identify,inspectMaterials};
 if(typeof module!=='undefined')module.exports=api;else globalThis.JobFillMaterials=api;
})();
