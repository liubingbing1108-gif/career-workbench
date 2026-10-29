/* A website module contains records; a record version contains its full field set. */
function materialModules(){return [...application.automatic,...application.decisions].filter(i=>i.website_field.collection&&!i.removed);}
function materialItem(wid){return materialModules().find(i=>i.website_field.id===wid);}
function materialEntry(item,eid){return item.selected.find(e=>e.id===eid)||(item.catalog||item.options).find(e=>e.id===eid);}
function optionalFieldRemoved(item,entryId,fieldId){return application.missing.some(i=>i.website_field.id===item.website_field.id&&(!entryId||i.entry_id===entryId)&&(!fieldId||i.field_id===fieldId)&&!i.blocking&&(preparationState.current?.removed_optional||[]).includes(preparationIssueKey(i)));}
function setFields(entry,item,blank=false){
 const used=new Set((item.mapping.members||[]).map(m=>m.field_id));
 return `<div class="set-field-grid">${entry.choices.filter(c=>blank||!optionalFieldRemoved(item,entry.id,c.field.id)).map(c=>{
  const ref=answerRef(item,entry.id,c),value=blank?'':answerDrafts.get(draftKey(ref))??c.content;
  return `<label class="${['multiline','versioned_text'].includes(c.field.type)?'full-span':''}" data-answer-ref="${escapeHtml(JSON.stringify(ref))}">${escapeHtml(c.field.label)} <small>${used.has(c.field.id)?'本网站使用':'资料组字段'}</small>${control(c.field,value,`data-set-value="${escapeHtml(c.field.id)}" aria-label="${escapeHtml(c.field.label)}"`)}</label>`;
 }).join('')}</div>`;
}
function materialModule(item){
 const selected=item.selected.map(e=>e.id),canChoose=true,catalog=item.catalog||item.options;
 const entries=[...item.selected,...catalog.filter(e=>!selected.includes(e.id))];
 return `<section class="card material-module" data-material-module="${escapeHtml(item.website_field.id)}" ${canChoose?`data-category-choice="${item.category}" data-group-choice="${escapeHtml(item.group_id)}"`:''}>
 <div class="section-heading"><label class="checkbox-label"><input type="checkbox" data-include-module ${item.included!==false?'checked':''} aria-label="本次使用${escapeHtml(item.website_field.label)}"><h3>${escapeHtml(item.website_field.label)}</h3></label><button data-material-action="remove-module">删除本次模块</button><span data-choice-count>已选 ${selected.length} / 全部 ${entries.length} ${preparationUnit(item)}</span></div>
 <div data-material-body><p>${escapeHtml(item.requirement.summary)}</p>
 <div class="button-row">${!['one','highest'].includes(item.requirement.selection)?'<button data-experience-all>全选适用资料</button><button data-experience-none>清空选择</button>':''}<button data-add-material="${escapeHtml(item.website_field.id)}">＋ 新增一${preparationUnit(item)}</button></div>
 ${entries.map(entry=>{
  const position=selected.indexOf(entry.id),blocked=entry.eligibility&&entry.eligibility!=='eligible',title=entryTitle(entry);
  return `<article class="prep-entry ${position>=0?'selected':''}" ${canChoose?`data-choice-entry="${entry.id}"`:''} data-material-entry="${entry.id}">
   <div class="record-heading"><label class="checkbox-label">${canChoose?`<input type="checkbox" data-experience ${position>=0?'checked':''} ${blocked?'disabled':''} aria-label="本次选择${escapeHtml(title)}">`:''}<strong>${escapeHtml(title)}</strong><span class="selection-label">${position>=0?'第 '+(position+1)+' '+preparationUnit(item):'未选择'}</span></label><button data-material-action="remove-record" class="remove-record-button" title="从本岗位填写材料中删除整条记录，资料库和其他岗位保留">删除本次记录</button></div>
   ${entry.scope_message?`<p class="scope-note">${escapeHtml(entry.scope_message)}</p>`:''}
   ${recordUsesVersions(entry)?`<div class="record-version-bar"><label>整组版本<select data-set-version aria-label="${escapeHtml(title)}整组版本"><option value="" ${!entry.selected_set?'selected':''}>本次字段组合</option>${(entry.set_versions||[]).map(v=>`<option value="${escapeHtml(v.id)}" ${entry.selected_set===v.id?'selected':''}>${escapeHtml(v.name)}</option>`).join('')}</select></label><button data-new-set-version>新建版本</button><button data-material-action="remove-version" ${!entry.selected_set?'disabled':''} title="仅从本岗位版本选项中删除，资料库版本和当前内容保留">删除</button>${entry.hidden_version_count?'<button data-material-action="restore-versions">恢复版本选项</button>':''}</div>`:''}
   <div data-linked-sources>${(entry.linked_source_choices||[]).map(c=>versionEditor(c,c.source_entry_id,item)).join('')}</div>
   <details data-set-details data-expansion-key="${sessionId}/${item.group_id}/${entry.id}"><summary>查看或编辑完整字段 · ${entry.choices.length} 项</summary>${setFields(entry,item)}<div class="group-save"><p>可以留空；保存整组内容：</p><div class="button-row"><button data-set-save="session" class="primary">仅供本次使用</button>${state.profile_contract===30?'<button data-set-save="update">预览差异并回库</button>':''}${recordUsesVersions(entry)?(state.profile_contract===30?'':'<button data-set-save="update">保存资料组</button>')+'<button data-set-save="new">另存为新版本</button>':''}</div></div></details>
   ${canChoose?`<div class="button-row"><button data-move-entry="up" ${position<=0?'disabled':''}>向上</button><button data-move-entry="down" ${position<0||position===selected.length-1?'disabled':''}>向下</button></div>`:''}
  </article>`;
 }).join('')||'<p class="empty">暂无资料，可新增一组后填写；字段允许留空。</p>'}<div data-module-missing>${preparationMissingGroups(application.missing.filter(i=>i.website_field.id===item.website_field.id))}</div></div></section>`;
}
function setSaveRecord(entry,root){return {entry_id:entry.id,edit_token:entry.edit_token,values:{...Object.fromEntries(entry.choices.map(c=>[c.field.id,c.content])),...Object.fromEntries($$('[data-set-value]',root).map(e=>[e.dataset.setValue,e.value]))},expected_values:Object.fromEntries(entry.choices.map(c=>[c.field.id,c.content])),revisions:Object.fromEntries(entry.choices.map(c=>[c.field.id,c.selected?.revision]))};}
async function clearSetDrafts(sid,item,entries){for(const entry of entries)for(const c of entry.choices)answerDrafts.delete(sid+'/'+item.group_id+'/'+entry.id+'/'+c.field.id);await answerDrafts.settled(sid);}
async function openSetVersion(item,entries,composition=false){
 if(preparationSaves?.busy(sessionId))throw Error('请等待当前选择保存完成');
 if(entries.some(e=>e.choices.some(c=>answerDrafts.has(draftKey(answerRef(item,e.id,c))))))throw Error('请先保存这组正在编辑的内容');
 const sid=sessionId,dialog=$('#set-version-dialog'),draftPrefix=sid+'/'+item.group_id+'/__newset/'+(composition?'module':entries[0].id)+'/';
 $('#set-version-title').textContent=composition?'新建模块版本':'新建整组版本';$('#set-version-name').value=answerDrafts.get(draftPrefix+'name')||'';$('#set-version-name').oninput=()=>answerDrafts.set(draftPrefix+'name',$('#set-version-name').value);
 $('#set-version-fields').innerHTML=entries.map(e=>`<fieldset data-new-set="${e.id}"><legend>${escapeHtml(entryTitle(e))}</legend>${setFields(e,item,true)}</fieldset>`).join('');
 for(const input of $$('[data-set-value]',dialog)){const key=draftPrefix+input.closest('[data-new-set]').dataset.newSet+'/'+input.dataset.setValue;input.value=answerDrafts.get(key)??'';input.oninput=()=>answerDrafts.set(key,input.value);}
 $('#set-version-discard').onclick=safe(async()=>{for(const key of [...answerDrafts.keys()])if(key.startsWith(draftPrefix))answerDrafts.delete(key);await answerDrafts.settled(sid);dialog.close();updatePreparationProgress();});
 $('#set-version-form').onsubmit=safe(async event=>{
  event.preventDefault();const button=$('#set-version-submit');if(button.disabled)return;button.disabled=true;
  try{
   if(sessionId!==sid)throw Error('岗位已切换，请重新打开');
   if(state.profile_contract===30){const records=entries.map(e=>setSaveRecord(e,$(`[data-new-set="${e.id}"]`,dialog))),name=$('#set-version-name').value;dialog.close();await previewMaterialWriteback(item,records,'new',name,composition);return;}
   await answerDrafts.settled(sid);await api('/api/website/set-answer',{session_id:sid,website_id:item.website_field.id,records:entries.map(e=>setSaveRecord(e,$(`[data-new-set="${e.id}"]`,dialog))),mode:'new',name:$('#set-version-name').value,composition});
   for(const key of [...answerDrafts.keys()])if(key.startsWith(draftPrefix))answerDrafts.delete(key);await answerDrafts.settled(sid);dialog.close();await refresh();toast('新版本已保存，旧版本保留');
  }finally{button.disabled=false;}
 });
 dialog.showModal();
}
function bindMaterialSets(){
 const root=$('#form-analysis');bindMaterialControls();
 $$('[data-missing-value]',root).forEach(input=>{const previous=input.oninput;input.oninput=()=>{previous?.();const key=draftKey(JSON.parse(input.closest('[data-answer-ref]').dataset.answerRef));for(const peer of $$('[data-set-value]',root))if(draftKey(JSON.parse(peer.closest('[data-answer-ref]').dataset.answerRef))===key)peer.value=input.value;};});
 $$('[data-set-value]',root).forEach(input=>input.oninput=()=>{const ref=JSON.parse(input.closest('[data-answer-ref]').dataset.answerRef);answerDrafts.set(draftKey(ref),input.value);for(const peer of $$('[data-missing-value]',root)){if(draftKey(JSON.parse(peer.closest('[data-answer-ref]').dataset.answerRef))===draftKey(ref))peer.value=input.value;}updatePreparationProgress();});
 $$('[data-set-save]',root).forEach(button=>button.onclick=safe(async()=>{
  const row=button.closest('[data-material-entry]'),item=materialItem(row.closest('[data-material-module]').dataset.materialModule),entry=materialEntry(item,row.dataset.materialEntry),sid=sessionId;
  if(preparationSaves?.busy(sid))throw Error('请等待当前选择保存完成');
  if(state.profile_contract===30&&button.dataset.setSave!=='session'){await previewMaterialWriteback(item,[setSaveRecord(entry,row)],button.dataset.setSave);return;}
  button.disabled=true;
  try{await answerDrafts.settled(sid);await api('/api/website/set-answer',{session_id:sid,website_id:item.website_field.id,records:[setSaveRecord(entry,row)],mode:button.dataset.setSave,name:'整组编辑版本'});await clearSetDrafts(sid,item,[entry]);if(sessionId===sid)await refresh();toast('整组资料已保存');}finally{button.disabled=false;}
 }));
 $$('[data-set-version]',root).forEach(select=>select.onchange=safe(async()=>{
  if(!select.value)return;const row=select.closest('[data-material-entry]'),item=materialItem(row.closest('[data-material-module]').dataset.materialModule),entry=materialEntry(item,row.dataset.materialEntry);
  if(entry.choices.some(c=>answerDrafts.has(draftKey(answerRef(item,entry.id,c)))))throw Error('请先保存这组正在编辑的内容');
  queuePreparation('set/'+item.group_id+'/'+entry.id,'/api/website/set-version',{website_id:item.website_field.id,entry_id:entry.id,version_id:select.value});
 }));
 $$('[data-new-set-version]',root).forEach(b=>b.onclick=safe(()=>{const row=b.closest('[data-material-entry]'),item=materialItem(row.closest('[data-material-module]').dataset.materialModule);return openSetVersion(item,[materialEntry(item,row.dataset.materialEntry)]);}));
 $$('[data-new-module-version]',root).forEach(b=>b.onclick=safe(()=>{const item=materialItem(b.closest('[data-material-module]').dataset.materialModule);return openSetVersion(item,item.selected,true);}));
 $$('[data-composition-version]',root).forEach(select=>select.onchange=safe(()=>{
  if(!select.value)return;const item=materialItem(select.closest('[data-material-module]').dataset.materialModule);
  if([...answerDrafts.keys()].some(k=>k.startsWith(sessionId+'/'+item.group_id+'/')))throw Error('请先保存模块内正在编辑的内容');
  queuePreparation('composition/'+item.group_id,'/api/website/composition-version',{website_id:item.website_field.id,version_id:select.value});
 }));
}
function patchMaterialSets(){
 patchScalarMaterials();
 for(const section of $$('[data-material-module]')){
  const item=materialItem(section.dataset.materialModule);if(!item){section.remove();continue;}
  const expected=[...new Set([...item.selected,...(item.catalog||item.options)].map(e=>e.id))],actual=$$('[data-material-entry]',section).map(e=>e.dataset.materialEntry);
  if(expected.length!==actual.length||expected.some(id=>!actual.includes(id))){const open=new Set($$('[data-expansion-key]',section).filter(e=>e.open).map(e=>e.dataset.expansionKey));const container=document.createElement('div');container.innerHTML=materialModule(item);const next=container.firstElementChild;section.replaceWith(next);$$('[data-expansion-key]',next).forEach(e=>e.open=open.has(e.dataset.expansionKey));continue;}
  $('[data-include-module]',section).checked=item.included!==false;
  $('[data-module-missing]',section).innerHTML=preparationMissingGroups(application.missing.filter(i=>i.website_field.id===item.website_field.id));
  const ids=item.selected.map(e=>e.id);$('[data-choice-count]',section).textContent=`已选 ${ids.length} / 全部 ${(item.catalog||item.options).length} ${preparationUnit(item)}`;
  for(const row of $$('[data-material-entry]',section)){
   const entry=materialEntry(item,row.dataset.materialEntry);if(!entry)continue;
   const linked=$('[data-linked-sources]',row);if(linked)linked.innerHTML=(entry.linked_source_choices||[]).map(c=>versionEditor(c,c.source_entry_id,item)).join('');
   if(recordUsesVersions(entry)){
   const select=$('[data-set-version]',row);select.innerHTML='<option value="">本次字段组合</option>'+entry.set_versions.map(v=>`<option value="${escapeHtml(v.id)}">${escapeHtml(v.name)}</option>`).join('');select.value=entry.selected_set||'';
   $('[data-material-action="remove-version"]',row).disabled=!entry.selected_set;
   const restore=$('[data-material-action="restore-versions"]',row);if(entry.hidden_version_count&&!restore){const button=document.createElement('button');button.dataset.materialAction='restore-versions';button.textContent='恢复版本选项';$('.record-version-bar',row).append(button);}else if(restore&&!entry.hidden_version_count)restore.remove();
   }
   row.classList.toggle('selected',ids.includes(entry.id));const number=ids.indexOf(entry.id);$('.selection-label',row).textContent=number<0?'未选择':'第 '+(number+1)+' '+preparationUnit(item);
   $('.checkbox-label strong',row).textContent=entryTitle(entry);if($('[data-experience]',row))$('[data-experience]',row).disabled=!!entry.eligibility&&entry.eligibility!=='eligible';
   for(const input of $$('[data-set-value]',row)){
    if(optionalFieldRemoved(item,entry.id,input.dataset.setValue)){input.closest('label').remove();continue;}
    const c=entry.choices.find(c=>c.field.id===input.dataset.setValue);
    if(c&&!answerDrafts.has(draftKey(answerRef(item,entry.id,c))))input.value=c.content;
   }
  }
 }
}

