function readableIssue(text){
 const [label]=String(text).split('：');
 if(/精度/.test(text))return label+'：日期没有填入。系统需要重新识别日期选择器后重试；你也可以在官网补填。';
 if(/等待官网控件超时|精确下拉|唯一对应控件/.test(text))return label+'：没有选中官网选项，请重试；仍失败时到官网选择。';
 if(/字段被重建或移动.*搜索/.test(text))return '选择窗口影响了检查。请重新填写并检查保存结果。';
 if(/字段被重建|STALE_/.test(text))return '官网表单发生变化，请重新读取后继续。已保存的材料选择会保留。';
 if(/保存\/附件处理后回读不一致/.test(text))return label+'：官网显示的内容与本次材料不同，请检查后重新保存。';
 if(/控件未接通|附件驱动|执行器尚未支持/.test(text))return label+'：这项尚未自动完成，请到官网处理。';
 return String(text).replace(/回读/g,'核对').replace(/执行器/g,'填写插件');
}
/* The scan is background context. Only material decisions occupy the main page. */
function preparationIssueKey(item){return [item.website_field.id,item.entry_id,item.child_id,item.field_id,item.kind].map(v=>v||'').join('/');}
function preparationMissing(item) {
  const field=state.fields.find(f=>f.id===item.field_id);
  const site=item.child_id ? item.website_field.children?.find(c=>c.id===item.child_id) : item.website_field;
  const ref={website_id:item.website_field.id,group_id:item.group_id,entry_id:item.entry_id,field_id:item.field_id,child_id:item.child_id};
  const key=preparationIssueKey(item),manual=(preparationState.current?.manual||[]).some(i=>i.key===key);
  const spec=site?.options?.length?{type:'select',options:site.options}:field||{type:site?.type==='textarea'?'multiline':'text'};
  const label=site?.label||item.message;
  return `<div class="missing-item" data-missing-key="${escapeHtml(key)}" data-answer-ref="${escapeHtml(JSON.stringify(ref))}"><label>${escapeHtml(label)}${item.blocking?' <span class="required-label">官网必填</span>':' · 可选'}${manual?'<span class="manual-label"> · 留给官网本人处理</span>':''}${item.editable&&!manual?control(spec,answerDrafts.get(draftKey(ref))??'',`data-missing-value aria-label="${escapeHtml(label)}"`):''}</label>${manual?'':`<p>${escapeHtml(item.message)}${site?.instructions?' · '+escapeHtml(site.instructions):''}</p>`}${item.previous_answer&&!manual?`<button class="text-button" data-reuse-answer="${escapeHtml(item.previous_answer)}">沿用此前确认：${escapeHtml(item.previous_answer)}</button>`:''}${item.editable&&item.kind==='value'?`<button class="text-button" data-defer-key="${escapeHtml(key)}" data-deferred="${!manual}">${manual?'改为在这里补充':'这项我到官网填写'}</button>`:''}${item.kind==='count'?`<button data-add-material="${escapeHtml(item.website_field.id)}">补充一条资料</button>`:''}</div>`;
}
function preparationMissingGroups(items){
  const groups=new Map();for(const item of items){const key=item.entry_id||item.group_id;if(!groups.has(key))groups.set(key,[]);groups.get(key).push(item);}
  return [...groups].map(([key,items])=>{
    const entry=state.entries.find(e=>e.id===items[0].entry_id),editable=items.some(i=>i.editable&&!(preparationState.current?.manual||[]).some(m=>m.key===preparationIssueKey(i)));
    return `<fieldset class="question-group" data-question-group="${escapeHtml(key)}"><legend>${escapeHtml(entry?entryTitle(entry):items[0].website_field.label)}</legend>${items.map(preparationMissing).join('')}${editable?`<div class="group-save"><p>补充这组信息后，选择保存方式：</p><div class="button-row"><button data-group-mode="session" class="primary">仅供本次使用</button><button data-group-mode="update">更新当前版本</button><button data-group-mode="new">保存为新版本</button></div></div>`:''}</fieldset>`;
  }).join('');
}
function preparationDecision(item) {
  const selected=item.selected.map(e=>e.id),catalog=item.catalog||item.options;
  // Catalog order stays fixed when checking. Selection order is explicit.
  const entries=[...item.selected,...catalog.filter(e=>!selected.includes(e.id))];
  return `<section class="card prep-internships" data-decision="${escapeHtml(item.website_field.id)}" data-category-choice="${item.category}" data-group-choice="${escapeHtml(item.group_id)}"><div class="section-heading"><h3>${escapeHtml(item.website_field.label)}</h3><span data-choice-count>已选 ${selected.length} / 全部 ${entries.length} 段</span></div><p>${escapeHtml(item.requirement.summary)}</p><p class="selection-help">每次勾选包含这一段的单位、岗位、时间和描述。版本仅切换本段描述；顺序按编号填写。选择自动保存到本岗位。</p><div class="button-row"><button data-experience-all>全选适用经历</button><button data-experience-none>清空选择</button></div>${entries.map(entry=>{
    const mapped=(item.mapping.members||[]).map(m=>m.field_id);
    const description=entry.choices.find(c=>mapped.includes(c.field.id)&&c.field.type==='versioned_text');
    const ref=description?answerRef(item,entry.id,{...description,child_id:item.mapping.members.find(m=>m.field_id===description.field.id)?.website_id}):null,position=selected.indexOf(entry.id);
    const blocked=entry.eligibility&&entry.eligibility!=='eligible';
    return `<article class="prep-entry ${selected.includes(entry.id)?'selected':''}" data-choice-entry="${entry.id}"><label class="checkbox-label"><input type="checkbox" data-experience ${selected.includes(entry.id)?'checked':''} ${blocked?'disabled':''}><strong>${escapeHtml(entryTitle(entry))}</strong><span class="selection-label">${position>=0?'第 '+(position+1)+' 段':'未选择'}</span></label><p class="muted">${escapeHtml([entry.values.started,entry.values.ended].filter(Boolean).join(' — '))}</p>${entry.scope_message?`<p class="scope-note">${escapeHtml(entry.scope_message)}</p>`:''}${description?`<div class="prep-version"><label>描述版本 · ${description.versions.length} 个<select ${entry.eligibility==='outside_scope'?'data-catalog-version':'data-prep-version'} data-answer-ref="${escapeHtml(JSON.stringify(ref))}" aria-label="${escapeHtml(entryTitle(entry))}经历版本">${description.versions.map(v=>`<option value="${v.id}" ${v.id===description.selected?.id?'selected':''}>${escapeHtml(versionName(v))}${state.entries.find(e=>e.id===entry.id)?.default_versions?.[description.field.id]===v.id?' · 默认':''}</option>`).join('')}</select></label><p data-description-summary>${escapeHtml(description.content)}</p></div>`:''}<details data-expansion-key="${sessionId}/${item.group_id}/${entry.id}" data-entry-details="${entry.id}"><summary>查看或修改整段内容</summary><div data-entry-editor></div></details><div class="button-row"><button data-move-entry="up" ${position<=0?'disabled':''}>向上</button><button data-move-entry="down" ${position<0||position===selected.length-1?'disabled':''}>向下</button></div></article>`;
  }).join('')}</section>`;
}

