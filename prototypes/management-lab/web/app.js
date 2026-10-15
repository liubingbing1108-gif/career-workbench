/* One local job table; input previews are temporary and never start filling. */
const $ = (s, el = document) => el.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const integration = window.ManagementIntegration;
let state = {jobs: [], stages: [], token: '', view: 'jobs', page: 1, q: '', status: '', stage: '', kind: '', sort: '', selected: new Set(), patches: {}, batch: null};
let toastTimer;
let returnFocus;
function toast(message) { const t = $('#toast'); t.textContent = message; t.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => t.hidden = true, 6500); }
async function api(path, method = 'GET', body) {
  const response = await fetch(integration.apiPath(path, window.location.search), {method, headers: {'Content-Type':'application/json', 'X-Management-Token': state.token}, body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json(); if (!response.ok) throw new Error(data.error || '操作未完成'); return data;
}
function close() { $('#overlay').hidden = true; $('#overlay').innerHTML = ''; if (returnFocus?.isConnected) returnFocus.focus(); }
function modal(title, eyebrow, content, footer, wide = false) {
  if ($('#overlay').hidden) returnFocus = document.activeElement;
  $('#overlay').innerHTML = `<section class="drawer ${wide ? 'wide' : ''}" role="dialog" aria-modal="true" aria-label="${esc(title)}"><div class="drawer-head"><div><div class="eyebrow">${esc(eyebrow)}</div><h2>${esc(title)}</h2></div><button class="quiet" data-close aria-label="关闭">✕</button></div><div class="drawer-body">${content}</div><div class="drawer-footer">${footer}</div></section>`;
  $('#overlay').hidden = false; $('[data-close]', $('#overlay')).onclick = close;
  for (const b of $('#overlay').querySelectorAll('[data-cancel]')) b.onclick = close;
  $('[data-close]', $('#overlay')).focus();
}
function link(url, label = '打开官网 ↗') {
  try { const parsed = new URL(url); if (!['https:', 'http:'].includes(parsed.protocol)) return '<span class="muted">—</span>'; }
  catch { return '<span class="muted">—</span>'; }
  return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
}
function sourceLinks(job) { return link(job.source_url,'查看来源 ↗'); }
function officialLink(job) { return job.official_url ? link(job.official_url,'官网投递 ↗')+(job.official_url_status==='verified'?'':'<div class="sub">待核验</div>') : '<span class="muted">待解析</span>'; }
function candidateRows() { return (state.batch ? state.batch.candidates : []).map(c => ({...c, ...(state.patches[c.id] || {})})); }
function visibleRows() {
  let rows = [...state.jobs];
  rows = rows.filter(r => (!state.q || (r.company + ' ' + r.role + ' ' + (r.legacy_role||'') + ' ' + r.location + ' ' + r.campaign).toLowerCase().includes(state.q.toLowerCase())) && (!state.status || r.application_status === state.status) && (!state.stage || r.recruitment_stage === state.stage) && (!state.kind || (state.kind === 'history' ? r.historical_applied : !r.historical_applied)));
  if (state.sort === 'application_date') {
    const day = r => (r.timeline || []).filter(t => t.label === '投递日期').map(t => t.day).sort().at(-1) || '';
    rows.sort((a,b) => day(b).localeCompare(day(a)));
  }
  return rows;
}
function dateSummary(row) { const timeline = row.timeline || []; if (!timeline.length) return '<span class="muted">未记录</span>'; const d = timeline.at(-1); return `<span>${esc(d.day)}</span><div class="sub">${esc(d.label)} · ${timeline.length} 个日期</div>`; }

function render() {
  $('#main').innerHTML = `<div class="page-title"><div class="module-title"><h1>投递管理</h1><p class="subtitle">管理已投递和你决定要投递的岗位。</p></div><div class="summary-line" id="list-summary" aria-live="polite"></div><button class="primary" id="new-button">＋ 录入岗位</button></div>
    <form id="intake-form" class="intake-bar"><textarea id="intake-text" aria-label="要投递的公司岗位或链接" placeholder="粘贴招聘链接，或输入：我要投递某公司的产品经理岗位"></textarea><button class="primary" id="intake-preview">解析并确认录入</button><span id="intake-note" class="small muted">仅录入已投递或你决定要投递的岗位。</span></form>
    <section class="panel"><div class="tools"><div class="search"><span>⌕</span><input id="search" placeholder="搜索公司或岗位" value="${esc(state.q)}" aria-label="搜索公司岗位"></div><select id="filter-status" aria-label="筛选投递状态"><option value="">全部投递状态</option>${['未投递','已投递'].map(s=>`<option ${state.status===s?'selected':''}>${s}</option>`).join('')}</select><select id="filter-stage" aria-label="筛选招聘进度"><option value="">全部招聘进度</option>${[...new Set([...state.stages,...state.jobs.map(j=>j.recruitment_stage)])].filter(Boolean).map(s=>`<option ${state.stage===s?'selected':''}>${esc(s)}</option>`).join('')}</select><select id="sort" aria-label="排序"><option value="">最近录入</option><option value="application_date" ${state.sort?'selected':''}>投递日期 ↓</option></select></div><div id="table-area"></div></section>`;
  renderTable();
  $('#search').oninput=e=>{state.q=e.target.value;state.page=1;renderTable();};
  for(const [id,key] of [['filter-status','status'],['filter-stage','stage'],['sort','sort']])$('#'+id).onchange=e=>{state[key]=e.target.value;state.page=1;renderTable();};
  $('#new-button').onclick=newInput;
  $('#intake-form').onsubmit=async e=>{e.preventDefault();const b=$('#intake-preview');b.disabled=true;$('#intake-note').textContent='正在解析岗位信息…';try{await previewInput($('#intake-text').value);}catch(err){toast(err.message);}finally{b.disabled=false;$('#intake-note').textContent='仅录入已投递或你决定要投递的岗位。';}};
}
function resetFilters() { state.page=1; state.q=''; state.stage=''; state.status=''; state.kind=''; }
function renderTable() {
  const all=visibleRows(),pageCount=Math.max(1,Math.ceil(all.length/20));state.page=Math.min(state.page,pageCount);
  $('#list-summary').innerHTML=integration.listStats(all,false).map(([label,n])=>`<span>${esc(label)} <strong>${n}</strong></span>`).join('');
  const rows=all.slice((state.page-1)*20,state.page*20);
  const short=(text)=>text?`<span class="table-note" title="${esc(text)}">${esc(text)}</span>`:'<span class="muted">—</span>';
  $('#table-area').innerHTML=`<div class="table-wrap"><table><thead><tr><th>公司名称</th><th>岗位名称</th><th>来源链接</th><th>官网投递链接</th><th>志愿顺序</th><th>投递状态</th><th>招聘进度</th><th>投递时间线</th><th>面试记录</th><th>复盘</th><th>操作</th></tr></thead><tbody>${rows.map(r=>`<tr data-row-id="${esc(r.id)}" tabindex="0" aria-label="查看 ${esc(r.company)} ${esc(r.role)} 详情"><td><strong>${esc(r.company)||'待补公司'}</strong></td><td><span class="role-name" title="${esc(r.role)}">${esc(r.role)||'待补具体岗位'}</span>${r.needs_review?'<div class="sub missing">请核对具体岗位</div>':''}${r.requires_preference?'<div class="sub">需人工选择志愿</div>':''}</td><td>${sourceLinks(r)}</td><td>${officialLink(r)}</td><td>${esc(r.preference_order)||'—'}</td><td><span class="tag ${r.application_status==='已投递'?'applied':'pending'}">${esc(r.application_status)}</span>${r.continuation?`<div class="sub">${esc(r.continuation.label)}</div>`:''}</td><td>${esc(r.recruitment_stage)||'—'}</td><td>${r.timeline?.length?dateSummary(r)+(r.timeline_text?short(r.timeline_text):''):r.timeline_text?short(r.timeline_text):dateSummary(r)}</td><td>${short(r.interview_notes||(r.legacy_interview_review?'原面试记录及复盘：'+r.legacy_interview_review:''))}</td><td>${short(r.review_notes)}</td><td class="operations"><button data-prepare="${esc(r.id)}" ${integration.canPrepare(r)?'':'disabled title="请补齐一个具体公司和岗位"'}>${r.continuation?'继续投递':'开始投递'}</button></td></tr>`).join('')}</tbody></table></div>${!rows.length?'<div class="empty"><h2>暂无匹配岗位</h2><p>在上方输入公司岗位或招聘链接，确认后录入。</p></div>':''}<div class="pagination"><span>共 ${all.length} 条 · 每页20条</span><div class="actions"><button id="prev" ${state.page===1?'disabled':''}>‹ 上一页</button><span>${state.page} / ${pageCount}</span><button id="next" ${state.page===pageCount?'disabled':''}>下一页 ›</button></div></div>`;
  $('#prev').onclick=()=>{state.page--;renderTable();};$('#next').onclick=()=>{state.page++;renderTable();};
  for(const b of document.querySelectorAll('[data-prepare]'))b.onclick=()=>prepareJob(state.jobs.find(r=>r.id===b.dataset.prepare),false);
  for(const row of document.querySelectorAll('[data-row-id]')){const open=()=>details(state.jobs.find(r=>r.id===row.dataset.rowId),false);row.onclick=e=>{if(!e.target.closest('button,a,input'))open();};row.onkeydown=e=>{if(e.target===row&&['Enter',' '].includes(e.key)){e.preventDefault();open();}};}
}
async function prepareJob(job) {
  try { integration.postPrepare(job, false, window); close(); }
  catch (err) { toast(err.message); }
}

function details(job) {
  const entry=(label,value)=>`<dt>${esc(label)}</dt><dd>${value||'<span class="muted">未记录</span>'}</dd>`;
  const body=`<div class="detail-company">${esc(job.company)||'待补公司'}</div><p class="detail-role">${esc(job.role||job.legacy_role)||'待补具体岗位'}</p>
    <dl class="detail-fields">${entry('投递状态',esc(job.application_status))}${entry('招聘进度',esc(job.recruitment_stage))}${job.continuation?entry('本次准备',esc(job.continuation.label)):''}${entry('工作地点',esc(job.location))}${entry('招聘批次',esc(job.campaign))}${entry('志愿顺序',esc(job.preference_order))}${entry('来源链接',sourceLinks(job))}${entry('官网投递链接',officialLink(job))}</dl>
    <section class="manual-application"><label>手动粘贴投递链接<input id="manual-application-url" type="url" placeholder="粘贴招聘网站的表单填写链接" value="${esc(job.official_url||'')}"></label><p class="small muted">用于当前公司和岗位，保留原来源链接。</p><button id="save-application-url">使用此投递链接</button><div id="application-url-error" role="status"></div></section>
    ${job.requires_preference?'<div class="callout warn">此申请涉及选择志愿，请到官网人工申请。记录中的志愿顺序不会代替官网选择。</div>':''}
    <h3>投递时间线</h3><p class="newline small">${esc(job.timeline_text||'')}</p>${job.timeline?.length?`<ol class="detail-timeline">${job.timeline.map(d=>`<li><span>${esc(d.label)}</span><time>${esc(d.day)}</time></li>`).join('')}</ol>`:'<p class="small muted">尚未记录日期</p>'}<h3>面试记录</h3><p class="newline small">${esc(job.interview_notes)||'<span class="muted">未记录</span>'}</p>${job.legacy_interview_review?'<h3>原面试记录及复盘（合并原文）</h3><p class="newline small">'+esc(job.legacy_interview_review)+'</p>':''}<h3>复盘</h3><p class="newline small">${esc(job.review_notes)||'<span class="muted">未记录</span>'}</p><div class="detail-management-actions"><button id="detail-query">查询官网投递进度</button><p id="query-result" role="status"></p><button class="danger" id="detail-delete">永久删除岗位</button></div>
`;
  modal(job.role||'岗位详情','管理岗位',body,`<button id="detail-edit">编辑记录</button><button id="detail-prepare" class="primary" ${integration.canPrepare(job)?'':'disabled'}>${job.continuation?'继续投递':'开始投递'}</button>`);
  $('#save-application-url').onclick=async e=>{e.target.disabled=true;try{const saved=await api('/api/jobs/'+job.id+'/application-url','POST',{revision:job.revision,url:$('#manual-application-url').value});await reloadJobs();renderTable();details(saved);toast('投递链接已保存，可直接开始');}catch(error){$('#application-url-error').textContent=error.message;e.target.disabled=false;}};
  $('#detail-edit').onclick=()=>editor(job,false);
  $('#detail-prepare').onclick=()=>prepareJob(job);
  if ($('#detail-query')) $('#detail-query').onclick=e=>query(job.id,e.currentTarget);
  if ($('#detail-delete')) $('#detail-delete').onclick=()=>deleteJob(job);
}
async function reloadJobs(){state.jobs=(await api('/api/jobs')).jobs;}
async function previewInput(text){
 const batch=await api('/api/preview/text','POST',{text});state.batch=batch;state.patches={};state.selected.clear();showInputPreview();
}
function showInputPreview(){
 const rows=candidateRows();
 modal('确认录入岗位','只录入管理表格',`<p class="small muted">核对公司、岗位和链接。确认录入不会打开官网或开始填写。缺少身份信息可先保存，补齐后才能开始。</p>${rows.map(r=>`<article class="input-candidate" data-candidate="${esc(r.id)}"><label class="check-label"><input type="checkbox" data-input-select="${esc(r.id)}" checked> 录入此岗位</label>${['company','role','source_url'].map((key,i)=>`<label>${['公司名称','岗位名称','来源链接'][i]}<input data-input-key="${key}" value="${esc(key==='source_url'?(r.source_url||r.url):r[key])}"></label>`).join('')}${r.mapping_notes?.length?`<p class="small muted">${r.mapping_notes.map(esc).join('；')}</p>`:''}</article>`).join('')}<div id="input-error" class="error-box"></div>`, '<button data-cancel>取消</button><button class="primary" id="confirm-input">确认录入管理表格</button>',true);
 const requestId=crypto.randomUUID();
 $('#confirm-input').onclick=async e=>{const selections=[...document.querySelectorAll('[data-candidate]')].filter(c=>c.querySelector('[data-input-select]').checked).map(c=>({id:c.dataset.candidate,patch:Object.fromEntries([...c.querySelectorAll('[data-input-key]')].map(x=>[x.dataset.inputKey,x.value]))}));e.target.disabled=true;try{await api('/api/import','POST',{source:'text',batch_id:state.batch.batch_id,selections,request_id:requestId});await reloadJobs();state.view='jobs';state.batch=null;close();render();toast('已录入管理表格，可以选择开始投递');}catch(err){$('#input-error').textContent=err.message;e.target.disabled=false;}};
}
function newInput(){
 modal('录入岗位','链接或自然语言', '<textarea class="text-input" id="source-text" aria-label="招聘链接或公司岗位" placeholder="粘贴链接，或输入要投递哪家公司、什么岗位"></textarea><div id="input-error" class="error-box"></div>', '<button data-cancel>取消</button><button class="primary" id="preview-button">解析并确认录入</button>');
 $('#preview-button').onclick=async e=>{e.target.disabled=true;try{await previewInput($('#source-text').value);}catch(err){$('#input-error').textContent=err.message;e.target.disabled=false;}};
}
function formField(label,key,job,full=false,type='text') { return `<label class="${full?'full':''}">${esc(label)}<input type="${type}" name="${key}" value="${esc(job[key]||'')}" ${key==='recruitment_stage'?'list="stage-options"':''}></label>`; }
function editor(job, isCandidate) {
  const form=`<form id="edit-form"><div class="form-grid">${formField('公司名称','company',job)}${formField('岗位名称','role',job)}${formField('来源链接','source_url',job,true,'url')}${formField('官网投递链接（未确认可留空）','official_url',job,true,'url')}${formField('志愿顺序（未知留空）','preference_order',job)}<label>投递状态<select name="application_status">${['未投递','已投递'].map(s=>`<option ${job.application_status===s?'selected':''}>${s}</option>`).join('')}</select></label>${formField('招聘进度（可选预设或直接输入自定义）','recruitment_stage',job,true)}<datalist id="stage-options">${state.stages.map(s=>`<option value="${s}"></option>`).join('')}</datalist>${formField('地点','location',job)}${formField('招聘批次','campaign',job)}<label class="full check-label"><input type="checkbox" name="requires_preference" ${job.requires_preference?'checked':''}> 此申请涉及选择志愿，请到官网人工申请</label></div><div class="callout">${isCandidate?'候选调整只作用于本次预览。选择入库后才建立管理记录。':'更改状态不生成招聘日期、不查询官网。'} 招聘进度留空表示尚未记录。</div>
    ${isCandidate?'':`<label class="full">时间线原文<textarea name="timeline_text" rows="3">${esc(job.timeline_text||'')}</textarea></label><h3>人工日期时间线</h3><p class="small muted">约面与实际面试日期分别记录；没有日期时保持空白。</p><div id="timeline-list"></div><datalist id="date-labels">${['投递日期','笔试／测评日期','完成笔试／测评日期','约一面日期','一面日期','约二面日期','二面日期','约三面日期','三面日期','约终面日期','终面日期'].map(s=>`<option value="${s}"></option>`).join('')}</datalist><button type="button" id="add-date" class="small">＋ 添加日期</button><div class="divider"></div><div class="form-grid"><label class="full">面试记录（保留字段）<textarea name="interview_notes" rows="3">${esc(job.interview_notes||'')}</textarea></label><label class="full">复盘（保留字段）<textarea name="review_notes" rows="3">${esc(job.review_notes||'')}</textarea></label></div>`}
<div class="error-box" id="edit-error"></div></form>`;
  modal(isCandidate?'候选详情与补齐':job.role,isCandidate?'预览 · 尚未入库':'管理记录 · 本机保存',form,`<span class="save-scope">${isCandidate?'原文保留':'仅保存本机管理记录'}</span><button data-cancel>取消</button><button class="primary" id="save-edit">${isCandidate?'应用到本次预览':'保存修改'}</button>`);
  if (!isCandidate) {
    const addDate=d=>{const row=document.createElement('div');row.className='timeline-row';row.innerHTML=`<input class="date-label" list="date-labels" value="${esc(d.label||'投递日期')}" aria-label="日期节点"><input class="date-day" type="date" value="${esc(d.day||'')}" aria-label="实际日期"><button type="button" aria-label="移除日期">✕</button>`;row.querySelector('button').onclick=()=>row.remove();$('#timeline-list').append(row);};
    for (const d of job.timeline||[]) addDate(d);
    $('#add-date').onclick=()=>addDate({});
  }
  $('#save-edit').onclick=async e=>{
    const f=$('#edit-form'),data=new FormData(f),patch=Object.fromEntries(data.entries());patch.requires_preference=f.elements.requires_preference.checked;
    const timeline=isCandidate?undefined:[...f.querySelectorAll('.timeline-row')].map(r=>({label:$('.date-label',r).value,day:$('.date-day',r).value}));
    e.target.disabled=true;
    try {
      if (isCandidate) {state.patches[job.id]={...(state.patches[job.id]||{}),...patch};}
      else {await api('/api/jobs/'+job.id,'PATCH',{revision:job.revision,patch,timeline});await reloadJobs();}
      close();render();toast(isCandidate?'已应用到本次预览，选择后才能入库':'已保存本机管理记录');
    } catch(err){$('#edit-error').textContent=err.message;e.target.disabled=false;}
  };
  $('#edit-form').onsubmit=e=>e.preventDefault();
}
function deleteJob(job) {
  modal('永久删除这个岗位？','删除范围',`<h2>${esc(job.company)}</h2><p>${esc(job.role)}</p><div class="callout danger">将永久删除本机的该岗位、${job.timeline.length} 个日期节点、面试记录、复盘、${job.preparation_count||0} 份本次材料和 ${job.execution_count} 条填写记录，没有恢复入口。正在执行的后续动作也会停止。</div><p class="small muted">共享底稿库、简历附件和其他岗位保留。不会撤回官网申请。</p><div id="delete-error" class="error-box"></div>`, '<button data-cancel>保留记录</button><button class="danger primary" id="confirm-delete">确认永久删除</button>');
  $('#confirm-delete').onclick=async e=>{e.target.disabled=true;try{await api('/api/jobs/'+job.id,'DELETE',{revision:job.revision,confirmed:true});integration.postDeleted(job.id,window);await reloadJobs();close();render();toast('已永久删除本机岗位及关联记录');}catch(err){$('#delete-error').textContent=err.message;e.target.disabled=false;}};
}
async function query(id,b) {
 b.disabled=true;b.textContent='正在查询…';
 const output=$('#query-result');
 try{
  let result=await api('/api/jobs/'+id+'/query','POST',{});
  for(let n=0;n<100;n++){
   if(output?.isConnected)output.textContent=result.message||'正在读取官网投递记录…';
   if(result.status!=='running')break;
   await new Promise(resolve=>setTimeout(resolve,1000));result=await api('/api/jobs/'+id+'/query');
  }
  if(result.status==='complete'){await reloadJobs();renderTable();if(b.isConnected)details(state.jobs.find(j=>j.id===id));}
  toast(result.message||'查询尚未结束，请稍后重试');
 }catch(err){toast(err.message);if(output?.isConnected)output.textContent=err.message;}
 finally{b.disabled=false;b.textContent='查询官网投递进度';}
}
$('#overlay').onclick=e=>{if(e.target===$('#overlay'))close();};
document.addEventListener('keydown',e=>{
  if ($('#overlay').hidden) return;
  if(e.key==='Escape') close();
  if(e.key==='Tab') {
    const focusable=[...$('#overlay').querySelectorAll('button:not(:disabled),a[href],input:not(:disabled),select:not(:disabled),textarea:not(:disabled),summary')];
    const first=focusable[0],last=focusable.at(-1);
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus();}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus();}
  }
});
async function boot() {try{const d=await api('/api/bootstrap');Object.assign(state,d);state.view='jobs';render();}catch(err){$('#main').innerHTML='<div class="empty"><h2>管理页面暂时无法连接</h2><p>'+esc(err.message)+'</p></div>';}}
boot();

window.addEventListener('message',async event=>{if(event.origin===location.origin&&event.source===window.parent&&event.data?.type==='workbench:jobs-changed'){try{await reloadJobs();if($('#table-area'))renderTable();}catch(error){toast(error.message);}}});
