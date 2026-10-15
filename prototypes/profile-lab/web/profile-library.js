/* P24: one module, directly editable collapsible records; no duplicate inventory. */
class ProfileLibraryEditor {
  constructor(){
    try{this.drafts=JSON.parse(localStorage.getItem('career-profile-drafts-v1')||'{}');}catch{this.drafts={};}
    this.library={records:[],drafts:{}};this.open=new Set();this.selected=new Map();this.queues=new Map();this.errors=new Map();this.archive=false;this.search='';
  }
  hydrate(library){
    this.library=library;
    for(const [key,item] of Object.entries(library.drafts||{})){
      if(!this.drafts[key])this.drafts[key]={...item.body,draftRevision:item.revision};
      else if([...(item.body.previous_edit_tokens||[]),item.body.previous_edit_token].filter(Boolean).includes(this.drafts[key].edit_token)){
        this.drafts[key].edit_token=item.body.edit_token;this.drafts[key].draftRevision=item.revision;
      }else if(this.drafts[key].draftRevision===undefined)this.drafts[key].draftRevision=item.revision;
    }
    for(const [key,draft] of Object.entries(this.drafts))if(draft.request_id&&library.saved_requests?.[draft.request_id])delete this.drafts[key];
    this.persist();
  }
  persist(){try{localStorage.setItem('career-profile-drafts-v1',JSON.stringify(this.drafts));}catch{toast('草稿暂存空间不足，请保存当前资料',true);}}
  entry(id){return this.library.records.find(e=>e.id===id)||Object.values(this.drafts).find(d=>d.id===id);}
  key(entry){return entry.id+'/'+(this.selected.get(entry.id)||'default');}
  snapshot(entry){
    const setId=this.selected.get(entry.id)||'default';
    const version=entry.record_versions?.find(v=>v.id===setId);
    const refs={};const values={};
    for(const field of this.fields(entry)){
      let vid=version?version.field_versions[field.id]:entry.default_versions?.[field.id];
      if(versionsFor(entry.id,field.id).find(v=>v.id===vid)?.profile_deleted)vid=entry.default_versions?.[field.id];
      refs[field.id]=vid||null;
      values[field.id]=versionsFor(entry.id,field.id).find(v=>v.id===vid)?.content??(!version?entry.values?.[field.id]:'')??'';
    }
    return {id:entry.id,entry_id:entry.isNew?null:entry.id,isNew:!!entry.isNew,category:entry.category,record_type:entry.record_type||'',values,field_versions:refs,edit_token:entry.edit_token,set_id:setId,name:'',draftRevision:0};
  }
  edit(entry){const key=this.key(entry);return this.drafts[key]||(this.drafts[key]=this.snapshot(entry));}
  stage(entry){const key=this.key(entry),draft=this.edit(entry);draft.dirty=true;delete draft.request_id;this.persist();this.status(entry.id,'未保存 · 草稿暂存中');this.queue(key);}
  queue(key){
    const body=structuredClone(this.drafts[key]);if(!body)return;
    const prior=this.queues.get(key)||Promise.resolve();
    const pending=prior.catch(()=>{}).then(async()=>{
      const draft=this.drafts[key];if(!draft)return;
      try{
        const saved=await api('/api/profile/draft',{key,body,revision:draft.draftRevision||0});
        if(this.drafts[key])this.drafts[key].draftRevision=saved.revision;
        this.errors.delete(key);this.persist();this.status(body.id,'未保存 · 草稿已暂存');
      }catch(error){this.errors.set(key,error);this.status(body.id,'草稿暂存失败 · 内容仍保留');throw error;}
    });this.queues.set(key,pending);pending.catch(()=>{});
  }
  status(id,text,error=false){const node=document.querySelector(`[data-record-status="${id}"]`);if(node){node.textContent=text;node.classList.toggle('error',error);}}
  meta(entry,values){const v=values||entry.values||{};return [v.role||v.degree||v.project_role||v.family_relation||v.skill_level||v.certificate_progress,[v.started||v.education_started||v.campus_started||v.project_started,v.ended||v.graduation_date||v.campus_ended||v.project_ended].filter(Boolean).join(' — '),v.award_date||v.exam_date||v.preferred_cities].filter(Boolean).join(' · ')||'展开填写资料';}
  field(entry,field,draft){
    const fid=field.id,value=draft.values[fid]??'',attrs=`data-library-field="${escapeHtml(fid)}" aria-label="${escapeHtml(field.label)}"`,versions=versionsFor(entry.id,fid);
    let input;
    if(field.widget==='boolean')input=`<select ${attrs}>${['','是','否','不适用'].map(v=>`<option value="${v}" ${value===v?'selected':''}>${v||'未提供'}</option>`).join('')}${value&&!['是','否','不适用'].includes(value)?`<option selected>${escapeHtml(value)}</option>`:''}</select>`;
    else if(['file','files'].includes(field.widget)){
      const selected=value.split('\n').filter(Boolean);const files=state.files.filter(f=>!f.archived||selected.includes(f.id));
      input=`<select ${attrs} ${field.widget==='files'?'multiple':''}><option value="">未选择</option>${files.map(f=>`<option value="${f.id}" ${selected.includes(f.id)?'selected':''}>${escapeHtml(f.display_name||f.name)}</option>`).join('')}</select>${selected.map(id=>`<a href="/api/files/${encodeURIComponent(id)}" target="_blank" rel="noopener">查看附件</a>`).join(' ')}${field.widget==='file'&&selected[0]&&/\.(png|jpe?g|webp|gif)$/i.test(files.find(f=>f.id===selected[0])?.name||'')?`<img class="profile-photo" alt="${escapeHtml(field.label)}" src="/api/files/${encodeURIComponent(selected[0])}">`:''}<button type="button" data-field-upload="${fid}">上传文件</button>`;
    }else input=control(field,value,attrs);
    return `<div class="library-field ${['multiline','versioned_text'].includes(field.type)?'full-span':''}" data-library-field-wrap="${fid}"><div class="field-heading"><label>${escapeHtml(field.label)}</label>${field.type==='versioned_text'?`<small data-word-count>${value.length} 字</small>`:''}</div>${input}<details class="field-versions"><summary>版本${versions.length?' · '+versions.length:''}</summary><div class="button-row">${versions.length?`<select data-library-field-version="${fid}" aria-label="${escapeHtml(field.label)}版本"><option value="">留空 / 新版本</option>${versions.map(v=>`<option value="${v.id}" ${draft.field_versions[fid]===v.id?'selected':''}>${escapeHtml(versionName(v))}${entry.default_versions?.[fid]===v.id?' · 默认':''}</option>`).join('')}</select>`:''}<button type="button" data-new-field-version="${fid}">新增版本</button>${draft.field_versions[fid]?`<button type="button" data-field-default="${fid}">设为默认</button>`:''}</div></details></div>`;
  }
  newFieldVersion(entry,fid){
    if(entry.isNew){toast('请先保存这条新资料，再新增字段版本');return;}
    const field=state.fields.find(f=>f.id===fid);if(!field){toast('请先保存这个新字段，再新增版本');return;}$('#new-version-title').textContent=field.label+' · 新增版本';$('#new-version-name').value='版本'+(versionsFor(entry.id,fid).length+1);$('#new-version-content').innerHTML=control(field,'','id="new-version-value" aria-label="新版本内容"');$('#new-version-error').hidden=true;
    $('#new-version-form').onsubmit=async event=>{event.preventDefault();const button=$('#save-new-version');button.disabled=true;
      try{const result=await api('/api/profile/field-version',{entry_id:entry.source_entry_id||entry.id,field_id:fid,edit_token:entry.edit_token,name:$('#new-version-name').value,content:$('#new-version-value').value});
        const key=this.key(entry),draft=this.edit(entry);draft.edit_token=result.record.edit_token;draft.field_versions[fid]=result.version.id;draft.values[fid]=result.version.content;this.stage(entry);await this.queues.get(key);$('#new-version-dialog').close();await refresh();this.replaceCard?.(this.entry(entry.id));toast('已保存 '+result.version.name);
      }catch(error){$('#new-version-error').hidden=false;$('#new-version-error').textContent=error.message;}finally{button.disabled=false;}
    };$('#new-version-dialog').showModal();
  }
  async discard(entry){const key=this.key(entry);await this.queues.get(key);const draft=this.drafts[key];if(draft)await api('/api/profile/draft',{key,revision:draft.draftRevision||0,discard:true});delete this.drafts[key];this.persist();this.render();}
  async setDefault(entry,field){const draft=this.drafts[this.key(entry)]||this.snapshot(entry),refs=Object.fromEntries(Object.entries(field?{[field]:draft.field_versions[field]}:draft.field_versions).filter(([fid,vid])=>vid&&state.fields.some(f=>f.id===fid)));const updated=await api('/api/profile/record-default',{entry_id:entry.source_entry_id||entry.id,edit_token:entry.edit_token,set_id:this.selected.get(entry.id)||'default',field_versions:refs});for(const d of Object.values(this.drafts)){if(d.id===entry.id&&d.edit_token===entry.edit_token)d.edit_token=updated.edit_token;}this.persist();await refresh();this.replaceCard?.(this.entry(entry.id));toast('已设为默认版本');}
  files(){
    return state.files.filter(f=>!!f.archived===this.archive).map(original=>{const f={...original,...(this.drafts['file:'+original.id]?.metadata||{})};return `<details class="library-record" data-file-card="${f.id}" ${this.open.has('file:'+f.id)?'open':''}><summary><span class="record-summary"><strong>${this.nameHTML(f.display_name||f.name,'data-file-rename="display_name"')}</strong><small>${escapeHtml(f.attachment_type||'未分类')} · ${Math.ceil(f.size/1024)} KB${f.version_name?' · '+escapeHtml(f.version_name):''}</small></span><span>⌄</span></summary><div class="record-body"><div class="field-grid">${[['attachment_type','附件类型'],['language','语言'],['target_role','适用岗位'],['target_company','适用公司']].map(([key,label])=>`<label>${label}${key==='attachment_type'?`<select data-file-meta="${key}"><option value="">未分类</option>${['简历','生活照','证件照','成绩单','证书/证明','作品集','推荐信','其他'].map(v=>`<option ${f[key]===v?'selected':''}>${v}</option>`).join('')}</select>`:`<input data-file-meta="${key}" value="${escapeHtml(f[key]||'')}">`}</label>`).join('')}<label>关联资料<select data-file-meta="linked_entry"><option value="">不关联</option>${this.library.records.filter(e=>!e.profile_archived||e.id===f.linked_entry).map(e=>`<option value="${e.id}" ${f.linked_entry===e.id?'selected':''}>${escapeHtml(this.title(e))}</option>`).join('')}</select></label></div><p class="muted">原文件：${escapeHtml(f.name)} · ${f.size} 字节${f.uploaded_at?' · '+new Date(f.uploaded_at*1000).toLocaleString():''}</p><div class="record-actions"><a href="/api/files/${f.id}" download>下载原文件</a><div class="button-row"><button data-file-archive="${f.id}">${f.archived?'恢复':'删除'}</button>${f.archived?'':`<span role="status" data-record-status="${f.id}">${this.drafts['file:'+f.id]?.dirty?'未保存 · 草稿已保留':'已保存'}</span><button data-file-discard="${f.id}">放弃草稿</button><button class="primary" data-file-save="${f.id}">保存附件信息</button>`}</div></div></div></details>`;}).join('')||'<div class="library-empty">暂无附件，上传后保留原文件。</div>';
  }
  async archiveFile(id){const key='file:'+id,file=state.files.find(f=>f.id===id);await this.queues.get(key);const updated=await api('/api/profile/attachment',{file_id:id,revision:file.profile_revision||0,metadata:{archived:!file.archived}});if(this.drafts[key]){this.drafts[key].file_revision=updated.profile_revision;this.persist();this.queue(key);}await refresh();}
  async discardFile(id){const key='file:'+id;await this.queues.get(key);if(this.drafts[key])await api('/api/profile/draft',{key,revision:this.drafts[key].draftRevision||0,discard:true});delete this.drafts[key];this.persist();this.render();}
  async saveFile(id){const file=state.files.find(f=>f.id===id),key='file:'+id,metadata={...(this.drafts[key]?.metadata||{})};await this.queues.get(key);$$('[data-file-meta]',$(`[data-file-card="${id}"]`)).forEach(i=>metadata[i.dataset.fileMeta]=i.value);await api('/api/profile/attachment',{file_id:id,revision:this.drafts[key]?.file_revision??file.profile_revision??0,metadata});if(this.drafts[key])await api('/api/profile/draft',{key,revision:this.drafts[key].draftRevision||0,discard:true});delete this.drafts[key];this.persist();await refresh();toast('附件信息已保存');}
  upload(entry,fieldId){
    const input=document.createElement('input');input.type='file';input.onchange=safe(async()=>{
      const file=input.files[0];if(!file)return;if(file.size>8*1024*1024)throw Error('请选择不超过 8 MiB 的文件');
      const key=entry?.id||'files';this.uploading||=new Set();this.uploading.add(key);toast('正在上传文件…');
      const buttons=()=>entry?$$('[data-save-record],[data-save-field],[data-save-group]',$(`[data-library-record="${entry.id}"]`)||document):[];
      buttons().forEach(b=>b.disabled=true);
      try{
        const base64=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.onerror=reject;r.readAsDataURL(file);});
        const stored=await api('/api/profile/attachment-upload',{filename:file.name,base64});
        if(entry){const draft=this.edit(entry),field=this.fields(entry).find(f=>f.id===fieldId);draft.values[fieldId]=field.widget==='files'?[...new Set([...(draft.values[fieldId]||'').split('\n').filter(Boolean),stored.id])].join('\n'):stored.id;this.stage(entry);}
        await refresh();if(entry)this.replaceCard?.(this.entry(entry.id));toast(entry?'文件已上传，请保存这条资料以确认引用':'附件已上传，原文件已保留');
      }finally{this.uploading.delete(key);buttons().forEach(b=>b.disabled=false);}
    });input.click();
  }

}
const profileLibrary=new ProfileLibraryEditor();