function preparationAutomatic(item) {
  if(item.website_field.collection)return `<section class="material-set" data-auto-group="${escapeHtml(item.group_id)}"><h4>${escapeHtml(item.website_field.label)} · ${item.selected.length} 条</h4>${item.selected.map(entry=>`<details data-expansion-key="${sessionId}/${item.group_id}/${entry.id}"><summary>${escapeHtml(entryTitle(entry))}</summary>${entryEditors(entry,item)}</details>`).join('')}<button data-add-material="${escapeHtml(item.website_field.id)}">补充一条资料</button></section>`;
  return `<div class="summary-row"><span>${escapeHtml(item.website_field.label)}</span><span>${escapeHtml(item.value||'留空')}</span></div>${item.choice?`<details><summary>修改本次内容</summary>${versionEditor(item.choice,item.entry_id,item)}</details>`:''}`;
}

function requireSavedPreparation(root){
  if(preparationSaves?.busy(sessionId))throw Error('本次选择尚未保存完成，请稍候或重试保存。');
  if($$('[data-version-content]',root).some(e=>e.value!==e.dataset.applied)||[...answerDrafts.keys()].some(key=>key.startsWith(sessionId+'/')))throw Error('修改的内容还未选择保存方式，请先选择三个保存按钮之一。');
}
function preparationPreviewBody(preview){
  if(!preview)return '<p class="muted">资料准备完成后将在这里显示。</p>';
  return preview.rows.map(row=>`<section class="preview-section"><h3>${escapeHtml(row.label)}${row.records?`<span>${row.records.length} 条</span>`:''}</h3>${row.records?row.records.map((record,index)=>`<article><div class="record-number">${String(index+1).padStart(2,'0')}</div><div>${record.values.map(v=>`<div class="summary-row"><span>${escapeHtml(v.label)}</span><span class="${v.value?'':'muted'}">${escapeHtml(v.value||(v.manual?'官网本人填写':v.pending?'待补充':'—'))}</span></div>`).join('')}</div></article>`).join('')||'<p class="muted">本次不填写</p>':`<p class="preview-scalar ${row.pending?'preview-pending':''}">${escapeHtml(row.value||(row.manual?'官网本人填写':row.pending?'待左侧补充':'—'))}</p>`}</section>`).join('')+`<section class="preview-section"><h3>简历附件</h3><p>${escapeHtml(preview.attachment?.name||(preparationState.attachment_decided?'本次不上传':'待选择'))}</p></section>`+(preview.notes||[]).map(note=>`<p class="notice">${escapeHtml(note)}</p>`).join('');
}
let preparationSaves;
function preparationQueue(){
  if(!preparationSaves)preparationSaves=new PreparationSaveQueue(
    (path,body)=>api(path,body),id=>api('/api/preparation/bundle?session='+encodeURIComponent(id)),
    id=>{if(id===sessionId)updatePreparationProgress();},
    (id,bundle)=>{if(id!==sessionId||currentView!=='practice')return;application=bundle.application;preparationState={...preparationState,...bundle.preparation};patchPreparation();});
  return preparationSaves;
}
function queuePreparation(key,path,body){preparationQueue().enqueue(sessionId,key,path,body);}
function patchPreparation(){
  $$('[data-category-choice]',$('#form-analysis')).forEach(section=>{
    const item=application.decisions.find(i=>i.group_id===section.dataset.groupChoice);if(!item)return;
    paintPreparationChoice(section,item.selected.map(e=>e.id));
    $$('[data-prep-version]',section).forEach(select=>{const ref=JSON.parse(select.dataset.answerRef),entry=(item.catalog||item.options).find(e=>e.id===ref.entry_id),choice=entry?.choices.find(c=>c.field.id===ref.field_id);if(choice){select.value=choice.selected?.id||'';$('[data-description-summary]',select.closest('.prep-version')).textContent=choice.content;}});
  });
  const scroll=$('#prep-live-preview')?.scrollTop||0;
  if($('#prep-live-preview')){$('#prep-live-preview').innerHTML=preparationPreviewBody(preparationState.current);$('#prep-live-preview').scrollTop=scroll;}
  if($('#prep-needed-body'))$('#prep-needed-body').innerHTML=preparationMissingGroups(application.missing.filter(i=>i.blocking))||'<p class="all-ready">已有资料已匹配，无需补充。</p>';
  if($('#prep-optional-body'))$('#prep-optional-body').innerHTML=preparationMissingGroups(application.missing.filter(i=>!i.blocking));
  if($('#prep-needed-count'))$('#prep-needed-count').textContent=String((preparationState.current?.tasks||[]).filter(i=>i.key!=='attachment').length);
  bindPreparation();updatePreparationProgress();
}
function paintPreparationChoice(section,ids){
  const item=application.decisions.find(i=>i.group_id===section.dataset.groupChoice);
  section.dataset.selection=JSON.stringify(ids);
  $('[data-choice-count]',section).textContent=`已选 ${ids.length} / 全部 ${(item.catalog||item.options).length} 段`;
  $$('[data-choice-entry]',section).forEach(row=>{const index=ids.indexOf(row.dataset.choiceEntry);row.classList.toggle('selected',index>=0);$('[data-experience]',row).checked=index>=0;$('.selection-label',row).textContent=index>=0?'第 '+(index+1)+' 段':'未选择';$('[data-move-entry="up"]',row).disabled=index<=0;$('[data-move-entry="down"]',row).disabled=index<0||index===ids.length-1;});
}
function preparationAnswerBody(ref,value,mode){
  const item=[...application.decisions,...application.automatic].find(i=>i.website_field.id===ref.website_id);
  const entry=item?.selected?.find(e=>e.id===ref.entry_id),choice=entry?.choices?.find(c=>c.field.id===ref.field_id)||item?.choice;
  return {session_id:sessionId,...ref,value,mode,version_id:choice?.selected?.id,expected_revision:choice?.selected?.revision};
}
function bindPreparation(){
  const root=$('#form-analysis');bindChoices();
  const persist=(section,ids)=>{paintPreparationChoice(section,ids);queuePreparation('choices/'+section.dataset.groupChoice,'/api/website/choices',{category:section.dataset.categoryChoice,group_id:section.dataset.groupChoice,entry_ids:ids});};
  const idsFor=section=>JSON.parse(section.dataset.selection||JSON.stringify(application.decisions.find(i=>i.group_id===section.dataset.groupChoice).selected.map(e=>e.id)));
  $$('[data-experience]',root).forEach(input=>input.onchange=()=>{const row=input.closest('[data-choice-entry]'),section=row.closest('[data-category-choice]'),ids=idsFor(section).filter(id=>id!==row.dataset.choiceEntry);if(input.checked)ids.push(row.dataset.choiceEntry);persist(section,ids);});
  $$('[data-experience-all],[data-experience-none]',root).forEach(button=>button.onclick=()=>{const section=button.closest('[data-category-choice]');persist(section,button.hasAttribute('data-experience-all')?$$('[data-choice-entry]',section).filter(row=>!$('[data-experience]',row).disabled).map(row=>row.dataset.choiceEntry):[]);});
  $$('[data-move-entry]',root).forEach(button=>button.onclick=()=>{const row=button.closest('[data-choice-entry]'),section=row.closest('[data-category-choice]'),ids=idsFor(section),index=ids.indexOf(row.dataset.choiceEntry),next=index+(button.dataset.moveEntry==='up'?-1:1);if(index<0||next<0||next>=ids.length)return;const target=$$('[data-choice-entry]',section).find(e=>e.dataset.choiceEntry===ids[next]),column=section.closest('.decision-column'),top=row.getBoundingClientRect().top;if(button.dataset.moveEntry==='up')target.before(row);else target.after(row);column.scrollTop+=row.getBoundingClientRect().top-top;[ids[index],ids[next]]=[ids[next],ids[index]];persist(section,ids);});
  $$('[data-entry-details]',root).forEach(details=>details.ontoggle=()=>{const body=$('[data-entry-editor]',details);if(!details.open||body.childElementCount)return;const section=details.closest('[data-category-choice]'),item=application.decisions.find(i=>i.group_id===section.dataset.groupChoice),entry=(item.catalog||item.options).find(e=>e.id===details.dataset.entryDetails);body.innerHTML=entry.eligibility==='outside_scope'?entry.choices.filter(c=>c.content).map(c=>`<p>${escapeHtml(c.field.label)}：${escapeHtml(c.content)}</p>`).join(''):entryEditors(entry,item)+(entry.scope_fields||[]).map(fid=>entry.choices.find(c=>c.field.id===fid)).filter(Boolean).map(c=>versionEditor(c,entry.id,item)).join('');bindPreparation();});
  $$('[data-catalog-version]',root).forEach(select=>select.onchange=()=>{$('[data-description-summary]',select.closest('.prep-version')).textContent=[...state.versions,...state.answer_versions].find(v=>v.id===select.value)?.content||'';});
  $$('[data-prep-version],[data-version-select]',root).forEach(select=>select.onchange=safe(async()=>{
    const block=select.closest('[data-answer-ref]'),ref=JSON.parse(block.dataset.answerRef),row=select.closest('[data-choice-entry]');
    if([...answerDrafts.keys()].some(key=>key.startsWith(sessionId+'/'+ref.group_id+'/'+ref.entry_id+'/')))throw Error('本段有未保存的修改，请先选择保存方式。');
    const version=[...state.versions,...state.answer_versions].find(v=>v.id===select.value);
    if(row){const summary=$('[data-description-summary]',row);if(summary&&ref.field_id===version?.field_id)summary.textContent=version.content;
      $$('[data-prep-version]',row).forEach(s=>{if(JSON.parse(s.dataset.answerRef).field_id===ref.field_id)s.value=select.value;});
      $$('[data-answer-ref]',row).forEach(b=>{if(JSON.parse(b.dataset.answerRef).field_id!==ref.field_id)return;const input=$('[data-version-content]',b),pick=$('[data-version-select]',b);if(input){input.value=version?.content||'';input.dataset.applied=input.value;}if(pick)pick.value=select.value;});}
    queuePreparation('version/'+ref.group_id+'/'+ref.entry_id+'/'+ref.field_id,'/api/website/version',{...ref,version_id:select.value});
  }));
  $$('[data-group-mode]',root).forEach(button=>button.onclick=safe(async()=>{
    if(preparationQueue().busy(sessionId))throw Error('本次选择正在保存，请稍候。');
    const blocks=$$('[data-answer-ref]',button.closest('[data-question-group]')).filter(b=>{const ref=JSON.parse(b.dataset.answerRef);return $('[data-missing-value]',b)&&answerDrafts.has(draftKey(ref));});
    if(!blocks.length)throw Error('请先填写这组缺少的信息。');button.dataset.saving='true';button.disabled=true;
    try{for(const block of blocks){const ref=JSON.parse(block.dataset.answerRef);await api('/api/website/answer',preparationAnswerBody(ref,$('[data-missing-value]',block).value,button.dataset.groupMode));answerDrafts.delete(draftKey(ref));}await refresh();toast('这组补充已保存');}finally{delete button.dataset.saving;updatePreparationProgress();}
  }));
  $$('[data-reuse-answer]',root).forEach(button=>button.onclick=safe(async()=>{const ref=JSON.parse(button.closest('[data-answer-ref]').dataset.answerRef);await api('/api/website/answer',preparationAnswerBody(ref,button.dataset.reuseAnswer,'session'));answerDrafts.delete(draftKey(ref));await refresh();}));
  $$('[data-defer-key]',root).forEach(button=>button.onclick=()=>{const ref=JSON.parse(button.closest('[data-answer-ref]').dataset.answerRef);answerDrafts.delete(draftKey(ref));queuePreparation('defer/'+button.dataset.deferKey,'/api/preparation/defer',{key:button.dataset.deferKey,deferred:button.dataset.deferred==='true'});});
  if($('#prep-attachment'))$('#prep-attachment').onchange=event=>{if(event.target.value!=='__undecided')queuePreparation('attachment','/api/preparation/settings',{file_id:event.target.value});};
  root.oninput=()=>updatePreparationProgress();
}
function focusPreparationTask(key){
  const node=key==='attachment'?$('#prep-attachment'):$$('[data-missing-key]').find(e=>e.dataset.missingKey===key);
  if(!node)return;for(let parent=node.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
  node.scrollIntoView({behavior:'smooth',block:'center'});const input=$('input,select,textarea',node)||node;input.focus({preventScroll:true});
}
function renderPreparation(analysis) {
  const root=$('#form-analysis'),same=root.dataset.session===sessionId;
  const leftScroll=same?$('.decision-column',root)?.scrollTop||0:0,previewScroll=same?$('#prep-live-preview')?.scrollTop||0:0;
  const expanded=new Set(same?$$('[data-expansion-key]',root).filter(e=>e.open).map(e=>e.dataset.expansionKey):[]);root.dataset.session=sessionId;
  const matched=!!application.website,required=application.missing.filter(i=>i.blocking),optional=application.missing.filter(i=>!i.blocking);
  const excludedFiles=application.website?.excluded_file_ids||[],automaticSets=application.automatic.filter(i=>i.website_field.collection&&i.selected.length);
  root.innerHTML=`<div class="prep-heading"><div><h2>${escapeHtml(analysis.title)}</h2></div><span class="verified-role">${matched?'✓ 已按官网问题匹配资料':'等待完成资料匹配'}</span></div>${matched?`
    <div class="prep-layout"><div class="decision-column">
      <div class="column-label"><span>01</span><div><h3>本次使用的资料</h3><p>已有信息自动带入，只处理本次取舍与真实缺项。</p></div></div>
      <section class="card auto-composition"><h3>已自动准备</h3><p>基础资料 ${application.automatic.filter(i=>!i.website_field.collection&&i.value).length} 项${automaticSets.map(i=>' · '+escapeHtml(i.website_field.label)+' '+i.selected.length+' 段').join('')}</p>${automaticSets.map(i=>`<div><strong>${escapeHtml(i.website_field.label)}</strong><p>${escapeHtml(i.requirement.summary)}</p>${i.selected.map(e=>`<p class="auto-member">✓ ${escapeHtml(entryTitle(e))}</p>`).join('')}</div>`).join('')}<small>每段的学校、专业、日期、学历和学位来自同一条资料；具体填写值见右侧。</small></section>
      <div id="prep-decisions">${application.decisions.map(preparationDecision).join('')}</div>
      <section class="card attachment-card"><h3>简历附件</h3><select id="prep-attachment" aria-label="本次简历附件"><option value="__undecided">选择本次使用的简历</option><option value="" ${preparationState.attachment_decided&&!preparationState.attachment_id?'selected':''}>本次不上传</option>${state.files.filter(f=>!excludedFiles.includes(f.id)).map(f=>`<option value="${f.id}" ${f.id===preparationState.attachment_id?'selected':''}>${escapeHtml(f.name)}</option>`).join('')}</select><p>选择原件，或选择本次不上传。</p></section>
      <section class="card" id="prep-needed"><div class="section-heading"><h3>还需处理</h3><span id="prep-needed-count" class="count-badge">${required.length}</span></div><p>按经历补齐；也可以明确留到官网本人填写。</p><div id="prep-needed-body">${preparationMissingGroups(required)||'<p class="all-ready">已有资料已匹配，无需补充。</p>'}</div></section>
      <details class="card" data-expansion-key="optional"><summary>可选补充 · 不影响确认填写 <span>${optional.length} 项</span></summary><div id="prep-optional-body">${preparationMissingGroups(optional)}</div></details>
      <details class="card" data-expansion-key="automatic"><summary>查看或修改自动带入的资料</summary>${application.automatic.map(preparationAutomatic).join('')}</details>
    </div><aside class="preview-column"><div class="column-label"><span>02</span><div><h3>本次填写预览</h3><p>核对以下内容，一次确认后交给插件填写。</p></div><button id="prep-preview" class="text-button">放大预览 ↗</button></div>
      <section class="preview-paper"><div class="preview-paper-heading"><strong>实际将填入官网的内容</strong><span id="preview-save-state" role="status">选择已保存</span></div><div id="prep-live-preview" class="live-preview">${preparationPreviewBody(preparationState.current)}</div><div class="preview-actions"><p id="prep-start-hint" aria-live="polite"></p><div id="prep-readiness"></div><button id="prep-retry-save" hidden>重试保存选择</button><button id="prep-confirm-inline" class="primary wide">确认填写 →</button><small>自动填写并检查保存；最终提交由你在官网完成。</small></div></section>
    </aside></div>`:`<section class="card prep-unmatched"><h3>正在准备本次材料</h3><p>${escapeHtml(preparationState.scan_error||'官网字段已读取，正在由模型理解问题并匹配资料。')}</p><button id="prep-match" class="primary">重新匹配资料</button></section>`}
    <details class="prep-scan" data-expansion-key="scan"><summary>查看网站要求与模型对应</summary><p>${escapeHtml(application.website?.engine||'')}</p>${(application.website?.mappings||[]).map(m=>`<p>${escapeHtml(application.website.fields.find(f=>f.id===m.website_id)?.label||'')}：${escapeHtml(m.reason||'')}</p>`).join('')}<button id="prep-rematch">重新理解官网要求</button></details>
    <dialog id="prep-preview-dialog" class="large-dialog" aria-labelledby="prep-preview-title"><div class="dialog-heading"><h2 id="prep-preview-title">本次填写预览</h2><button id="prep-close-preview" aria-label="关闭填写预览">×</button></div><div id="prep-preview-content"></div><div class="dialog-footer"><button id="prep-back">返回修改</button><button class="primary" id="prep-confirm">确认填写</button></div></dialog>`;
  bindPreparation();
  $$('[data-expansion-key]',root).forEach(e=>e.open=expanded.has(e.dataset.expansionKey));
  if($('.decision-column',root))$('.decision-column',root).scrollTop=leftScroll;
  if($('#prep-live-preview'))$('#prep-live-preview').scrollTop=previewScroll;
  if($('#prep-confirm-inline'))$('#prep-confirm-inline').onclick=safe(confirmPreparation);
  if($('#prep-retry-save'))$('#prep-retry-save').onclick=()=>preparationQueue().retry(sessionId);
  for(const id of ['#prep-match','#prep-rematch'])if($(id))$(id).onclick=safe(async()=>{requireSavedPreparation(root);const button=$(id);button.disabled=true;button.textContent='模型正在理解官网要求…';try{await api('/api/preparation/match',{session_id:sessionId});await refresh();}finally{button.disabled=false;}});
  if($('#prep-preview'))$('#prep-preview').onclick=safe(async()=>{
    requireSavedPreparation(root);const preview=await api('/api/preparation/preview',{session_id:sessionId});
    $('#prep-preview-content').innerHTML=preparationPreviewBody(preview);
    $('#prep-confirm').onclick=safe(async()=>{$('#prep-preview-dialog').close();await confirmPreparation();});
    $('#prep-close-preview').onclick=$('#prep-back').onclick=()=>$('#prep-preview-dialog').close();updatePreparationProgress();$('#prep-preview-dialog').showModal();
  });updatePreparationProgress();
}

let confirmingPreparation=false,executionError='';
function showExecutionDialog(){updatePreparationProgress();if(!$('#execution-dialog').open)$('#execution-dialog').showModal();}
async function confirmPreparation(){
  if(confirmingPreparation)return;
  requireSavedPreparation($('#form-analysis'));confirmingPreparation=true;executionError='';
  const selected=sessionId;
  try{
    const fresh=await api('/api/preparation/preview',{session_id:selected});
    if(fresh.digest!==preparationState.current?.digest){await refresh();throw Error('资料已更新，请核对右侧最新预览。');}
    if(fresh.pending.length)throw Error('请先处理左侧待补充项');
    showExecutionDialog();
    // A read-only controller intentionally rejects filling. A new material
    // confirmation must reconnect in prepare mode before queueing its values.
    if(preparationState.execution?.verification_only)await launchBrowser('prepare',true);
    else if(!preparationState.executor?.connected)await launchBrowser();
    const execution=await api('/api/preparation/start',{session_id:selected,digest:fresh.digest});
    if(selected===sessionId){preparationState.execution=execution;updatePreparationProgress();}
  }catch(error){executionError=error.message;updatePreparationProgress();throw error;}
  finally{confirmingPreparation=false;updatePreparationProgress();}
}
function updatePreparationProgress(){
  const execution=confirmingPreparation?null:preparationState.execution,pending=preparationState.current?.pending||[];
  const total=(execution?.confirmed_materials?.rows||preparationState.current?.rows||[]).reduce((n,row)=>n+(row.records?row.records.reduce((sum,record)=>sum+record.values.filter(v=>v.value!==''&&v.value!=null).length,0):row.value?1:0),0);
  const active=['awaiting_executor','running'].includes(execution?.status),finished=!!execution&&!active;
  const preserve=!!execution?.confirmed_materials?.preserve_unsaved_page,readyCurrent=finished&&preserve&&execution.verified===total&&(!execution.confirmed_materials?.attachment||execution.attachment_verified);
  const readOnly=!!execution?.verification_only||!!execution?.confirmed_materials?.verification_only;
  const checkedReadOnly=finished&&readOnly&&total>0&&execution.verified===total&&(!execution.confirmed_materials?.attachment||execution.attachment_verified)&&!execution.issues?.length;
  const dirty=[...answerDrafts.keys()].some(key=>key.startsWith(sessionId+'/'))||$$('[data-version-content]',$('#form-analysis')).some(e=>e.value!==e.dataset.applied);
  for(const id of ['#prep-confirm-inline','#prep-confirm'])if($(id))$(id).disabled=!!pending.length||active||dirty||confirmingPreparation||!!preparationSaves?.busy(sessionId);
  for(const button of $$('[data-group-mode]'))button.disabled=!!preparationSaves?.busy(sessionId)||button.dataset.saving==='true';
  const save=preparationSaves?.state(sessionId),saving=save&&(save.running||save.pending.size),tasks=preparationState.current?.tasks||[];
  if($('#preview-save-state'))$('#preview-save-state').textContent=save?.error?'保存失败，选择仍保留':saving?'正在保存本次选择…':dirty?'有尚未保存的编辑':'选择已保存 · 预览已更新';
  if($('#prep-retry-save'))$('#prep-retry-save').hidden=!save?.error;
  if($('#prep-start-hint'))$('#prep-start-hint').textContent=save?.error?'选择未保存，请重试后确认。':saving?'正在同步预览，请稍候。':dirty?'有编辑尚未保存，请在对应内容下选择保存方式。':pending.length?`还需处理 ${pending.length} 项，点击下方可定位。`:active?'正在填写，可查看进度。':`已准备 ${total} 项，核对预览后即可确认填写。`;
  if($('#prep-readiness')){
    const markup=tasks.map(t=>`<button class="readiness-task" data-focus-task="${escapeHtml(t.key)}">${escapeHtml(t.label)} <span>去处理 →</span></button>`).join('')+(preparationState.current?.manual?.length?`<p class="manual-summary">${preparationState.current.manual.length} 项已留给你在官网填写，插件会跳过。</p>`:'');
    if($('#prep-readiness').innerHTML!==markup){$('#prep-readiness').innerHTML=markup;$$('[data-focus-task]').forEach(b=>b.onclick=()=>focusPreparationTask(b.dataset.focusTask));}
  }
  if($('#prep-preview-connection'))$('#prep-preview-connection').textContent='确认后自动连接本次岗位并填写；最终由你在官网提交。';
  $('#show-execution').hidden=!execution;
  let phase=execution?.phase|| (execution?.status==='awaiting_executor'?'connecting':active?'filling':['complete','needs_attention'].includes(execution?.status)?'review':execution?.filled?'filling':'connecting');
  const order=['connecting','filling','saving','verifying','review'],index=order.indexOf(phase);
  const completed=[index>0,!!execution&&total>0&&execution.verified>=total,!!execution?.saved&&!!execution?.persistence_verified,!!execution?.saved&&!!execution?.persistence_verified,false];
  $$('#execution-steps li').forEach((li,i)=>{li.classList.toggle('done',i<index&&completed[i]);li.classList.toggle('incomplete',finished&&i<index&&!completed[i]);li.classList.toggle('active',i===index);if(i===index)li.setAttribute('aria-current','step');else li.removeAttribute('aria-current');});
  $('#execution-title').textContent=executionError?'本次填写需要处理':active||confirmingPreparation?(readOnly?'正在核对官网资料':'正在为你填写'):execution?.status==='failed'?'填写遇到阻碍':execution?.status==='paused'?'填写已暂停':finished?(readyCurrent?'资料已填好，请在当前官网提交':execution.saved&&execution.persistence_verified?'草稿已保存，请到官网确认':checkedReadOnly?'当前资料已核对，请到官网确认':'还有内容未完成，请检查下方事项'):'准备自动填写';
  const connectionNotice=execution?.status==='awaiting_executor'&&['needs_user','failed'].includes(preparationState.browser?.status)?preparationState.browser.message:'';
  $('#execution-current').textContent=executionError||connectionNotice||(confirmingPreparation?'正在自动连接本次官网':(execution?.saved&&!execution?.persistence_verified?'此前收到暂存提示，但没有重新打开核对；保存结果尚未确认。':execution?.message)||preparationState.browser?.message||'正在连接本次官网');
  $('#execution-counts').textContent=execution?`本轮写入 ${execution.filled||0} 项 · 页面已核对 ${execution.verified||0}${total?' / '+total:''} 项${execution.attachment_verified?' · 附件已确认':''}${execution.persistence_verified?' · 重新打开后保留 '+(execution.persisted||0)+' / '+(execution.expected_count||total)+' 项':preserve?' · 官网不保留草稿，请勿刷新':execution.save_acknowledged||execution.saved?' · 保存尚待核对':' · 尚未确认保存'}`:'';
  const currentSession=typeof state==='undefined'?null:state.sessions?.find(s=>s.id===sessionId);
  const siteTitle=currentSession?.website?.title||execution?.confirmed_materials?.title||'';
  const roleTitle=currentSession?.target?.title||currentSession?.name||'';
  const siteName=siteTitle.replace(/^投递简历\s*[-–·]\s*/,'').replace(/(?:校园招聘门户|校招官网|招聘门户|招聘官网)$/,'').trim();
  $('#execution-target').textContent=[siteName||siteTitle,roleTitle].filter((v,i,a)=>v&&a.indexOf(v)===i).join(' · ');
  $('#execution-official').textContent=siteName&&siteName.length<=16?'去'+siteName+'官网确认':'去本次官网确认';
  const file=execution?.confirmed_materials?.attachment;
  $('#execution-attachment').hidden=!file;
  $('#execution-attachment').textContent=file?(execution.attachment_verified&&execution.persistence_verified?'已保存到官网「简历附件」：'+file.name:execution.attachment_verified?(preserve?'所选原件已上传至当前官网：':readOnly?'当前官网附件已核对：':'附件已显示，正在检查是否保存：')+file.name:'附件尚未确认保存：'+file.name):'';
  $('#execution-issues').innerHTML=[...new Set((execution?.issues||[]).map(readableIssue))].map(t=>`<li>${escapeHtml(t)}</li>`).join('');
  $('#execution-return').hidden=active||confirmingPreparation;$('#execution-pause').hidden=!active;$('#execution-official').hidden=!finished&&!executionError&&preparationState.browser?.status!=='needs_user';
  $('.execution-monitor').classList.toggle('running',active||confirmingPreparation);
}
setInterval(async()=>{
  if(typeof currentView==='undefined'||currentView!=='practice'||!sessionId)return;
  try{const selected=sessionId,latest=await api('/api/preparation?session='+encodeURIComponent(selected));if(selected!==sessionId||currentView!=='practice')return;preparationState={...latest,current:preparationState.current};updatePreparationProgress();}catch{}
},1200);