function resumeSetDraft(){
 const key=[...answerDrafts.keys()].find(k=>k.startsWith(sessionId+'/')&&k.includes('/__newset/'));if(!key)return false;
 const parts=key.split('/'),item=materialModules().find(i=>i.group_id===parts[1]);if(!item)return false;
 const composition=parts[3]==='module',entries=composition?item.selected:[materialEntry(item,parts[3])].filter(Boolean);
 if(!entries.length)return false;void safe(()=>openSetVersion(item,entries,composition))();return true;
}
function scalarMaterials(){return (application.material_items||application.automatic).filter(i=>!i.website_field.collection&&!i.removed&&!optionalFieldRemoved(i)).map(item=>{
 const content=`<p>${escapeHtml(item.value||'待补充或确认本次不填')}</p>${item.choice?`<details><summary>修改本次内容</summary>${versionEditor(item.choice,item.entry_id,item)}</details>`:''}`;
 return `<div class="scalar-material" data-scalar-material="${escapeHtml(item.website_field.id)}"><div class="record-heading"><label class="checkbox-label"><input type="checkbox" data-include-scalar ${item.included!==false?'checked':''} aria-label="本次填写${escapeHtml(item.website_field.label)}"><strong>${escapeHtml(item.website_field.label)}</strong></label><button data-material-action="remove-module">删除本次信息</button></div>${content}</div>`;
}).join('');}
function bindMaterialControls(){
 const root=$('#form-analysis');
 $$('[data-include-module],[data-include-scalar]',root).forEach(input=>input.onchange=()=>{
  const host=input.closest('[data-material-module],[data-scalar-material]'),wid=host.dataset.materialModule||host.dataset.scalarMaterial;
  queuePreparation('include/'+wid,'/api/website/material-control',{website_id:wid,action:'include',included:input.checked});
 });
 $$('[data-material-action]',root).forEach(button=>button.onclick=safe(async()=>{
  const host=button.closest('[data-material-module],[data-scalar-material]'),wid=host.dataset.materialModule||host.dataset.scalarMaterial,item=materialItem(wid),row=button.closest('[data-material-entry]'),eid=row?.dataset.materialEntry||button.dataset.restoreEntry;
  const sid=sessionId;const action=button.dataset.materialAction,versionId=action==='remove-composition'?$('[data-composition-version]',host).value:action==='remove-version'?$('[data-set-version]',row).value:undefined;
  if(action.startsWith('remove-')){
   await answerDrafts.settled(sid);
   const prefix=sid+'/'+(item?.group_id||wid)+'/';
   for(const key of [...answerDrafts.keys()])if(key.startsWith(prefix)&&(action==='remove-module'||action==='remove-record'&&(key.startsWith(prefix+eid+'/')||key.startsWith(prefix+'__newset/'+eid+'/'))))answerDrafts.delete(key);
   await answerDrafts.settled(sid);
  }
  preparationQueue().enqueue(sid,'control/'+wid+'/'+(eid||action),'/api/website/material-control',{website_id:wid,action,entry_id:eid,version_id:versionId});
 }));
}

