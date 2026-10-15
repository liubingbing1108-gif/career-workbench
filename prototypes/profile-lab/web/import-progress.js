let importTasks=[],importPolling=false,completedImportId='';
function importTaskMarkup(task){
  const busy=['待识别','识别中'].includes(task.status),stages=['原文件已保存','转换为 Markdown','按资料组识别内容','核验来源与整理资料组','完成'];
  const index=stages.indexOf(task.stage||task.status),seconds=task.started_at?Math.max(0,Math.floor(Date.now()/1000-task.started_at)):0;
  if(!busy)return `<article class="import-task import-task-error"><div class="section-heading"><strong>${escapeHtml(task.filename)}</strong><span role="status">${escapeHtml(task.status)}</span></div>${task.error?`<p class="form-error">${escapeHtml(task.error)}</p>`:''}<div class="button-row"><button data-import-preview="${escapeHtml(task.id)}">查看详情</button><button data-import-retry="${escapeHtml(task.id)}">继续识别</button></div></article>`;
  return `<article class="import-task"><div class="section-heading"><strong>${escapeHtml(task.filename)}</strong><span role="status">${escapeHtml(task.stage||task.status)}${busy?' · '+seconds+' 秒':''}</span></div><progress aria-label="${escapeHtml(task.filename)}解析进度" ${busy?'':`value="${task.status==='完成'?4:Math.max(0,index)}" max="4"`}></progress><ol class="import-stages">${stages.map((s,i)=>`<li class="${i<index?'done':i===index?'active':''}">${escapeHtml(s)}</li>`).join('')}</ol>${task.error?`<p class="form-error">${escapeHtml(task.error)}</p>`:''}<button data-import-preview="${escapeHtml(task.id)}">${busy?'查看解析预览':'查看识别结果'}</button>${['失败','已中断'].includes(task.status)?` <button data-import-retry="${escapeHtml(task.id)}">继续识别</button>`:''}</article>`;
}
function renderImportTasks(){
  const host=$('#import-tasks');if(!host)return;
  const active=importTasks.filter(t=>t.status!=='完成').slice().reverse(),completed=importTasks.filter(t=>t.status==='完成').slice().reverse();
  const historyOpen=$('#completed-imports',host)?.open||false;
  if(!completed.some(t=>t.id===completedImportId))completedImportId=completed[0]?.id||'';
  host.innerHTML=`<div class="active-imports">${active.map(importTaskMarkup).join('')}</div>${completed.length?`<details id="completed-imports" ${historyOpen?'open':''}><summary>已完成识别 · ${completed.length} 份${completed.some(t=>t.pending_count)?' · 有待确认资料':''}</summary><div class="completed-import-picker"><label>选择简历<select id="completed-import-select">${completed.map(t=>`<option value="${escapeHtml(t.id)}" ${t.id===completedImportId?'selected':''}>${escapeHtml(t.filename)} · ${t.pending_count?'待确认 '+t.pending_count+' 项':'已处理'}</option>`).join('')}</select></label><button data-import-preview="${escapeHtml(completedImportId)}">查看识别结果</button></div></details>`:''}`;
  if($('#completed-import-select',host))$('#completed-import-select',host).onchange=event=>{completedImportId=event.target.value;renderImportTasks();};
  $$('[data-import-preview]',host).forEach(b=>b.onclick=safe(async()=>{await refresh();openPreview(state.imports.find(p=>p.id===b.dataset.importPreview));}));
  $$('[data-import-retry]',host).forEach(b=>b.onclick=safe(async()=>{b.disabled=true;await api('/api/import/retry',{import_id:b.dataset.importRetry,async:true});await pollImportTasks();}));
  renderImportTaskPreview();
}
function renderImportTaskPreview(){
  const host=$('#import-task-preview');if(!host)return;
  const wasOpen=$('details',host)?.open,scroll=$('pre',host)?.scrollTop||0;
  const task=importTasks.find(t=>t.id===preview?.id)||preview;
  host.innerHTML=task?`<p role="status"><strong>${escapeHtml(task.filename)}</strong> · ${escapeHtml(task.stage||task.status)}</p>${['待识别','识别中'].includes(task.status)?'<progress aria-label="简历解析进度"></progress><p>正在识别，完成后会展示成组资料预览。可以关闭此窗口，稍后继续查看。</p>':''}<details><summary>${task.conversion_format==='markdown'?'Markdown 转换预览':'历史原文预览'}（最多 16000 字）</summary><pre class="resume-text-preview">${escapeHtml(task.text_preview||(['待识别','识别中'].includes(task.status)?'正在用 MarkItDown 转换；转换失败会保留原文件并提示。':'此任务没有可用的原文预览；识别结果与说明见下方。'))}</pre></details>`:'';
  if(wasOpen&&$('details',host))$('details',host).open=true;if($('pre',host))$('pre',host).scrollTop=scroll;
}
async function pollImportTasks(){
  if(importPolling)return;importPolling=true;
  try{importTasks=(await api('/api/imports')).map(t=>({...t,status:t.status||'完成'}));
    const changed=importTasks.some(t=>(state.imports.find(p=>p.id===t.id)?.status||'完成')!==t.status);
    if(changed){const id=preview?.id,open=$('#import-dialog').open;await refresh();if(open&&id)openPreview(state.imports.find(p=>p.id===id));}
    renderImportTasks();
  }catch(error){if($('#upload-progress')){$('#upload-progress').hidden=false;$('#upload-progress').textContent='解析状态暂未连接，恢复后自动更新；已上传原件保留。';}}
  finally{importPolling=false;}
}
setInterval(()=>{if(importTasks.some(t=>['待识别','识别中'].includes(t.status)))void pollImportTasks();},1000);
document.addEventListener('workbench-ready',()=>void pollImportTasks());
