const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, x => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x]));
let state, materials, application, increments, selectedCategory = 'basic', sessionId, preview, currentView = 'profile';
let toastTimer;
const answerDrafts = new Map();
const profileVersions = new Map();
const profileDrafts = new Map();
let newVersionTarget;
let profileGroups = [];
let preparationState = {};
const expandedProfileEntries = new Set();
const initialCategory = location.hash.match(/^#profile\/([\w-]+)$/)?.[1];
if (initialCategory) selectedCategory = initialCategory;

function versionsFor(entryId, fieldId) {
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
  return generated ? '版本 ' + number : name;
}
function profileDraftKey(entry, field) {
  return entry.id + '/' + field.id + '/' + (entry.default_versions?.[field.id] || 'empty');
}
function renderProfileField(entry, field) {
  const key = entry.id + '/' + field.id;
  const versions = versionsFor(entry.id, field.id);
  const selected = versions.find(v => v.id === profileVersions.get(key)) ||
    versions.find(v => v.id === entry.default_versions?.[field.id]) || versions[0];
  const isDefault = !selected || selected.id === entry.default_versions?.[field.id];
  const value = isDefault ? profileDrafts.get(profileDraftKey(entry, field)) ?? selected?.content ?? entry.values[field.id] ?? '' : selected.content;
  const full = ['multiline', 'versioned_text'].includes(field.type);
  return `<div class="profile-field ${full ? 'full-span' : ''}" data-profile-answer-key="${key}">
    <div class="field-heading"><label for="profile-value-${entry.id}-${field.id}">${escapeHtml(field.label)}</label><button type="button" class="add-version" data-add-version data-entry="${entry.id}" data-field="${field.id}">＋ 新增版本</button></div>
    ${versions.length > 1 ? `<div class="profile-version-row"><select data-profile-version data-entry="${entry.id}" data-field="${field.id}" aria-label="${escapeHtml(field.label)}版本">${versions.map(v => `<option value="${v.id}" ${v.id === selected.id ? 'selected' : ''}>${escapeHtml(versionName(v))}${v.id === entry.default_versions?.[field.id] ? ' · 默认' : ''}</option>`).join('')}</select>${isDefault ? '' : `<button type="button" data-default-version="${selected.id}" data-entry="${entry.id}" data-field="${field.id}">设为默认</button>`}</div>` : selected ? `<div class="single-version">${escapeHtml(versionName(selected))} · 默认</div>` : ''}
    ${field.type === 'versioned_text' || !isDefault ? `<div class="version-content ${value ? '' : 'muted'}" id="profile-value-${entry.id}-${field.id}">${escapeHtml(value || '暂无内容')}</div>` : control(field, value, `id="profile-value-${entry.id}-${field.id}" data-field="${field.id}" data-entry="${entry.id}" aria-label="${escapeHtml(field.label)}"`)}
  </div>`;
}
function bindProfileFields(root = $('#profile-fields')) {
  $$('[data-profile-version]', root).forEach(select => select.onchange = () => {
    const entry = state.entries.find(e => e.id === select.dataset.entry);
    const field = state.fields.find(f => f.id === select.dataset.field);
    const key = entry.id + '/' + field.id;
    profileVersions.set(key, select.value);
    const card = select.closest('[data-profile-answer-key]');
    card.innerHTML = $("[data-profile-answer-key]", new DOMParser().parseFromString(renderProfileField(entry, field), 'text/html')).innerHTML;
    bindProfileFields(card);
  });
  $$('[data-field][data-entry]:is(input,textarea,select):not([data-profile-version])', root).forEach(input => input.oninput = () => {
    const entry = state.entries.find(e => e.id === input.dataset.entry);
    const field = state.fields.find(f => f.id === input.dataset.field);
    profileDrafts.set(profileDraftKey(entry, field), input.value);
  });
  $$('[data-add-version]', root).forEach(button => button.onclick = () => {
    const entry = state.entries.find(e => e.id === button.dataset.entry);
    const field = state.fields.find(f => f.id === button.dataset.field);
    const versions = versionsFor(entry.id, field.id);
    const selected = versions.find(v => v.id === profileVersions.get(entry.id + '/' + field.id)) || versions.find(v => v.id === entry.default_versions?.[field.id]) || versions[0];
    let number = versions.length + 1;
    while (versions.some(v => versionName(v) === '版本 ' + number)) number++;
    newVersionTarget = {entryId: entry.id, fieldId: field.id};
    $('#new-version-title').textContent = field.label + ' · 新增版本';
    $('#new-version-name').value = '版本 ' + number;
    const content = selected?.id === entry.default_versions?.[field.id] ? profileDrafts.get(profileDraftKey(entry, field)) ?? selected?.content : selected?.content;
    $('#new-version-content').innerHTML = control(field, content ?? entry.values[field.id] ?? '', 'id="new-version-value" aria-label="新版本内容" required');
    $('#new-version-error').hidden = true;
    $('#new-version-dialog').showModal();
    $('#new-version-value').focus();
  });
  $$('[data-default-version]', root).forEach(button => button.onclick = safe(async () => {
    await api('/api/default-version', {entry_id: button.dataset.entry, field_id: button.dataset.field, version_id: button.dataset.defaultVersion});
    await refresh(); toast('已设为默认版本');
  }));
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
  const [groups,newIncrements,newMaterials,newApplication,newPreparation]=await Promise.all([
    api('/api/profile-groups'),api('/api/increments'),
    selected?api('/api/materials?session='+encodeURIComponent(selected)):Promise.resolve({}),
    selected?api('/api/application?session='+encodeURIComponent(selected)):Promise.resolve({website:null,automatic:[],decisions:[],missing:[]}),
    selected?api('/api/preparation?session='+encodeURIComponent(selected)):Promise.resolve({})
  ]);
  if(newApplication.website&&latest.sessions.find(s=>s.id===selected)?.form_analysis)newPreparation.current=await api('/api/preparation/current?session='+encodeURIComponent(selected));
  if(revision!==refreshRevision)return;
  state=latest;profileGroups=groups;increments=newIncrements;materials=newMaterials;application=newApplication;preparationState=newPreparation;sessionId=selected;
  if(!state.categories.some(c=>c.id===selectedCategory))selectedCategory='basic';
  if(sessionId)localStorage.setItem('profile-lab-session',sessionId);else localStorage.removeItem('profile-lab-session');
  renderProfile();renderPractice();
}
function control(field, value, attrs = '') {
  const escaped = escapeHtml(value);
  if (['multiline','versioned_text'].includes(field.type)) return `<textarea ${attrs}>${escaped}</textarea>`;
  if (field.type === 'select') return `<select ${attrs}><option value="">留空</option>${field.options.map(x=>`<option value="${escapeHtml(x)}" ${x===value?'selected':''}>${escapeHtml(x)}</option>`).join('')}</select>`;
  return `<input type="${field.type==='date'?'date':field.type==='number'?'number':'text'}" value="${escaped}" ${attrs}>`;
}
function profileEntryTitle(entry, index = 0) {
  const values = entry.values;
  const firstNamedValue = state.fields.find(f=>f.category===entry.category && ['text','select'].includes(f.type) && values[f.id]);
  return [values.company || values.school || values.organization || values.title || values.name || (firstNamedValue && values[firstNamedValue.id]) || '第 '+(index+1)+' 条记录',
    entry.category === 'education' ? values.degree : values.role || values.major].filter(Boolean).join(' · ');
}
function profileEntryMeta(entry) {
  const v=entry.values;
  return [v.major, [v.education_started || v.started, v.graduation_date || v.ended].filter(Boolean).join(' — ')].filter(Boolean).join(' · ');
}
function groupMember(entry, index) {
  return `<li data-set-member="${entry.id}"><div><strong>${escapeHtml(profileEntryTitle(entry,index))}</strong><p>${escapeHtml(profileEntryMeta(entry))}</p></div><button type="button" data-edit-group-entry="${entry.id}">查看 / 编辑</button></li>`;
}
function profileSetComposition(set) {
  const missing = set.issues.filter(i=>i.kind==='coverage').map(i=>i.condition.values.join('／')+'（待补）');
  return [...missing, ...(set.composition?[set.composition]:[])].join('＋') || '尚无对应经历';
}
function renderProfileGroup(group, entries) {
  if(group.category==='education') {
    return `<section class="profile-group" data-profile-group="education"><div class="group-intro"><strong>教育经历组合</strong><span class="tag">由网站要求决定使用哪一组</span><p>本科、硕士等经历是组内成员；填写时整组带入，各条资料使用默认版本。</p></div><div class="education-sets">${group.sets.map(set=>`<article class="education-set" data-profile-set="${set.id}"><header><h3>${escapeHtml(set.label)}</h3><span class="tag">${set.entry_ids.length} 段经历</span></header><p class="set-composition">${escapeHtml(profileSetComposition(set))}</p><p>${escapeHtml(set.requirement.summary)}</p><ul>${set.entry_ids.map(id=>groupMember(entries.find(e=>e.id===id),entries.findIndex(e=>e.id===id))).join('')}</ul>${set.issues.filter(i=>i.kind==='coverage').map(i=>`<div class="set-gap" data-set-gap>缺少${escapeHtml(i.condition.values.join('／'))}经历 · 遇到此要求时需要补充</div>`).join('')}${set.issues.some(i=>i.kind==='scope')?'<p class="set-gap">有经历的学历待补充或待明确，尚不能确定完整组合。</p>':''}</article>`).join('')}</div>${group.unassigned_ids.length?`<div class="ungrouped-entries"><strong>尚未归入上述组合</strong><p>学历不明确或不属于这两个起填范围，资料仍保留。</p><ul>${group.unassigned_ids.map(id=>groupMember(entries.find(e=>e.id===id),entries.findIndex(e=>e.id===id))).join('')}</ul></div>`:''}<p class="group-footnote">两组引用同一份经历资料。在下方修改一条经历后，两组同步更新；实际网站若有其他范围，以读取到的要求为准。</p></section>`;
  }
  return `<section class="profile-group" data-profile-group="${group.category}"><div class="group-intro"><strong>${escapeHtml(group.label)} · 经历与答案库</strong><span class="tag">${entries.length} 条资料</span><p>${group.category==='employment'?'投递时按网站要求选择实习组合、顺序及每段的版本；要求完整工作履历时自动取齐相应经历。':'这些资料共同属于一个逻辑字段。投递时按网站要求取用；只有确实需要选择的内容才让你决定。'}</p></div><ul class="group-inventory">${entries.map(groupMember).join('')}</ul></section>`;
}
function renderProfile() {
  $('#category-nav').innerHTML = state.categories.map(cat => `<button data-category="${cat.id}" class="${cat.id===selectedCategory?'active':''}"><span>${cat.label}</span><span class="count">${cat.id==='education'?'2 组':cat.repeatable?state.entries.filter(e=>e.category===cat.id).length+' 条':state.fields.filter(f=>f.category===cat.id).length}</span></button>`).join('');
  $$('#category-nav button').forEach(b => b.onclick=()=>{selectedCategory=b.dataset.category;history.replaceState(null,'','#profile/'+selectedCategory);renderProfile();});
  const cat = state.categories.find(c => c.id===selectedCategory);
  const fields = state.fields.filter(f=>f.category===selectedCategory);
  const entries = state.entries.filter(e=>e.category===selectedCategory);
  const group = profileGroups.find(g=>g.category===selectedCategory);
  $('#category-title').textContent=cat.label;
  $('#category-description').textContent=selectedCategory==='education'?'先看整组包含哪些经历，再展开组内资料维护内容与版本。':cat.repeatable?'同一逻辑字段下集中管理全部记录，展开一条即可维护其内容和版本。':'选择版本查看内容；默认版本用于自动填写。每个字段都可以直接新增版本。';
  $('#add-field').hidden=selectedCategory==='attachments';
  if (selectedCategory==='attachments') {
    $('#profile-fields').innerHTML=state.files.length?state.files.map(f=>`<div class="file-row"><div><strong>${escapeHtml(f.name)}</strong><p>${f.size} 字节 · 保留上传原件</p></div><a href="/api/files/${f.id}" download>下载原文件</a></div>`).join(''):'<div class="empty">尚未上传附件。全表单独立存在，上传文件不会替代资料字段。</div>';
  } else if (!fields.length) {
    $('#profile-fields').innerHTML='<div class="empty">此分类已预留。点击“新增字段”添加实际招聘需要的资料项。</div>';
  } else if (!entries.length && selectedCategory!=='education') {
    $('#profile-fields').innerHTML='<div class="empty">尚无记录，可手动添加，也可从简历中提取。</div>';
  } else {
    $('#profile-fields').innerHTML=(group?renderProfileGroup(group,entries)+'<h3 class="group-records-title">组内资料与版本</h3>':'')+entries.map((entry,index)=>cat.repeatable?`<details class="entry-card grouped-entry" data-profile-entry="${entry.id}" ${expandedProfileEntries.has(entry.id)?'open':''}><summary><span>${escapeHtml(profileEntryTitle(entry,index))}<small>${escapeHtml(profileEntryMeta(entry))}</small></span><span class="entry-edit-label">内容与版本</span></summary><div class="field-grid">${fields.map(field=>renderProfileField(entry,field)).join('')}</div></details>`:`<article class="entry-card"><h3>${escapeHtml(cat.label)}</h3><div class="field-grid">${fields.map(field=>renderProfileField(entry,field)).join('')}</div></article>`).join('');
  }
  $('#profile-foot').innerHTML=(cat.repeatable?'<button id="add-entry">＋ 添加一条记录</button> ':'')+(fields.some(f=>f.type!=='versioned_text')&&entries.length&&selectedCategory!=='attachments'?'<button id="save-profile" class="primary">保存到底稿</button>':'')+(increments.candidates.length?`<div class="pending-card">${increments.candidates.length} 项新增或变化待处理<button id="open-increments">处理增量</button></div>`:'')+state.imports.filter(p=>p.status==='失败').map(p=>`<div class="pending-card">${escapeHtml(p.filename)} · 识别失败<button data-pending="${p.id}">查看并重试</button></div>`).join('');
  if($('#open-increments'))$('#open-increments').onclick=()=>openPreview();
  bindProfileFields();
  $$('[data-profile-entry]').forEach(details=>details.ontoggle=()=>{if(details.open)expandedProfileEntries.add(details.dataset.profileEntry);else expandedProfileEntries.delete(details.dataset.profileEntry);});
  $$('[data-edit-group-entry]').forEach(button=>button.onclick=()=>{
    const details=$(`[data-profile-entry="${button.dataset.editGroupEntry}"]`);
    details.open=true;expandedProfileEntries.add(button.dataset.editGroupEntry);details.scrollIntoView({block:'start',behavior:'smooth'});
  });
  if($('#add-entry')) $('#add-entry').onclick=safe(async()=>{const added=await api('/api/entries',{category:selectedCategory});expandedProfileEntries.add(added.id);await refresh();$(`[data-profile-entry="${added.id}"]`)?.scrollIntoView({block:'start',behavior:'smooth'});});
  if($('#save-profile')) $('#save-profile').onclick=safe(async()=>{
    const values=entries.flatMap(entry=>fields.filter(f=>f.type!=='versioned_text').map(field=>({field_id:field.id,entry_id:entry.id,value:profileDrafts.get(profileDraftKey(entry,field))??entry.values[field.id]??''})));
    await api('/api/profile',{values});
    entries.forEach(entry=>fields.forEach(field=>profileDrafts.delete(profileDraftKey(entry,field))));
    await refresh();toast('已保存到底稿');
  });
  $$('[data-pending]').forEach(b=>b.onclick=()=>openPreview(state.imports.find(p=>p.id===b.dataset.pending)));
}
$('#new-version-form').onsubmit=async event=>{
  event.preventDefault();
  const button=$('#save-new-version');button.disabled=true;
  try{
    const name=$('#new-version-name').value.trim(),content=$('#new-version-value').value;
    if(!name||!content.trim())throw new Error('请填写版本名称和内容');
    const existingIds=versionsFor(newVersionTarget.entryId,newVersionTarget.fieldId).map(v=>v.id);
    const result=await api('/api/versions/create',{entry_id:newVersionTarget.entryId,field_id:newVersionTarget.fieldId,content,name});
    profileVersions.set(newVersionTarget.entryId+'/'+newVersionTarget.fieldId,result.id);
    $('#new-version-dialog').close();await refresh();toast((existingIds.includes(result.id)?'内容相同，已显示 ':'已保存 ')+versionName(result));
  }catch(error){$('#new-version-error').textContent=error.message;$('#new-version-error').hidden=false;}
  finally{button.disabled=false;}
};
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
$('#view-profile').onclick=()=>showView('profile');$('#view-management').onclick=()=>showView('management');
$$('[data-close]').forEach(b=>b.onclick=()=>$('#'+b.dataset.close).close());
$('#add-field').onclick=()=>{
  $('#field-form').reset();$('#field-options-label').hidden=true;
  $('#field-category').innerHTML=state.categories.filter(c=>c.id!=='attachments').map(c=>`<option value="${c.id}">${c.label}</option>`).join('');
  $('#field-category').value=selectedCategory;$('#field-dialog').showModal();
};
$('#field-type').onchange=()=>$('#field-options-label').hidden=$('#field-type').value!=='select';
$('#field-form').onsubmit=safe(async event=>{
  event.preventDefault();
  await api('/api/fields',{label:$('#field-label').value,category:$('#field-category').value,type:$('#field-type').value,options:$('#field-options').value.split('\n').map(x=>x.trim()).filter(Boolean)});
  selectedCategory=$('#field-category').value;$('#field-dialog').close();await refresh();toast('字段已添加到全表单');
});
$('#resume-file').onchange=safe(async event=>{
  const files=[...event.target.files];if(!files.length)return;
  if(files.some(file=>file.size>8*1024*1024))throw new Error('每份简历最多 8 MiB');
  event.target.disabled=true;$('#upload-progress').hidden=false;
  const completed=[],errors=[];
  try{
    for(const [index,file] of files.entries()){
      $('#upload-progress').textContent=`正在识别 ${index+1}/${files.length}：${file.name}，完成后可预览。`;
      const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
      try{completed.push(await api('/api/import',{filename:file.name,base64:encoded}));}
      catch(error){errors.push(file.name+'：'+error.message);}
    }
    await refresh();
    const first=completed[0]||state.imports.at(-1);
    if(first)openPreview(state.imports.find(p=>p.id===first.id));
    $('#upload-progress').textContent=`已识别 ${completed.length}/${files.length} 份，尚未写入底稿。`+(errors.length?' '+errors.join('；'):'');
  }finally{event.target.value='';event.target.disabled=false;}
});
function openPreview(result) {
  preview=result;
  $('#import-summary').textContent=`${increments.candidates.length} 项增量 · ${increments.consistent} 项一致自动复用 · ${increments.merged} 项重复合并`;
  $('#import-warnings').innerHTML=state.imports.flatMap(p=>[...(p.warnings||[]),...(p.error?[p.error]:[])]).map(w=>`<p class="notice">${escapeHtml(w)}</p>`).join('');
  $('#retry-import').hidden=!result?.semantic||result.candidates.some(c=>c.saved)||result.status==='识别中';
  $('#import-candidates').innerHTML=increments.candidates.length?increments.candidates.map(c=>`<div class="candidate" data-candidate="${c.id}"><input type="checkbox" aria-label="选择增量 ${escapeHtml(c.label)}" ${c.selected?'checked':''}><div class="candidate-title">${escapeHtml(c.group_title||state.categories.find(cat=>cat.id===c.category)?.label||'')}<br>${escapeHtml(c.label)}<span class="tag">${escapeHtml(({事实冲突:'新的答案，与默认不同',描述待检查:'新增描述版本'})[c.status]||c.status)}</span></div><div>${control({type:c.type,options:state.fields.find(f=>f.id===c.field_id)?.options||c.definition?.options||[]},c.value,`aria-label="预览 ${escapeHtml(c.label)}" data-candidate-value`)}${c.existing?`<div class="existing">当前默认：${escapeHtml(c.existing)}</div><label>替换哪个版本<select data-replace-version>${c.existing_versions.map(v=>`<option value="${v.id}" ${v.id===c.default_version_id?'selected':''}>${escapeHtml(versionName(v))}</option>`).join('')}</select></label>`:''}<div class="button-row">${['replace','new','ignore'].map(mode=>`<button data-one-import="${mode}">${{replace:'替换现有版本',new:'存为新版本',ignore:'忽略'}[mode]}</button>`).join('')}</div></div></div>`).join(''):'<div class="empty">没有新增或变化内容需要处理。</div>';
  $('#import-count').textContent='仅选中的增量会按所点动作处理';
  $$('[data-one-import]').forEach(b=>b.onclick=safe(()=>resolveIncrements(b.dataset.oneImport,[b.closest('[data-candidate]')])));
  if(!$('#import-dialog').open)$('#import-dialog').showModal();
}
$('#select-all-import').onclick=()=>$$('[data-candidate] input[type=checkbox]').forEach(c=>c.checked=true);
$('#clear-import').onclick=()=>$$('[data-candidate] input[type=checkbox]').forEach(c=>c.checked=false);
$('#retry-import').onclick=safe(async()=>{
  $('#retry-import').disabled=true;
  try{toast('正在重新识别…');const result=await api('/api/import/retry',{import_id:preview.id});await refresh();openPreview(result);}
  finally{$('#retry-import').disabled=false;}
});
async function resolveIncrements(mode,rows){
  if(!rows.length)throw new Error('请先选择要处理的增量');
  const decisions=rows.map(row=>({candidate_id:row.dataset.candidate,mode,value:$('[data-candidate-value]',row).value,version_id:$('[data-replace-version]',row)?.value}));
  const result=await api('/api/import/resolve',{decisions,revisions:increments.revisions});
  await refresh();openPreview();toast(`已保存 ${result.saved} 项，忽略 ${result.ignored} 项`);
  if(!increments.candidates.length)$('#import-dialog').close();
}
$$('[data-import-mode]').forEach(b=>b.onclick=safe(()=>resolveIncrements(b.dataset.importMode,$$('[data-candidate]').filter(row=>$('input[type=checkbox]',row).checked))));

function answerRef(item, entryId, choice, childId){
  return {website_id:item.website_field.id,group_id:item.group_id,entry_id:entryId,field_id:choice?.field.id,child_id:childId||choice?.child_id};
}
function draftKey(ref){return sessionId+'/'+ref.group_id+'/'+ref.entry_id+'/'+(ref.field_id||ref.child_id||ref.website_id);}
function versionEditor(choice, entryId, item){
  const ref=answerRef(item,entryId,choice),key=entryId+'/'+choice.field.id;
  return `<div class="version-block" data-answer-key="${escapeHtml(key)}" data-answer-ref="${escapeHtml(JSON.stringify(ref))}"><label>${escapeHtml(choice.field.label)}${choice.versions.length>1?`<select data-version-select aria-label="${escapeHtml(choice.field.label)}版本">${choice.versions.map(v=>`<option value="${v.id}" ${v.id===choice.selected?.id?'selected':''}>${escapeHtml(versionName(v))}${state.entries.find(e=>e.id===entryId)?.default_versions?.[choice.field.id]===v.id?' · 默认':''}</option>`).join('')}</select>`:choice.selected?`<input type="hidden" data-version-select value="${choice.selected.id}">`:''}</label><label>本次使用内容${control(choice.field,answerDrafts.get(draftKey(ref))??choice.content,`data-version-content data-applied="${escapeHtml(choice.content)}"`)}</label><div class="button-row"><button data-version-mode="update">更新当前版本</button><button data-version-mode="new">保存为新版本</button><button data-version-mode="session">仅供本次使用</button></div></div>`;
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
    await api('/api/website/answer',{session_id:sessionId,...ref,version_id:versionId,mode,value:input.value,expected_revision:version?.revision});
    answerDrafts.delete(draftKey(ref));await refresh();toast(button.textContent+'已完成');
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
