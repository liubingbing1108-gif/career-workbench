const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let state, materials, application, increments, selectedCategory = 'basic', sessionId, preview, currentView = 'profile';
let toastTimer;
const answerDrafts = new AnswerDrafts(localStorage, (path, body)=>api(path, body), ()=>{if(typeof preparationState!=="undefined"&&preparationState)updatePreparationProgress();});
let profileGroups = [];
let preparationState = {};
const initialCategory = location.hash.match(/^#profile\/([\w-]+)$/)?.[1];
if (initialCategory) selectedCategory = initialCategory;

function recordUsesVersions(entry){const stored=profileLibrary.library.records.find(e=>e.id===entry?.id);return stored?!!stored.versions_enabled:['employment','projects','campus','preferences','subjective'].includes(entry?.category);}
function versionsFor(entryId, fieldId) {
  entryId=profileLibrary.library.records.find(e=>e.id===entryId)?.source_entry_id||entryId;
  return [...state.versions, ...(state.answer_versions || [])].filter(v => v.entry_id === entryId && v.field_id === fieldId);
}
function versionName(version) {
  const stored = [...state.versions, ...(state.answer_versions || [])].find(v => v.id === version.id) || version;
  const versions = versionsFor(stored.entry_id, stored.field_id);
  const number = Math.max(0, versions.findIndex(v => v.id === stored.id)) + 1;
  const name = String(stored.name || '').trim();
  const generated = !name || /\.(pdf|docx?|txt)(?:\b|$)/i.test(name) ||
    (stored.source?.filename && name.includes(stored.source.filename)) ||
    /^(已确认版本|手填版本|手填描述|新描述版本|新版本|官网补充版本)$/.test(name);
  return generated ? '版本' + number : name.replace(/^版本\s+(\d+)$/, '版本$1');
}
async function api(path, data) {
  const response = await fetch(path, data === undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || '请求失败');
  return body;
}
function toast(message, error = false) {
  clearTimeout(toastTimer); $('#toast').textContent = message; $('#toast').classList.toggle('error',error); $('#toast').hidden = false;
  toastTimer = setTimeout(() => $('#toast').hidden = true, 6000);
}
function safe(fn) { return async (...args) => { try { await fn(...args); } catch (error) { toast(error.message,true); } }; }
let refreshRevision=0;
async function refresh() {
  const revision=++refreshRevision,latest=await api('/api/state');
  if(revision!==refreshRevision)return;
  const requestedSession=location.hash.match(/^#practice\/([\w-]+)$/)?.[1];
  const remembered=localStorage.getItem('profile-lab-session');
  const selected=latest.sessions.find(s=>s.id===requestedSession)?.id||latest.sessions.find(s=>s.id===sessionId)?.id||latest.sessions.find(s=>s.id===remembered)?.id||latest.sessions[0]?.id;
  const [groups,newIncrements,newMaterials,newApplication,newPreparation,library]=await Promise.all([
    api('/api/profile-groups'),api('/api/increments'),
    selected?api('/api/materials?session='+encodeURIComponent(selected)):Promise.resolve({}),
    selected?api('/api/application?session='+encodeURIComponent(selected)):Promise.resolve({website:null,automatic:[],decisions:[],missing:[]}),
    selected?api('/api/preparation?session='+encodeURIComponent(selected)):Promise.resolve({}),
    api('/api/profile/library').catch(error=>({loadError:error.message}))
  ]);
  if(newApplication.website&&latest.sessions.find(s=>s.id===selected)?.form_analysis)newPreparation.current=await api('/api/preparation/current?session='+encodeURIComponent(selected));
  if(revision!==refreshRevision)return;
  answerDrafts.hydrate(selected,newPreparation.drafts||{});
  state=latest;profileGroups=groups;increments=newIncrements;materials=newMaterials;application=newApplication;preparationState=newPreparation;sessionId=selected;
  if(!library.tree?.nodes.some(c=>c.id===selectedCategory)&&!state.categories.some(c=>c.id===selectedCategory))selectedCategory='basic';
  if(sessionId)localStorage.setItem('profile-lab-session',sessionId);else localStorage.removeItem('profile-lab-session');
  profileLibraryLoadError=library.loadError||'';
  if(!profileLibraryLoadError)profileLibrary.hydrate(library);
  renderProfile();renderPractice();
}
function control(field, value, attrs = '') {
  const escaped = escapeHtml(value);
  if (['multiline','versioned_text'].includes(field.type)) return `<textarea ${attrs}>${escaped}</textarea>`;
  if (field.type === 'select') return `<select ${attrs}><option value="">留空</option>${field.options.map(x=>`<option value="${escapeHtml(x)}" ${x===value?'selected':''}>${escapeHtml(x)}</option>`).join('')}</select>`;
  return `<input type="${field.type==='date'?'date':field.type==='number'?'number':'text'}" value="${escaped}" ${attrs}>`;
}
let profileLibraryLoadError='';
function renderProfile(){
  if(profileLibraryLoadError){
    $('#category-nav').replaceChildren();$('#profile-add-controls').replaceChildren();$('#profile-foot').replaceChildren();
    $('#category-title').textContent='我的资料';$('#category-description').textContent='';
    $('#profile-fields').innerHTML='<p role="status">资料页暂时无法读取，请稍后重试。已保存资料和本次投递仍保留。</p>';
    return;
  }
  profileLibrary.render();
}
function showView(view) {
  currentView=view;
  window.dispatchEvent(new CustomEvent('workbench:view-change',{detail:view}));
  document.body.classList.toggle('practice-active',view==='practice');
  document.body.classList.toggle('management-active',view==='management');
  for(const name of ['profile','practice','management']){
    $('#'+name+'-view').hidden=view!==name;
    const nav=$('#view-'+name),selected=view===name||(view==='practice'&&name==='management');
    if(nav){nav.classList.toggle('active',selected);nav.setAttribute('aria-current',selected?'page':'false');}
  }
  if(view==='management'){
    const frame=$('#management-frame');if(!frame.getAttribute('src'))frame.src=frame.dataset.src;
    else frame.contentWindow.postMessage({type:'workbench:jobs-changed'},location.origin);
  }
  history.replaceState(null,'',view==='practice'?(sessionId?'#practice/'+sessionId:'#practice'):view==='profile'?'#profile/'+selectedCategory:'#management');
}
$('#view-profile').onclick=()=>showView('profile');
$('#archive-profile').onclick=()=>{profileLibrary.archive=!profileLibrary.archive;renderProfile();};
$('#pending-profile').onclick=()=>openPreview();
$('#profile-search').oninput=e=>{profileLibrary.search=e.target.value;renderProfile();};
$('#expand-profile').onclick=()=>{$$('[data-library-record],[data-file-card]').forEach(e=>{e.open=true;profileLibrary.open.add(e.dataset.libraryRecord||'file:'+e.dataset.fileCard);});};
$('#collapse-profile').onclick=()=>{$$('[data-library-record],[data-file-card]').forEach(e=>{e.open=false;profileLibrary.open.delete(e.dataset.libraryRecord||'file:'+e.dataset.fileCard);});};
$('#view-management').onclick=()=>showView('management');
$$('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
$('#resume-file').onchange=safe(async event=>{
  const files=[...event.target.files];if(!files.length)return;
  if(files.some(file=>file.size>8*1024*1024))throw new Error('每份简历最多 8 MiB');
  event.target.disabled=true;$('#upload-progress').hidden=false;
  const completed=[],errors=[];
  try{
    for(const [index,file] of files.entries()){
      $('#upload-progress').textContent=`正在上传 ${index+1}/${files.length}：${file.name}，识别将在后台继续。`;
      const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
      try{completed.push(await api('/api/import',{filename:file.name,base64:encoded,async:true}));}
      catch(error){errors.push(file.name+'：'+error.message);}
    }
    await refresh();await pollImportTasks();
    const first=completed[0]||state.imports.at(-1);
    if(first)openPreview(state.imports.find(p=>p.id===first.id)||first);
    $('#upload-progress').textContent=`已上传 ${completed.length}/${files.length} 份，可查看解析进度与原文预览。`+(errors.length?' '+errors.join('；'):'');
  }finally{event.target.value='';event.target.disabled=false;}
});
function importCandidateMarkup(c, grouped=false) {
  const newField=state.profile_contract===30&&!state.fields.some(f=>f.id===c.field_id)?`<label><input type="checkbox" data-confirm-new-field>已检查字段目录，确认“${escapeHtml(c.label)}”是此对象的新属性</label>`:'';
  return `<div class="candidate ${grouped?'set-field':''}" data-candidate="${c.id}">${grouped?'':`<input type="checkbox" data-import-scalar aria-label="选择增量 ${escapeHtml(c.label)}" ${c.selected?'checked':''}>`}<div class="candidate-title">${escapeHtml(c.label)}<span class="tag">${escapeHtml(({事实冲突:'新的答案，与默认不同',描述待检查:'新增描述版本'})[c.status]||c.status)}</span></div><div>${control({type:c.type,options:state.fields.find(f=>f.id===c.field_id)?.options||c.definition?.options||[]},c.value,`aria-label="预览 ${escapeHtml(c.label)}" data-candidate-value`)}${c.existing?`<div class="existing">当前默认：${escapeHtml(c.existing)}</div><label>替换哪个版本<select data-replace-version>${c.existing_versions.map(v=>`<option value="${v.id}" ${v.id===c.default_version_id?'selected':''}>${escapeHtml(versionName(v))}</option>`).join('')}</select></label>`:''}${newField}</div></div>`;
}
function skillImportMarkup(unit,title){
  const rows=unit.rows,c=rows[0],task=state.imports.find(p=>p.id===c.import_id),reviewPending=task?.review_contract&&!task.review_completed,variants=c.representation_versions||[],conflicts=c.conflict_fields||[],blocked=rows.some(r=>r.validation_issues?.length);
  const identity=c.identity_review?`<div class="notice identity-review"><p>先确认是否同一条资料：${escapeHtml(c.identity_reason||'对象归属尚不确定')}</p><select data-identity-choice aria-label="选择已有资料或独立记录"><option value="">请选择</option><option value="__new">不同，是独立资料</option>${(c.identity_options||[]).map(v=>`<option value="${escapeHtml(v.id)}">同一条：${escapeHtml(v.label)}</option>`).join('')}</select><button data-confirm-identity="${c.id}">确认归属</button></div>`:'';
  const currentProfile=state.profile_contract===30,canVersion=['employment','projects'].includes(unit.category);
  const previous=variants.length?`<details open><summary>已有版本（A）</summary>${variants.map(v=>`<article><strong>${escapeHtml(v.name)}</strong>${Object.entries(v.values).map(([fid,value])=>`<div class="summary-row"><span>${escapeHtml(state.fields.find(f=>f.id===fid)?.label||fid)}</span><span style="white-space:pre-wrap">${escapeHtml(value)}</span></div>`).join('')}</article>`).join('')}</details>`:'';
  const warning=conflicts.length?`<div class="notice">事实待核对：${conflicts.map(fid=>escapeHtml(rows.find(r=>r.field_id===fid)?.label||fid)).join('、')}。请核对后保留已有版，或确认采用本次事实。<label><input type="checkbox" data-confirm-facts>确认采用本次填写的事实</label></div>`:'';
  return `<section class="import-set" data-import-unit data-skill-import data-import-category="${unit.category}"><header><label><input type="checkbox" data-import-set ${rows.every(r=>r.selected)?'checked':''}>${escapeHtml(title)}</label><span class="tag">${escapeHtml(c.status)}</span></header>${identity}${warning}${currentProfile&&c.record_type==='exam'?'<label><input type="checkbox" data-confirm-exam-result>确认采用本次考试完整结果，缺失的日期、分项及证明留空</label>':''}${blocked?`<p class="notice">${rows.flatMap(r=>r.validation_issues||[]).filter((v,i,a)=>a.indexOf(v)===i).map(escapeHtml).join('；')}。此组尚不能保存。</p>`:''}${previous}<details open><summary>本次文件版本（B）</summary>${rows.map(r=>`<div class="candidate set-field" data-candidate="${r.id}"><label>${currentProfile?`<input type="checkbox" data-adopt ${r.selected?'checked':''}>采用 `:''}${escapeHtml(r.label)}</label>${control({type:r.type,options:state.fields.find(f=>f.id===r.field_id)?.options||[]},r.value,'data-candidate-value aria-label="预览 '+escapeHtml(r.label)+'"')}</div>`).join('')}</details><details><summary>查看本次对象原文与来源</summary><p>${escapeHtml(c.source?.filename||'')}</p><pre style="white-space:pre-wrap">${escapeHtml(c.object_source||'')}</pre></details><div class="button-row"><button data-unit-import="ignore">${variants.length?'保留已有版（A）':'忽略本次'}</button><button data-unit-import="replace" ${blocked||c.identity_review||reviewPending?'disabled':''}>${variants.length?'保留本次版（B）':'保存此组'}</button>${variants.length&&(!currentProfile||canVersion)?`<button data-unit-import="new" ${blocked||c.identity_review||conflicts.length||reviewPending?'disabled':''}>都保留（同一条资料的不同版本）</button>`:''}</div></section>`;
}
function importUnits(candidates) {
  const groups=new Map();
  for(const c of candidates){
    const repeatable=!!c.parser_contract||state.categories.find(cat=>cat.id===c.category)?.repeatable;
    const key=repeatable?c.import_id+'/'+c.group:c.id;
    if(!groups.has(key))groups.set(key,{key,repeatable,category:c.category,rows:[]});
    groups.get(key).rows.push(c);
  }
  return [...groups.values()];
}
function importReviewMarkup(p){
  if(!p.review_contract)return (p.warnings||[]).map(w=>`<p class="notice">${escapeHtml(w)}</p>`).join('');
  const done=p.review_completed&&!p.reviewEditing,questions=p.review_questions||[],locked=q=>p.candidates.some(c=>c.saved&&(!q.group||c.group===q.group));
  return `<section data-review-form="${escapeHtml(p.id)}" class="import-set"><h3>${done?'识别确认已完成':'识别确认与可选补充'} · ${escapeHtml(p.filename)}</h3><p>缺项可以跳过；采用解释后只更新本次识别候选，保存至资料库仍需下方确认。</p><a href="/api/files/${encodeURIComponent(p.file_id)}" target="_blank" rel="noopener">查看原PDF／Word文件</a><details><summary>清洁文本与转换原文</summary>${(p.document_blocks||[]).map(b=>`<h4>${escapeHtml(b.location)}</h4><pre style="white-space:pre-wrap">${escapeHtml(b.text)}</pre>${b.raw_text!==undefined?`<details><summary>清理前原文</summary><pre style="white-space:pre-wrap">${escapeHtml(b.raw_text)}</pre></details>`:''}`).join('')}</details>${questions.map(q=>{const answer=p.review_answers?.[q.id]||{},action=answer.action||'skip',readOnly=done||locked(q);return `<div data-review-question="${q.id}" style="padding:12px 0;border-top:1px solid #ddd"><strong>${escapeHtml(q.title)}</strong><p style="white-space:pre-wrap">${escapeHtml(q.prompt)}</p><select data-review-action aria-label="处理此疑点" ${readOnly?'disabled':''}>${[['skip','跳过，暂不补充'],['original','保留原文，不采用解释'],...(q.kind==='source'?[['confirm','已核对原件，确认此项归属']]:[]),...(q.changes.length?[['apply',q.kind==='source'?'填写更正内容并确认此疑点':'采用／填写下方内容']]:[]),['note','仅补充说明']].map(([v,l])=>`<option value="${v}" ${v===action?'selected':''}>${l}</option>`).join('')}</select>${q.changes.map(c=>`<label style="display:block">${escapeHtml(c.label)}${control({type:c.type,options:state.fields.find(f=>f.id===c.field_id)?.options||[]},answer.values?.[c.field_id]??c.value,`data-review-field="${escapeHtml(c.field_id)}" aria-label="补充 ${escapeHtml(c.label)}" ${readOnly?'disabled':''}`)}</label>`).join('')}<label style="display:block">补充说明（可空）<textarea data-review-note aria-label="补充说明" ${readOnly?'disabled':''}>${escapeHtml(answer.note||'')}</textarea></label></div>`;}).join('')}${done?'<p>已保留本次选择；跳过的内容保持原文或未知，归属未确定的对象继续待处理。</p>'+(questions.some(q=>!locked(q))?'<button type="button" data-edit-review>补充未保存对象的确认</button>':''):'<button type="button" data-complete-review>完成识别确认（未填写项跳过）</button>'}</section>`;
}
function bindImportReviewForms(){
  $$('[data-edit-review]').forEach(button=>button.onclick=()=>{const p=state.imports.find(p=>p.id===button.closest('[data-review-form]').dataset.reviewForm);p.reviewEditing=true;openPreview(p);});
  $$('[data-review-field]').forEach(input=>input.oninput=()=>{const row=input.closest('[data-review-question]');$('[data-review-action]',row).value='apply';});
  $$('[data-review-note]').forEach(input=>input.oninput=()=>{const action=$('[data-review-action]',input.closest('[data-review-question]'));if(action.value==='skip')action.value='note';});
  $$('[data-complete-review]').forEach(button=>button.onclick=safe(async()=>{
    const form=button.closest('[data-review-form]'),pid=form.dataset.reviewForm,p=state.imports.find(p=>p.id===pid);
    const answers=$$('[data-review-question]',form).filter(row=>!$('[data-review-action]',row).disabled).map(row=>({id:row.dataset.reviewQuestion,action:$('[data-review-action]',row).value,note:$('[data-review-note]',row).value,values:Object.fromEntries($$('[data-review-field]',row).map(input=>[input.dataset.reviewField,input.value]))}));
    await api('/api/import/review',{import_id:pid,revision:p.revision,answers});await refresh();openPreview(state.imports.find(p=>p.id===pid));toast('识别确认已完成，未填内容保持空缺');
  }));
}

function openPreview(result) {
  preview=result;
  const parsing=['待识别','识别中'].includes(result?.status),candidates=result?increments.candidates.filter(c=>c.import_id===result.id):increments.candidates,units=importUnits(candidates);
  $$('[data-import-mode],#select-all-import,#clear-import').forEach(button=>button.disabled=parsing);
  if(typeof renderImportTaskPreview==='function')renderImportTaskPreview();
  $('#import-summary').textContent=parsing?'正在解析，资料组生成后会自动显示':`${units.length} 组待处理 · ${increments.consistent} 项一致自动复用 · ${increments.merged} 项重复合并`;
  $('#import-warnings').innerHTML=(result?[result]:state.imports).map(p=>importReviewMarkup(p)+(p.error?`<p class="notice">${escapeHtml(p.error)}</p>`:'')).join('');
  bindImportReviewForms();
  $('#retry-import').hidden=!result?.semantic||result.candidates.some(c=>c.saved)||result.status==='识别中';
  $('#import-candidates').innerHTML=parsing?'<div class="empty">正在识别，资料组尚未生成。</div>':units.length?units.map(unit=>{
    const rows=unit.rows,first=rows[0],category=state.categories.find(cat=>cat.id===unit.category),title=first.group_title||rows.find(c=>['company','school','award_name','language_name','project_name','certificate_name','skill_name'].includes(c.field_id))?.value||category?.label;
    if(state.profile_contract===30&&!first.parser_contract)return `<section class="import-set" data-legacy-import><h3>${escapeHtml(title||'旧解析结果')}</h3><p class="notice">此结果来自旧解析契约，保留原文与已有结果。请从原文件重新识别并核对后，再保存至当前资料。</p>${rows.map(c=>`<div class="summary-row"><span>${escapeHtml(c.label)}</span><span style="white-space:pre-wrap">${escapeHtml(c.value)}</span></div>`).join('')}</section>`;
    if(first.parser_contract)return skillImportMarkup(unit,title);
    if(!unit.repeatable)return `<section data-import-unit data-import-category="${unit.category}">${importCandidateMarkup(first)}<div class="button-row">${['replace','new','ignore'].map(mode=>`<button data-unit-import="${mode}">${{replace:'替换现有版本',new:'存为新版本',ignore:'忽略'}[mode]}</button>`).join('')}</div></section>`;
    return `<section class="import-set" data-import-unit data-import-category="${unit.category}"><header><label class="checkbox-label"><input type="checkbox" data-import-set aria-label="选择资料组 ${escapeHtml(title)}" ${rows.every(c=>c.selected)?'checked':''}><strong>${escapeHtml(title)}</strong></label><span class="tag">${escapeHtml(category?.label)} · ${rows.length} 项待处理</span></header>${first.identity_review?`<div class="notice identity-review"><p>请确认这是否为已有的同一段经历／同一次获奖。</p><select data-identity-choice aria-label="选择已有资料或独立记录"><option value="">请选择</option><option value="__new">不同，是独立资料</option>${(first.identity_choices||[]).map(id=>{const e=state.entries.find(e=>e.id===id);return `<option value="${id}">同一条：${escapeHtml(profileLibrary.title(e))} · ${escapeHtml(profileLibrary.meta(e))}</option>`;}).join('')}</select><button data-confirm-identity="${first.id}">确认归属</button></div>`:''}<details><summary>查看 / 修改整组资料</summary><div class="import-set-fields">${rows.map(c=>importCandidateMarkup(c,true)).join('')}</div></details><div class="button-row">${['replace','new','ignore'].map(mode=>`<button data-unit-import="${mode}">${{replace:'整组替换现有版本',new:'整组存为新版本',ignore:'忽略整组'}[mode]}</button>`).join('')}</div></section>`;
  }).join(''):'<div class="empty">没有新增或变化内容需要处理。</div>';
  if(result&&!parsing){
    const pendingIds=new Set(candidates.map(c=>c.id)),finished=importUnits(result.candidates.filter(c=>!pendingIds.has(c.id)));
    if(finished.length)$('#import-candidates').insertAdjacentHTML('beforeend',`<details class="import-confirmed"><summary>已处理 / 已复用资料 · ${finished.length} 组</summary>${finished.map(unit=>`<section class="import-set"><strong>${escapeHtml(unit.rows[0].group_title||state.categories.find(c=>c.id===unit.category)?.label||'资料')}</strong>${unit.rows.map(c=>`<div class="summary-row"><span>${escapeHtml(c.label)}</span><span>${escapeHtml(c.value)}</span></div>`).join('')}</section>`).join('')}</details>`);
  }
  const categorySelect=$('#import-category');
  categorySelect.innerHTML='<option value="">全部类别</option>'+state.categories.filter(c=>units.some(u=>u.category===c.id)).map(c=>`<option value="${c.id}">${escapeHtml(c.label)}</option>`).join('');
  categorySelect.onchange=()=>$$('[data-import-unit]').forEach(unit=>unit.hidden=!!categorySelect.value&&unit.dataset.importCategory!==categorySelect.value);
  $('#import-count').textContent=state.profile_contract===30?'只采用勾选字段；未选内容保持不变':'按资料组保存或忽略；组内已确认的一致内容保持原样';
  $$('[data-unit-import]').forEach(b=>b.onclick=safe(()=>resolveIncrements(b.dataset.unitImport,$$('[data-candidate]',b.closest('[data-import-unit]')))));
  $$('[data-confirm-identity]').forEach(button=>button.onclick=safe(async()=>{const c=increments.candidates.find(c=>c.id===button.dataset.confirmIdentity),choice=$('[data-identity-choice]',button.closest('.identity-review')).value;if(!choice)throw Error('请选择同一条资料或独立资料');await api('/api/import/identity',{import_id:c.import_id,group:c.group,entry_id:choice==='__new'?null:choice,revision:increments.revisions[c.import_id]});const pid=preview?.id;await refresh();openPreview(state.imports.find(p=>p.id===pid));}));
  $$('[data-import-set]').forEach(box=>box.onchange=()=>$$('[data-adopt]',box.closest('[data-import-unit]')).forEach(child=>child.checked=box.checked));
  if(!$('#import-dialog').open)$('#import-dialog').showModal();
}
$('#select-all-import').onclick=()=>$$('[data-import-unit]:not([hidden]) [data-import-set],[data-import-unit]:not([hidden]) [data-import-scalar],[data-import-unit]:not([hidden]) [data-adopt]').forEach(c=>c.checked=true);
$('#clear-import').onclick=()=>$$('[data-import-unit]:not([hidden]) [data-import-set],[data-import-unit]:not([hidden]) [data-import-scalar],[data-import-unit]:not([hidden]) [data-adopt]').forEach(c=>c.checked=false);
$('#retry-import').onclick=safe(async()=>{
  $('#retry-import').disabled=true;
  try{toast('正在重新识别…');const result=await api('/api/import/retry',{import_id:preview.id,async:true});await refresh();await pollImportTasks();openPreview(result);}
  finally{$('#retry-import').disabled=false;}
});
async function resolveIncrements(mode,rows){
  if(state.profile_contract===30)rows=rows.filter(row=>!$('[data-adopt]',row)||$('[data-adopt]',row).checked);
  if(!rows.length)throw new Error('请先选择要处理的增量');
  const decisions=rows.map(row=>({candidate_id:row.dataset.candidate,mode,value:$('[data-candidate-value]',row).value,version_id:$('[data-replace-version]',row)?.value,confirm_new_field:!!$('[data-confirm-new-field]',row)?.checked,confirm_facts:!!$('[data-confirm-facts]',row.closest('[data-import-unit]'))?.checked,confirm_exam_result:!!$('[data-confirm-exam-result]',row.closest('[data-import-unit]'))?.checked}));
  const result=await api('/api/import/resolve',{decisions,revisions:increments.revisions});
  const previewId=preview?.id;await refresh();await pollImportTasks();openPreview(state.imports.find(p=>p.id===previewId));toast(`已保存 ${result.saved} 项，忽略 ${result.ignored} 项`);
  if(!increments.candidates.some(c=>!preview||c.import_id===preview.id))$('#import-dialog').close();
}
$$('[data-import-mode]').forEach(b=>b.onclick=safe(()=>resolveIncrements(b.dataset.importMode,$$('[data-import-unit]:not([hidden])').filter(unit=>$('[data-import-set],[data-import-scalar]',unit)?.checked).flatMap(unit=>$$('[data-candidate]',unit)))));

function answerRef(item, entryId, choice, childId){
  return {website_id:item.website_field.id,group_id:item.group_id,entry_id:choice?.source_entry_id||entryId,field_id:choice?.field.id,child_id:childId||choice?.child_id};
}
function draftKey(ref){return sessionId+'/'+ref.group_id+'/'+ref.entry_id+'/'+(ref.field_id||ref.child_id||ref.website_id);}
function versionEditor(choice, entryId, item){
  const ref=answerRef(item,entryId,choice),key=entryId+'/'+choice.field.id;
  return `<div class="version-block" data-answer-key="${escapeHtml(key)}" data-answer-ref="${escapeHtml(JSON.stringify(ref))}"><label>${escapeHtml(choice.field.label)}${control(choice.field,answerDrafts.get(draftKey(ref))??choice.content,`data-version-content data-applied="${escapeHtml(choice.content)}"`)}</label><div class="button-row"><button data-version-mode="session">仅供本次使用</button>${state.profile_contract===30?'<button data-single-sync>预览差异并回库</button>':''}</div></div>`;
}

function entryTitle(entry){
  const v=entry.values;
  return [v.school||v.company||v.certificate_name||v.language||v.language_name||v.award_name||v.project_name||v.name||v.person_name||v.contact_name||v.family_name||'资料记录',v.degree||v.role||v.relationship||v.relation||'',v.started||v.education_started||''].filter(Boolean).join(' · ');
}
function entryEditors(entry,item){
  if(!item.website_field.collection)return entry.choices.filter(c=>c.content).map(c=>`<div class="summary-row"><span>${escapeHtml(c.field.label)}</span><span>${escapeHtml(c.content)}</span></div>`).join('');
  const choices=entry.answer_choices||(item.mapping.members?.length?item.mapping.members.map(m=>{const c=entry.choices.find(c=>c.field.id===m.field_id);return c?{...c,child_id:m.website_id}:null;}).filter(Boolean):entry.choices);
  return choices.map(c=>versionEditor(c,entry.id,item)).join('');
}
function renderPractice(){
  window.renderMappingRelationPanel?.();
  const expanded=new Set($$('[data-expansion-key]').filter(e=>e.open).map(e=>e.dataset.expansionKey));
  $('#session-select').innerHTML=state.sessions.map(s=>`<option value="${s.id}" ${s.id===sessionId?'selected':''}>${escapeHtml(s.name)}</option>`).join('');
  $('#session-select').hidden=!state.sessions.length;
  const currentSession=state.sessions.find(s=>s.id===sessionId);
  const analysis=currentSession?.form_analysis;
  if(typeof updateTargetPanel==='function')updateTargetPanel(currentSession);
  if(!currentSession){$('#form-analysis').hidden=true;$('.target-bar').hidden=true;$('.practice-grid').hidden=true;return;}
  if(currentSession?.manual_reason||(currentSession?.target&&(!analysis||!currentSession.website||['matching','failed'].includes(preparationState.scan_status)))){$('#form-analysis').hidden=true;$('.target-bar').hidden=true;$('.practice-grid').hidden=true;return;}
  $('#form-analysis').hidden=!analysis;
  $('.target-bar').hidden=!!analysis;
  $('.practice-grid').hidden=!!analysis;
  if(analysis){renderPreparation(analysis);return;}
  $('#target-url').value=application.website?.url||$('#target-url').value;
  const seen=new Set();
  $('#version-editor').innerHTML=application.decisions.filter(item=>{if(seen.has(item.group_id))return false;seen.add(item.group_id);return true;}).map(item=>{
    const single=['one','highest'].includes(item.requirement.selection);
    return `<section data-decision="${escapeHtml(item.website_field.id)}" data-category-choice="${item.category}" data-group-choice="${escapeHtml(item.group_id)}"><h4>${escapeHtml(item.website_field.label)}</h4><p>${escapeHtml(item.requirement.summary||'选择本次需要展示的资料；已有默认版本已选好。')}</p>${single?'':`<div class="button-row"><button data-experience-all>全选经历</button><button data-experience-none>清空选择</button></div>`}${[...item.selected,...item.options.filter(e=>!item.selected.some(s=>s.id===e.id))].map(entry=>`<article class="entry-choice" data-choice-entry="${entry.id}"><label class="checkbox-label"><input type="${single?'radio':'checkbox'}" name="${escapeHtml(item.group_id)}" data-experience ${(!single||item.selected.length===1)&&item.selected.some(e=>e.id===entry.id)?'checked':''}>${escapeHtml(entryTitle(entry))}</label><details data-expansion-key="${sessionId}/${escapeHtml(item.group_id)}/${entry.id}"><summary>查看内容与版本</summary>${entryEditors(entry,item)}</details>${single?'':`<div class="button-row"><button data-move-entry="up">向上</button><button data-move-entry="down">向下</button></div>`}</article>`).join('')}</section>`;
  }).join('')||`<p>${application.website?'已按网站要求准备资料，无需逐项选择。':'读取网站要求后，只显示需要你决定的内容。'}</p>`;
  $('#materials-summary').innerHTML=application.automatic.map(item=>{
    if(item.website_field.collection)return `<section class="material-set" data-auto-group="${escapeHtml(item.group_id)}"><h4>${escapeHtml(item.website_field.label)} · ${item.selected.length} 条</h4><p>${escapeHtml(item.requirement.summary)}</p>${item.selected.map(entry=>`<details data-auto-entry="${entry.id}" data-expansion-key="${sessionId}/${escapeHtml(item.group_id)}/${entry.id}"><summary>${escapeHtml(entryTitle(entry))}</summary>${entryEditors(entry,item)}</details>`).join('')}<button data-add-material="${escapeHtml(item.website_field.id)}">补充一条资料</button></section>`;
    return `<div class="summary-row"><span>${escapeHtml(item.website_field.label)}</span><span>${escapeHtml(item.value)}</span></div>${item.choice?`<details><summary>修改本次内容</summary>${versionEditor(item.choice,item.entry_id,item)}</details>`:''}`;
  }).join('');
  $('#missing-fields').innerHTML=application.missing.map((item,index)=>{
    const field=state.fields.find(f=>f.id===item.field_id),entry=state.entries.find(e=>e.id===item.entry_id);
    const ref={website_id:item.website_field.id,group_id:item.group_id,entry_id:item.entry_id,field_id:item.field_id,child_id:item.child_id};
    const version=[...state.versions,...(state.answer_versions||[])].find(v=>v.id===entry?.default_versions?.[item.field_id]);
    const current=entry?.values[item.field_id]||version?.content||'';
    return `<div class="missing-item" data-missing="${escapeHtml(item.website_field.id)}" data-missing-index="${index}" data-answer-ref="${escapeHtml(JSON.stringify(ref))}"><strong>${escapeHtml(item.message||item.mapping.reason)}</strong>${entry?`<p>${escapeHtml(entryTitle(entry))}${field?' · '+escapeHtml(field.label):''}</p>`:''}${item.editable?`${control(field||{type:item.website_field.type==='textarea'?'multiline':item.website_field.type||'text'},answerDrafts.get(draftKey(ref))??current,'data-missing-value')}<div class="button-row"><button data-missing-mode="update">更新当前版本</button><button data-missing-mode="new">保存为新版本</button><button data-missing-mode="session">仅供本次使用</button></div>`:item.requirement&&['coverage','count'].includes(item.kind)?`<button data-add-material="${escapeHtml(item.website_field.id)}">补充一条资料</button>`:''}</div>`;
  }).join('');
  $('#fill-start').disabled=!application.website||application.missing.some(i=>i.blocking)||application.website.execution==='manual';
  $('#execution-note').textContent=application.website?.execution==='manual'?application.website.manual_reason:application.website?'确认以上资料后开始填写，并逐项回读。':'读取字段后才能开始。';
  $('#target-title').textContent=application.website?.title||'本地招聘表单';
  $('#target-source').textContent=application.website?.source||'验证网站要求、资料集合、版本和补充字段。';
  $('#mock-form').hidden=application.website?.execution==='manual';
  restoreLocalForm(application.website);
  $$('[data-expansion-key]').forEach(e=>e.open=expanded.has(e.dataset.expansionKey));
  bindChoices();
}
function bindChoices(){
  $$('[data-version-content],[data-missing-value]').forEach(input=>input.oninput=()=>{const ref=JSON.parse(input.closest('[data-answer-ref]').dataset.answerRef);answerDrafts.set(draftKey(ref),input.value);});
  async function persistChoices(section){
    await api('/api/website/choices',{session_id:sessionId,category:section.dataset.categoryChoice,group_id:section.dataset.groupChoice,entry_ids:$$('[data-choice-entry]',section).filter(row=>$('[data-experience]',row).checked).map(row=>row.dataset.choiceEntry)});await refresh();
  }
  $$('[data-experience]').forEach(input=>input.onchange=safe(()=>persistChoices(input.closest('[data-category-choice]'))));
  $$('[data-experience-all],[data-experience-none]').forEach(b=>b.onclick=safe(async()=>{const section=b.closest('[data-category-choice]');$$('[data-experience]',section).forEach(c=>c.checked=!c.disabled&&b.hasAttribute('data-experience-all'));await persistChoices(section);}));
  $$('[data-move-entry]').forEach(b=>b.onclick=safe(async()=>{const row=b.closest('[data-choice-entry]');if(b.dataset.moveEntry==='up'&&row.previousElementSibling?.matches('[data-choice-entry]'))row.previousElementSibling.before(row);if(b.dataset.moveEntry==='down'&&row.nextElementSibling?.matches('[data-choice-entry]'))row.nextElementSibling.after(row);await persistChoices(row.closest('[data-category-choice]'));}));
  $$('[data-version-select]').forEach(select=>select.onchange=safe(async()=>{
    const block=select.closest('[data-answer-ref]'),ref=JSON.parse(block.dataset.answerRef);
    if($('[data-version-content]',block).value!==$('[data-version-content]',block).dataset.applied)throw new Error('请先处理这段修改，再切换版本');
    await api('/api/website/version',{session_id:sessionId,...ref,version_id:select.value});await refresh();
  }));
  $$('[data-version-mode],[data-missing-mode]').forEach(button=>button.onclick=safe(async()=>{
    const block=button.closest('[data-answer-ref]'),ref=JSON.parse(block.dataset.answerRef),input=$('[data-version-content],[data-missing-value]',block),versionId=$('[data-version-select]',block)?.value;
    const version=[...state.versions,...state.answer_versions].find(v=>v.id===versionId);
    const mode=button.dataset.versionMode||button.dataset.missingMode;
    await answerDrafts.settled(sessionId);
    await api('/api/website/answer',{session_id:sessionId,...ref,version_id:versionId,mode,value:input.value,expected_revision:version?.revision});
    answerDrafts.delete(draftKey(ref));await answerDrafts.settled(sessionId);await refresh();toast(button.textContent+'已完成');
  }));
  $$('[data-single-sync]').forEach(button=>button.onclick=safe(async()=>{
    const block=button.closest('[data-answer-ref]'),ref=JSON.parse(block.dataset.answerRef),value=$('[data-version-content]',block).value;
    await previewSingleWriteback(ref,value);
  }));
  $$('[data-add-material]').forEach(button=>button.onclick=safe(async()=>{await api('/api/website/entry',{session_id:sessionId,website_id:button.dataset.addMaterial});await refresh();toast('已添加待补充资料，请填写相关字段');}));
}
$('#session-select').onchange=safe(async event=>{sessionId=event.target.value;history.replaceState(null,'','#practice/'+sessionId);$$('[data-rows]').forEach(e=>e.replaceChildren());$('#readback').innerHTML='';$$('[data-site] input,input[data-site]').forEach(e=>e.value='');await refresh();showView('practice');});

function localChild(label,id,type='text',required=false){return `<label>${label}<${type==='textarea'?'textarea':'input'} data-child="${id}" ${type==='textarea'?'':`type="${type}"`} ${required?'required':''}>${type==='textarea'?'</textarea>':''}</label>`;}
function restoreLocalForm(website){
  if(website?.execution!=='local'||website.contract_version!==2)return;
  if(website.demo_kind)$('#demo-kind').value=website.demo_kind;
  const fields=website.fields;
  const current=$$('[data-site]',$('#mock-form')).map(e=>[e.dataset.site,$('template',e)?$$('[data-child]',$('template',e).content).map(c=>c.dataset.child):[]]);
  const expected=fields.map(f=>[f.id,(f.children||[]).map(c=>c.id)]);
  if(JSON.stringify(current)===JSON.stringify(expected))return;
  const input=(f,attribute)=>{
    const attrs=`${attribute}="${escapeHtml(f.id)}" ${f.required?'required':''} ${f.maxLength?`maxlength="${Number(f.maxLength)}"`:''}`;
    if(f.options?.length)return `<select ${attrs}>${f.options.map(o=>`<option value="${escapeHtml(typeof o==='object'?o.value:o)}">${escapeHtml(typeof o==='object'?o.label:o)}</option>`).join('')}</select>`;
    return ['textarea','multiline','versioned_text'].includes(f.type)?`<textarea ${attrs}></textarea>`:`<input ${attrs} type="${['date','month','number','email','tel'].includes(f.type)?f.type:'text'}">`;
  };
  $('#mock-form').innerHTML=fields.map(f=>f.collection?`<section data-site="${escapeHtml(f.id)}" data-collection="${escapeHtml(website.mappings.find(m=>m.website_id===f.id)?.category||'records')}" data-required="${!!f.required}"><h4>${escapeHtml(f.label)}</h4><p>${escapeHtml(f.instructions||'')}</p><template>${(f.children||[]).map(c=>`<label>${escapeHtml(c.label)}${input(c,'data-child')}</label>`).join('')}</template><div data-rows></div></section>`:`<label>${escapeHtml(f.label)}${input(f,'data-site')}</label>`).join('');
}
function prepareLocalDemo(){
  const variant=$('#demo-kind').value;
  if(variant==='employment'){
    $('#mock-form').innerHTML=`<label>名字<input data-site="w_name" required></label><label>电子邮箱<input data-site="w_email" required></label><section data-site="w_employment" data-collection="employment" data-required="true"><h4>工作 / 实习经历</h4><p>允许选择展示哪些经历，并可新增多段；本次至少填写一段。</p><template>${localChild('公司','company')}${localChild('职位','role')}${localChild('开始日期','started')}${localChild('结束日期','ended')}${localChild('工作内容','description','textarea')}</template><div id="target-experiences" data-rows></div></section><label>最早可以入职的日期<input data-site="w_available" type="date" required></label>`;
  }else{
    const from=variant==='education-high-school'?'高中':'本科';
    $('#mock-form').innerHTML=`<section data-site="w_education" data-collection="education" data-required="true"><h4>教育经历</h4><p>请从${from}开始填写全部教育经历，按学历从低到高排列。${from==='本科'?'不包含高中经历。':''}</p><template>${localChild('学校','school','text',true)}${localChild('学历','degree','text',true)}${localChild('所学专业','major')}</template><div data-rows></div></section><label>最高学历院校<input data-site="w_highest_school" required></label><label>本科院校<input data-site="w_bachelor_school" required></label>`;
  }
}
function readLocalManifest(){
  return {url:location.origin+'/local-recruiting-form',title:'本地招聘表单 · '+$('#demo-kind').selectedOptions[0].textContent,demo_kind:$('#demo-kind').value,execution:'local',source:'从右侧表单读取实际问题、范围、子字段和必填要求，经已配置的 Agent 理解。',fields:$$('[data-site]').map(e=>{
    const field={id:e.dataset.site,label:e.closest('label')?.firstChild.textContent.trim()||$('h4',e)?.textContent.trim(),type:e.type||'collection',required:e.required||e.dataset.required==='true',collection:e.hasAttribute('data-collection'),instructions:$('p',e)?.textContent.trim()||'',section:e.hasAttribute('data-collection')?$('h4',e)?.textContent:'申请资料'};
    if(field.collection)field.children=$$('[data-child]',$('template',e).content).map(c=>({id:c.dataset.child,label:c.closest('label').firstChild.textContent.trim(),type:c.type||'textarea',required:c.required,maxLength:c.maxLength>0?c.maxLength:null}));
    return field;
  })};
}
async function scan(manifest){
  $('#scan-status').textContent='正在理解网站问题、资料范围与完整性要求…';
  await api('/api/website/scan',{session_id:sessionId,manifest});await refresh();$('#scan-status').textContent='已读取 '+manifest.fields.length+' 个问题；'+application.website.engine;
}
$('#scan-demo').onclick=safe(async()=>{prepareLocalDemo();await scan(readLocalManifest());});
$('#scan-target').onclick=safe(async()=>{
  const manifest=await (await fetch('/51job-fields.json')).json();
  const supplied=new URL($('#target-url').value||manifest.url);
  if(supplied.origin!==new URL(manifest.url).origin||supplied.pathname!==new URL(manifest.url).pathname||supplied.searchParams.get('_jobId')!==new URL(manifest.url).searchParams.get('_jobId'))throw new Error('离线演练只使用虚构示例链接；真实申请请从投递管理开始');
  await scan(manifest);
});
function setInput(input,value){const proto=input.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:input.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;Object.getOwnPropertyDescriptor(proto,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));return input.value;}
$('#fill-start').onclick=safe(async()=>{
  if($$('[data-version-content]').some(input=>input.value!==input.dataset.applied&&(!input.closest('[data-choice-entry]')||$('[data-experience]',input.closest('[data-choice-entry]')).checked)))throw new Error('修改的内容还未选择保存方式，请点击更新、新版本或仅本次使用');
  const plan=await api('/api/application?session='+encodeURIComponent(sessionId));
  if(plan.website?.execution!=='local')throw new Error('此链接需要人工申请；当前执行器仅验证本地表单');
  if(plan.missing.some(i=>i.blocking))throw new Error('请先处理资料缺项或范围问题');
  $('#readback').innerHTML='';const results=[];
  const targetFor=id=>$$('[data-site]').find(e=>e.dataset.site===id);
  const setAndCheck=(input,value,label)=>{if(!input)throw new Error('表单已变化，请重新扫描');const actual=setInput(input,value);if(actual!==String(value)||!input.checkValidity())throw new Error(label+'填写后回读或网站校验未通过');results.push({label,value,actual});};
  for(const item of plan.payload){
    const site=targetFor(item.website_field.id);if(!site)throw new Error('表单已变化，请重新扫描');
    if(item.website_field.collection){
      const container=$('[data-rows]',site),template=$('template',site);if(!container||!template)throw new Error('缺少本地表单条目模板');container.replaceChildren();
      for(const [index,values] of item.value.entries()){
        const row=document.createElement('fieldset');row.dataset.filledEntry=String(index);if(site.dataset.collection==='employment')row.dataset.filledExperience=String(index);
        const legend=document.createElement('legend');legend.textContent='第 '+(index+1)+' 条';row.append(legend,template.content.cloneNode(true));container.append(row);
        for(const child of item.website_field.children||[]){
          const member=item.mapping.members.find(m=>m.website_id===child.id),key=member.field_id||child.id;
          const input=$$('[data-child]',row).find(e=>e.dataset.child===child.id);if(input)input.dataset.filledField=key;
          setAndCheck(input,values[key]??'',item.website_field.label+' '+(index+1)+' · '+child.label);
        }
      }
    }else setAndCheck(site,item.value,item.website_field.label);
  }
  $('#readback').innerHTML=results.map(r=>`<div class="readback-row"><strong>${escapeHtml(r.label)} · 已回读</strong><span class="readback-value">${escapeHtml(r.actual)}</span></div>`).join('');
  toast('按本次资料填写完成，'+results.length+' 项已回读');
});

safe(async()=>{
  await refresh();
  const health=await api('/api/health');
  showView(/^#practice\/[\w-]+$/.test(location.hash)?'practice':location.hash.startsWith('#profile/')?'profile':health.management?'management':'profile');
  document.dispatchEvent(new Event('workbench-ready'));
  const engine=await api('/api/recognition');
  if(engine.engine.includes('测试模式'))$('#recognition-status').textContent='离线带标签样例测试模式；正式识别请用默认启动方式。';
  else if(!engine.available)$('#recognition-status').textContent='未找到本机模型程序，上传失败后仍可保留原文件并手填。';
  const requested=new URLSearchParams(location.search).get('preview');
  const imported=state.imports.find(p=>p.id===requested);
  if(imported&&increments.candidates.length)openPreview(imported);
})();