function patchScalarMaterials(){
 const root=$('#scalar-materials');if(!root)return;
 const container=document.createElement('div');container.innerHTML=scalarMaterials();
 const visible=new Set([...container.children].map(e=>e.dataset.scalarMaterial));
 for(const current of [...root.children])if(!visible.has(current.dataset.scalarMaterial))current.remove();
 for(const next of [...container.children]){
  const current=[...root.children].find(e=>e.dataset.scalarMaterial===next.dataset.scalarMaterial);
  if(current){
   const opened=$$('details',current).map(e=>e.open),drafts=$$('[data-version-content]',current).map(e=>({value:e.value,dirty:e.value!==e.dataset.applied}));
   current.replaceWith(next);$$('details',next).forEach((e,i)=>e.open=opened[i]||false);
   $$('[data-version-content]',next).forEach((e,i)=>{if(drafts[i]?.dirty)e.value=drafts[i].value;});
  }else root.append(next);
 }
}

async function previewMaterialWriteback(item,records,mode,name='新表达版本',composition=false){
 const sid=sessionId,preview=await api('/api/website/sync-preview',{session_id:sid,website_id:item.website_field.id,records});
 const requestId=crypto.randomUUID();
 profileLibrary.ask('选择同步到资料库的变化',preview.records.map((record,index)=>`<section><h3>${escapeHtml(entryTitle(materialEntry(item,record.entry_id)))}</h3>${record.differences.map(diff=>`<label class="checkbox-label"><input type="checkbox" name="field" value="${index}/${escapeHtml(diff.field_id)}" ${diff.clear?'':'checked'}><span>${escapeHtml(diff.label)} · ${escapeHtml(diff.impact)}<br>原值：${escapeHtml(diff.old||'未填写')}<br>新值：${escapeHtml(diff.new||'清空（需明确勾选）')}</span></label>${diff.new_definition?`<label class="checkbox-label"><input type="checkbox" name="definition" value="${index}/${escapeHtml(diff.field_id)}">同时创建此对象的新属性“${escapeHtml(diff.label)}”（与选中答案共同保存）</label>`:''}`).join('')||'<p>没有需要同步的答案变化。</p>'}<details><summary>可同时保存的字段对应</summary>${record.relation_candidates.map(r=>`<label class="checkbox-label"><input name="relation" type="checkbox" value="${index}/${escapeHtml(r.question_id)}">${escapeHtml(r.label)} → ${escapeHtml(r.field_label)}${r.new_definition?'（须同时勾选新属性与答案）':''}</label>`).join('')}</details></section>`).join('')+`<label>选中对应的复用范围<select name="relation_scope"><option value="site" ${preview.site_scope_available?'':'disabled'}>本站、当前租户及表单</option><option value="general">明确确认为通用含义</option></select></label>`,async form=>{
  if(sessionId!==sid)throw Error('岗位已切换，请重新打开');
  const selected=form.getAll('field'),relations=form.getAll('relation'),definitions=form.getAll('definition');
  if(!selected.length&&!relations.length)return;
  const valuesFor=(list,index)=>list.filter(x=>x.startsWith(index+'/')).map(x=>x.slice(x.indexOf('/')+1));
  const payload=records.map((record,index)=>({...record,edit_token:preview.records[index].edit_token,sync_token:preview.records[index].sync_token,selected_fields:valuesFor(selected,index),confirmed_field_ids:valuesFor(definitions,index),relations:valuesFor(relations,index).map(question_id=>({question_id,scope:form.get('relation_scope'),confirmed:true}))})).filter(r=>r.selected_fields.length||r.relations.length);
  await api('/api/website/set-answer',{session_id:sid,website_id:item.website_field.id,records:payload,mode,name,composition,request_id:requestId});
  for(const record of payload){const entry=materialEntry(item,record.entry_id);for(const fid of record.selected_fields){const choice=entry.choices.find(c=>c.field.id===fid);if(choice)answerDrafts.delete(draftKey(answerRef(item,entry.id,choice)));}}await answerDrafts.settled(sid);await refresh();toast('已同步选中变化，未选字段和草稿保持原样');
 });
}

async function previewSingleWriteback(ref,value){
 const sid=sessionId,preview=await api('/api/website/answer-preview',{session_id:sid,...ref,value}),requestId=crypto.randomUUID();
 const relationHtml=`<label><input name="save_relation" type="checkbox">同时确认并保存此网站问题到“${escapeHtml(preview.label)}”的字段对应</label><label>对应复用范围<select name="relation_scope"><option value="site" ${preview.site_scope_available?'':'disabled'}>本站当前租户及表单</option><option value="general" ${preview.site_scope_available?'':'selected'}>通用含义（保留对象限制）</option></select></label>`;
 profileLibrary.ask('同步此字段到资料库',`<p>${escapeHtml(preview.label)} · ${escapeHtml(preview.impact)}</p><p>原值：${escapeHtml(preview.old||'未填写')}</p><p>新值：${escapeHtml(value||'清空')}</p>${preview.new_definition?'<p>同时在此对象创建已核对的新属性。</p>':''}${preview.expression?'<label>保存方式<select name="mode"><option value="update">更新所选表达版本</option><option value="new">另存新表达版本</option></select></label><label>新版本名称<input name="name" value="本次表达"></label>':''}${value===''?'<label><input name="clear" type="checkbox" required>确认清空当前字段</label>':''}${relationHtml}`,async form=>{
  if(sessionId!==sid)throw Error('岗位已切换，请重新核对');
  await api('/api/website/answer',{session_id:sid,...ref,value,mode:form.get('mode')||'update',name:form.get('name')||'',version_id:preview.version_id,expected_revision:preview.expected_revision,request_id:requestId,preview_token:preview.token,relation_options:form.has('save_relation')?{scope:form.get('relation_scope'),confirmed:true}:null});
  answerDrafts.delete(draftKey(ref));await answerDrafts.settled(sid);await refresh();toast('此字段已同步到资料库');
 });
}
