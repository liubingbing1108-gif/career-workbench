/* F0.31: flat objects and direct scalar fields. Enabled by migrated server state. */
(() => {
const proto=ProfileLibraryEditor.prototype,legacyHydrate=proto.hydrate,legacyRender=proto.render;
const labels={basic:'基本身份',identity_documents:'身份证件',contact:'联系与地址',education:'教育经历',employment:'实习与工作',projects:'项目与研究',campus:'活动经历',language:'语言与考试',skills:'专业技能',certificates:'资格证书',honors:'奖项荣誉',academic:'论文',portfolio:'作品与主页',family:'家庭与联系人',subjective:'个人陈述',attachments:'文件附件',additional:'自定义资料'};
class FlatProfile {
  constructor(owner){
    this.owner=owner;this.selected=new Map();this.open=new Set(JSON.parse(localStorage.getItem('career-flat-open')||'[]'));this.queues=new Map();this.errors=new Map();
    try{this.drafts=JSON.parse(localStorage.getItem('career-flat-profile-drafts')||'{}');}catch{this.drafts={};}
    this.hidden={};this.pending=false;
  }
  hydrate(library){
    this.library=library;this.hidden=library.visibility||{};
    for(const [key,item] of Object.entries(library.drafts||{}))if(key.startsWith('flat:')&&!this.drafts[key])this.drafts[key]={...item.body,draftRevision:item.revision};
    for(const [key,draft] of Object.entries(this.drafts))if(draft.request_id&&library.saved_requests?.[draft.request_id])delete this.drafts[key];
    for(const e of library.records)if(!this.selected.has(e.id))this.selected.set(e.id,e.profile_default_set_id??'');
    this.persist();
  }
  persist(){localStorage.setItem('career-flat-profile-drafts',JSON.stringify(this.drafts));}
  key(e,unit=''){return 'flat:'+e.id+'/'+(this.selected.get(e.id)??'none')+'/'+unit;}
  title(e){const v=e.values||{};return v.company||v.project_name||v.school||v.exam_name||v.language_name||v.award_name||v.campus_title||v.identity_type||v.family_name||v.skill_name||v.certificate_name||v.academic_name||v.portfolio_name||v.homepage_platform||labels[e.category]||'资料';}
  fields(e){return e.fields||state.fields.filter(f=>!f.legacy_preserved&&f.category===e.category&&(!f.entry_id||f.entry_id===e.id)&&(!f.record_types?.length||f.record_types.includes(e.record_type)));}
  values(e){if(e.versions_enabled&&!this.selected.get(e.id))return Object.fromEntries(this.fields(e).map(f=>[f.id,f.value_role==='expression'?'':e.values?.[f.id]||'']));return e.version_values?.[this.selected.get(e.id)]||e.values||{};}
  draft(e,unit=''){
    const key=this.key(e,unit);
    return this.drafts[key]||(this.drafts[key]={id:e.id,entry_id:e.isNew?null:e.id,category:e.category,record_type:e.record_type||'',values:{},edit_token:e.edit_token,set_id:this.selected.get(e.id)??'',draftRevision:0,unit});
  }
  async stage(e,unit){
    const key=this.key(e,unit),draft=this.draft(e,unit);delete draft.request_id;this.persist();
    const body=structuredClone(draft),previous=this.queues.get(key)||Promise.resolve();
    const queued=previous.catch(()=>{}).then(async()=>{
      try{const saved=await api('/api/profile/draft',{key,body,revision:this.drafts[key]?.draftRevision||0});if(this.drafts[key])this.drafts[key].draftRevision=saved.revision;this.errors.delete(key);this.persist();}
      catch(error){this.errors.set(key,error);throw error;}
    });this.queues.set(key,queued);queued.catch(error=>toast('草稿保留在本页：'+error.message,true));return queued;
  }
  input(e,f,unit){
    const value=this.drafts[this.key(e,unit)]?.values[f.id]??this.values(e)[f.id]??'',attrs=`data-flat-field="${escapeHtml(f.id)}" aria-label="${escapeHtml(f.label)}"`;
    let html;
    if(f.widget==='boolean')html=`<select ${attrs}>${['',...(f.boolean_values||['是','否','不适用'])].map(x=>`<option value="${x}" ${value===x?'selected':''}>${x||'未提供'}</option>`).join('')}</select>`;
    else if(['file','files'].includes(f.widget))html=`<select ${attrs} ${f.widget==='files'?'multiple':''}><option value="">未选择</option>${state.files.filter(file=>(!file.archived&&!file.library_removed)||value.split('\n').includes(file.id)).map(file=>`<option value="${file.id}" ${value.split('\n').includes(file.id)?'selected':''}>${escapeHtml(file.name)}</option>`).join('')}</select><button type="button" data-flat-file-upload="${f.id}">上传原文件</button>${value.split('\n').filter(Boolean).map(id=>`<a href="/api/files/${encodeURIComponent(id)}" target="_blank" rel="noopener">查看所选原件</a>`).join(' ')}`;
    else if(f.widget==='multi_select')html=`<select ${attrs} multiple>${f.options.map(x=>`<option ${value.split('\n').includes(x)?'selected':''}>${escapeHtml(x)}</option>`).join('')}</select>`;
    else if(f.widget==='exam_components'){
      let rows=[];try{rows=JSON.parse(value||'[]');}catch{}
      html=`<div data-components="${f.id}">${[...rows,{}].map((r,i)=>`<div class="flat-components" data-component-row><input data-part="name" aria-label="分项${i+1}名称" placeholder="项目名称" value="${escapeHtml(r.name||'')}"><input data-part="score" aria-label="分项${i+1}成绩" placeholder="成绩" value="${escapeHtml(r.score||'')}"><input data-part="scale" aria-label="分项${i+1}分制" placeholder="分制" value="${escapeHtml(r.scale||'')}"></div>`).join('')}</div><small>留空不代表0；各分项保持同一次考试。</small>`;
    }else html=control(f,value,attrs+(f.type==='number'?' step="any"':''));
    return `<div class="flat-field ${['multiline','versioned_text'].includes(f.type)||f.widget==='exam_components'?'full-span':''}" data-flat-wrap="${f.id}"><label>${escapeHtml(f.label)}</label>${html}<button class="text-button" type="button" data-hide="${f.id}">隐藏</button><details class="flat-field-settings"><summary>字段设置</summary><button type="button" data-rename-field="${f.id}">更改显示名称</button>${f.entry_id&&!f.preset_id&&f.value_role!=='expression'?`<button type="button" data-merge-field="${f.id}">合并等价字段</button>`:''}</details>${f.value_role==='expression'?'<small>当前表达版本</small>':e.versions_enabled?'<small>本对象各版本共用</small>':''}</div>`;
  }
  form(e,fields,unit){
    const hidden=this.hidden[e.id]?.fields||[],q=this.owner.search.trim().toLowerCase();
    fields=fields.filter(f=>!hidden.includes(f.id)||q&&[f.label,...(f.aliases||[])].some(x=>x.toLowerCase().includes(q)));
    return `<form data-flat-form="${escapeHtml(e.id)}" data-unit="${unit}"><div class="flat-fields">${fields.map(f=>this.input(e,f,unit)).join('')}</div><div class="button-row"><button class="primary" type="submit">保存${unit&&!unit.startsWith('address:')?'此字段':'当前资料'}</button><button type="button" data-cancel-draft>取消修改</button><span role="status" data-flat-status></span></div></form>`;
  }
  record(e){
    if(e.category==='basic'||e.category==='subjective'||e.category==='contact'){
      const fields=this.fields(e),scalar=fields.filter(f=>!f.id.startsWith('residence_')&&!f.id.startsWith('mailing_'));
      return scalar.map(f=>`<section class="flat-scalar">${this.form(e,[f],f.id)}</section>`).join('')+['residence','mailing'].map(prefix=>{
        const address=fields.filter(f=>f.id.startsWith(prefix+'_'));return address.length?`<details class="library-record" data-flat-record="${e.id}:${prefix}" open><summary>${prefix==='residence'?'现居地址':'通讯地址'}</summary>${this.form(e,address,'address:'+prefix)}</details>`:'';
      }).join('');
    }
    const version=e.versions_enabled?`<div class="flat-version"><label>表达版本<select data-flat-version><option value="">未选择</option>${e.record_versions.map(v=>`<option value="${v.id}" ${this.selected.get(e.id)===v.id?'selected':''}>${escapeHtml(v.name)}${e.profile_default_set_id===v.id?' · 默认':''}</option>`).join('')}</select></label><button data-version-action="default">设为默认</button><button data-version-action="new">另存版本</button><button data-version-action="blank">新建空白版</button><button data-version-action="rename">重命名</button><button data-version-action="delete">删除此版</button></div>`:'';
    return `<details class="library-record" data-flat-record="${e.id}" ${(this.open.has(e.id)||e.isNew||this.owner.search)?'open':''}><summary>${escapeHtml(this.title(e))}</summary>${version}${this.form(e,this.fields(e),'')}${e.record_type==='ability'?this.links(e):''}<button data-custom-field="${e.id}" class="text-button">＋ 自定义字段</button><button data-delete-object="${e.id}" class="text-button">删除此对象 · 30天内可恢复</button></details>`;
  }
  links(e){
    const chosen=this.drafts[this.key(e,'')]?.exam_ids??this.library.links.filter(l=>l.active&&l.ability_id===e.id).map(l=>l.exam_id);
    const exams=this.library.records.filter(x=>x.record_type==='exam'&&!x.profile_archived);
    return `<form data-exam-links="${e.id}"><label>关联考试<select multiple aria-label="关联考试">${exams.map(x=>`<option value="${x.id}" ${chosen.includes(x.id)?'selected':''}>${escapeHtml(this.title(x))} · ${escapeHtml(x.values.language_score||'未填成绩')}</option>`).join('')}</select></label>${exams.filter(x=>chosen.includes(x.id)).map(x=>`<fieldset data-linked-exam="${x.id}"><legend>${escapeHtml(this.title(x))}</legend>${['exam_name','language_score'].map(fid=>{const f=this.fields(x).find(f=>f.id===fid),v=this.drafts[this.key(e,'')]?.exam_edits?.find(d=>d.entry_id===x.id)?.values?.[fid]??x.values[fid]??'';return `<label>${escapeHtml(f.label)}<input data-exam-field="${fid}" value="${escapeHtml(v)}" ${f.type==='number'?'type="number" step="any"':''}></label>`;}).join('')}<small>这里修改的是同一考试当前结果；更换一次考试请到考试对象核对日期、分制与分项。</small></fieldset>`).join('')}<label class="checkbox-label"><input name="confirm" type="checkbox">确认同步修改所关联考试的名称或成绩</label><button>保存能力与考试关联</button></form>`;
  }

  files(area){
    area.innerHTML=`<form data-flat-upload class="flat-scalar"><label>附件类型<input name="type" aria-label="附件类型" placeholder="可留空"></label><label>原文件<input name="file" type="file" required></label><button>上传并保存</button></form>`+state.files.filter(f=>!f.archived&&!f.library_removed).map(f=>`<form class="flat-scalar" data-flat-file="${f.id}"><a href="/api/files/${encodeURIComponent(f.id)}" target="_blank" rel="noopener">${escapeHtml(f.name)}</a><label>附件类型<input name="type" value="${escapeHtml(f.attachment_type||'')}"></label><button>保存类型</button><button type="button" data-file-delete>删除记录</button><small>原件 ${Math.ceil(f.size/1024)} KB</small></form>`).join('');
    $('[data-flat-upload]',area).onsubmit=safe(async event=>{
      event.preventDefault();const form=event.target,file=$('[name=file]',form).files[0];if(!file||file.size>8*1024*1024)throw Error('请选择不超过8 MiB的原文件');
      const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});
      await api('/api/profile/attachment-upload',{filename:file.name,base64:encoded,attachment_type:$('[name=type]',form).value});await refresh();toast('原文件与附件类型已保存');
    });
    $$('[data-flat-file]',area).forEach(form=>{
      const file=state.files.find(f=>f.id===form.dataset.flatFile);
      form.onsubmit=safe(async event=>{event.preventDefault();await api('/api/profile/attachment',{file_id:file.id,revision:file.profile_revision||0,metadata:{attachment_type:$('[name=type]',form).value}});await refresh();});
      $('[data-file-delete]',form).onclick=()=>this.owner.ask('删除附件记录',`<p>将“${escapeHtml(file.name)}”移入回收站，30天内可恢复。附件原件和历史引用保留；新的附件选择不再列出此记录。</p>`,async()=>{await api('/api/profile/attachment',{file_id:file.id,revision:file.profile_revision||0,action:'delete'});await refresh();});
    });
  }
  showOldDrafts(){
    const rows=Object.entries(this.library.drafts||{}).filter(([key])=>!key.startsWith('flat:'));
    const dialog=document.createElement('dialog');dialog.className='library-dialog';
    dialog.innerHTML='<h3>旧版未保存草稿</h3><p>这些内容尚未保存，不会自动成为当前资料。请核对对象与字段后复制使用；旧草稿继续保留。</p>'+rows.map(([key,item])=>{
      const body=item.body||{},entry=state.entries.find(e=>e.id===body.entry_id);
      return `<details open><summary>${escapeHtml(this.title(entry||body))} · ${escapeHtml(body.name||'原草稿')}</summary>${Object.entries(body.values||{}).filter(([,value])=>value!=='').map(([fid,value])=>`<label>${escapeHtml(state.fields.find(f=>f.id===fid)?.label||fid)}<textarea readonly aria-label="旧版草稿内容">${escapeHtml(String(value))}</textarea></label>`).join('')||'<p>无已填写内容</p>'}</details>`;
    }).join('')+(rows.length?'':'<p>没有旧版未保存草稿。</p>')+'<button type="button" data-close>关闭</button>';
    document.body.append(dialog);dialog.onclose=()=>dialog.remove();$('[data-close]',dialog).onclick=()=>dialog.close();dialog.showModal();
  }
  showHidden(){
    const records=this.library.records.filter(e=>!e.profile_archived),hidden=records.flatMap(e=>(this.hidden[e.id]?.fields||[]).map(fid=>({entry:e,field:this.fields(e).find(f=>f.id===fid)}))).filter(x=>x.field);
    this.owner.ask('重新显示字段',hidden.map((x,i)=>`<label class="checkbox-label"><input type="checkbox" name="show" value="${i}">${escapeHtml(this.title(x.entry))} · ${escapeHtml(x.field.label)}</label>`).join('')||'<p>没有隐藏字段。</p>',async form=>{
      const revisions={};for(const index of form.getAll('show')){const {entry,field}=hidden[Number(index)];const result=await api('/api/profile/visibility',{entry_id:entry.id,field_id:field.id,hidden:false,revision:revisions[entry.id]??this.hidden[entry.id].revision});revisions[entry.id]=result.revision;}await refresh();
    });
  }
  addField(e){
    const candidates=this.library.records.filter(x=>!x.profile_archived&&x.category===selectedCategory);if(!e&&!candidates.length){toast('请先新增一个资料对象',true);return;}
    this.owner.ask('新增自定义属性',(e?'':`<label>所属对象<select name="entry">${candidates.map(x=>`<option value="${x.id}">${escapeHtml(this.title(x))}</option>`).join('')}</select></label>` )+'<p>先用搜索查找全部字段和别名。新属性保存于当前对象。</p><label>属性名称<input name="label" required maxlength="100"></label><label>类型<select name="type"><option value="text">短文本</option><option value="multiline">长文本</option><option value="number">数字</option><option value="partial_date">日期</option></select></label><label class="checkbox-label"><input name="confirmed" type="checkbox" required>已查找全部字段，确认这是不同的新属性</label>',async form=>{e=e||candidates.find(x=>x.id===form.get('entry'));await api('/api/fields',{entry_id:e.id,edit_token:e.edit_token,label:form.get('label'),type:form.get('type'),confirmed_new_attribute:form.has('confirmed')});await refresh();});
  }
  async renameField(fid){
    const shown=await api('/api/profile/field-preview',{field_id:fid});
    this.owner.ask('更改字段显示名称',`<p>只更改显示名称，字段身份、含义、答案与版本保持不变。</p><label>名称<input name="label" required maxlength="100" value="${escapeHtml(shown.field.label)}"></label>`,async data=>{await api('/api/profile/field',{request_id:crypto.randomUUID(),operation:'rename',field_id:fid,token:shown.token,label:data.get('label')});await refresh();});
  }
  async mergeField(fid){
    const initial=await api('/api/profile/field-preview',{operation:'merge',field_id:fid}),dialog=document.createElement('dialog');dialog.className='library-dialog';
    dialog.innerHTML=`<form><h3>合并等价自定义字段</h3><p>将“${escapeHtml(initial.field.label)}”合并到同一对象的已有字段。旧值、来源和历史保留；独立草稿不自动改绑。</p><label>目标字段<select name="target" required><option value="">请选择</option>${initial.targets.map(t=>`<option value="${t.id}">${escapeHtml(t.label)}</option>`).join('')}</select></label><div data-merge-diff></div><label><input name="equivalent" type="checkbox" required>已核对两字段含义、单位及对象范围等价</label><button type="button" data-close>取消</button><button class="primary" disabled>确认合并并保存选择</button></form>`;
    document.body.append(dialog);dialog.onclose=()=>dialog.remove();$('[data-close]',dialog).onclick=()=>dialog.close();let shown,serial=0;
    $('[name=target]',dialog).onchange=safe(async()=>{
      const request=++serial;shown=null;$('button.primary',dialog).disabled=true;$('[data-merge-diff]',dialog).replaceChildren();const target=$('[name=target]',dialog).value;if(!target)return;
      const next=await api('/api/profile/field-preview',{operation:'merge',field_id:fid,target_id:target});if(serial!==request)return;shown=next;
      $('[data-merge-diff]',dialog).innerHTML=`<p>选择合并后采用的当前内容：</p><label><input type="radio" name="choice" value="source" required>采用“${escapeHtml(next.field.label)}”</label><pre>${escapeHtml(next.source_value||'（空白）')}</pre><label><input type="radio" name="choice" value="target" required>保留“${escapeHtml(next.target.label)}”</label><pre>${escapeHtml(next.target_value||'（空白）')}</pre>${next.source_value===''&&next.target_value?'<label><input type="checkbox" name="clear">如采用空白，明确清空目标当前内容</label>':''}`;
      $('button.primary',dialog).disabled=false;
    });
    $('form',dialog).onsubmit=safe(async event=>{event.preventDefault();if(!shown)throw Error('请先选择目标并核对差异');const data=new FormData(event.target);await api('/api/profile/field',{request_id:crypto.randomUUID(),operation:'merge',field_id:fid,target_id:shown.target.id,token:shown.token,value_choice:data.get('choice'),confirmed_equivalent:data.has('equivalent'),confirmed_clear:data.has('clear')});dialog.close();await refresh();toast('等价字段已合并；旧内容和独立草稿已保留');});dialog.showModal();
  }
  pendingList(area){
    const names={shared_fact:'共用事实冲突',current_choice:'选择当前内容',value_format:'旧值格式',exam_semantics:'考试字段含义',exam_sitting:'选择同一次考试结果',duplicate_identity:'重复身份',record_type:'对象类型',statement_choice:'旧陈述归属',removed_values:'已取消字段的旧值',legacy_object:'已移除预设',historical_evidence:'历史证据不足'};
    area.innerHTML='<h2>旧值待核对</h2><p>旧内容保留供核对。选择当前内容会更新对应字段；仅保留旧值不会参与填写。</p>'+this.library.pending.map(p=>`<article class="flat-scalar"><strong>${escapeHtml(names[p.kind]||p.kind)}</strong><p>${escapeHtml(p.reason||'请核对后选择当前内容')}</p><details><summary>查看保留的旧内容</summary>${(p.evidence||[]).map(v=>`<p><b>${escapeHtml(v.label)}</b>：${escapeHtml(v.value)}</p>`).join('')}${p.candidates?`<pre>${escapeHtml(p.candidates.join('\n'))}</pre>`:''}</details>${p.state!=='pending'?`<p>已处理：${escapeHtml(p.state==='preserved'?'仅保留旧值':'已选择当前内容')}</p>`:p.kind==='historical_evidence'?'<p>需要原执行记录补证；当前值不能代替历史。</p>':`<button data-resolve-pending="${p.id}">核对与处理</button>`}</article>`).join('');
    $$('[data-resolve-pending]',area).forEach(button=>button.onclick=()=>{
      const item=this.library.pending.find(p=>p.id===button.dataset.resolvePending),kind=item.kind;
      let html=`<label>处理方式<select name="action">${kind==='removed_values'?'':'<option value="choose">选择当前内容</option>'}<option value="preserve">仅保留旧值，不作为当前内容</option></select></label>`;
      const fields=kind==='statement_choice'?['personal_statement','hobbies','personal_strengths']:kind==='legacy_object'?['wechat','qq']:kind==='exam_semantics'?({exam_date:['obtained_date'],exam_level:['exam_level'],exam_subscores:['exam_components']}[item.field_id]||[]):[item.field_id];
      if(kind==='duplicate_identity')html+=`<label>当前对象<select name="chosen_entry_id">${item.related_ids.map(id=>`<option value="${id}">${escapeHtml(id)}</option>`).join('')}</select></label>`;
      else if(kind==='removed_values'){html+='<p>仅保留原内容供查看；不写入新的预设字段。</p>';}
      else if(kind==='exam_sitting'){
        html+='<p>整组选用一次结果，未提供的日期、分项和附件留空。单字段旧值不代表完整的一次考试。</p>'+item.bundles.map(b=>`<label><input type="radio" name="bundle_id" value="${escapeHtml(b.id)}">${escapeHtml(b.label)}<pre>${escapeHtml(Object.entries({...b.values,...b.legacy_values}).map(([fid,value])=>(state.fields.find(f=>f.id===fid)?.label||fid)+'：'+value).join('\n'))}</pre></label>`).join('');
        html+='<p>旧“考试日期”和旧“等级”不会自动改成“获得日期”或“报考级别”。仅在含义和考试批次已核对后补入下列字段。</p>'+['obtained_date','exam_level','exam_components'].map(fid=>`<label><input type="checkbox" name="exam_apply" value="${fid}">确认填写${escapeHtml(state.fields.find(f=>f.id===fid)?.label||fid)}<textarea name="exam_${fid}"></textarea></label>`).join('');
      }
      else if(kind==='record_type'){
        const old=state.entries.find(e=>e.id===item.entry_id);html+=`<label>对象类型<select name="record_type"><option value="">请选择已核对的类型</option>${(state.profile_record_types[old.category]||[]).map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select></label><p>此步只确认类型。存在多个旧值或考试结果时，将另列待核对项。</p>`;
      }else{
        html+=`<label>目标字段<select name="field_id">${fields.filter(Boolean).map(id=>`<option value="${id}">${escapeHtml(state.fields.find(f=>f.id===id)?.label||id)}</option>`).join('')}</select></label><label>核对后的当前内容<textarea name="value" rows="5">${escapeHtml(item.candidates?.[0]||'')}</textarea></label>`;
        if(['statement_choice','legacy_object'].includes(kind))html+='<small>确认后会替换对应当前字段，请核对完整内容。</small>';
      }
      html+='<label class="checkbox-label"><input type="checkbox" name="confirmed" required>已核对字段含义与当前内容</label>';
      this.owner.ask('核对旧资料',html,async form=>{
        const fid=form.get('field_id'),target=this.library.records.find(e=>!e.profile_archived&&this.fields(e).some(f=>f.id===fid));
        await api('/api/profile/pending',{request_id:crypto.randomUUID(),id:item.id,edit_token:item.edit_token,confirmed:form.has('confirmed'),action:form.get('action'),field_id:fid,value:form.get('value'),chosen_entry_id:form.get('chosen_entry_id'),record_type:form.get('record_type'),target_entry_id:target?.id,bundle_id:form.get('bundle_id'),values:Object.fromEntries(form.getAll('exam_apply').map(id=>[id,form.get('exam_'+id)]))});await refresh();
      });
    });
  }
  relationList(area){
    area.innerHTML='<h2>已保存字段对应</h2>'+this.library.relations.map(r=>`<section class="flat-scalar"><strong>${escapeHtml(r.question_label)}</strong><p>→ ${r.field_ids.map(fid=>escapeHtml(state.fields.find(f=>f.id===fid)?.label||fid)).join('＋')} · ${escapeHtml(r.scope.level==='general'?'通用范围':r.scope.origin+' / '+r.scope.tenant)} · ${escapeHtml(r.state)}</p>${['active','needs_review'].includes(r.state)?`<button data-correct-relation="${r.id}">纠正此对应</button><button data-disable-relation="${r.id}">停用此对应</button>`:''}</section>`).join('');
    $$('[data-disable-relation]',area).forEach(button=>button.onclick=safe(async()=>{const relation=this.library.relations.find(r=>r.id===button.dataset.disableRelation);await api('/api/mapping/relations',{request_id:crypto.randomUUID(),operation:'disable',relation_id:relation.id,expected_revision:relation.revision,expected_relation_revision:this.library.relation_revision,confirmed:true});await refresh();}));
    $$('[data-correct-relation]',area).forEach(button=>button.onclick=()=>{
      const relation=this.library.relations.find(r=>r.id===button.dataset.correctRelation);
      const contexts=state.sessions.flatMap(s=>(s.mapping_skill?.request.questions||[]).filter(q=>q.semantic_fingerprint===relation.semantic_fingerprint&&q.object.entry_id===relation.scope.entry_id&&(relation.scope.level==='general'||['origin','tenant','form_key'].every(k=>s.mapping_skill.request.site[k]===relation.scope[k]))).map(q=>({session:s,question:q})));
      if(!contexts.length){toast('请先在对应岗位重新读取官网问题，再回到这里纠正；旧关系与资料保留。',true);return;}
      const fields=state.fields.filter(f=>!f.legacy_preserved&&f.category===relation.scope.category&&(!f.entry_id||f.entry_id===relation.scope.entry_id)&&(!f.record_types?.length||f.record_types.includes(relation.scope.record_type)));
      const methods={alias:'直接取一个同义字段',compose:'组合所选字段，内容另行确认',month:'日期转换为月份',year:'日期转换为年份',education_level:'转换学历层级',academic_degree_level:'转换学位层级',is_full_time:'转换是否全日制'};
      this.owner.ask('纠正字段对应',`<p>${escapeHtml(relation.question_label)} · ${escapeHtml(relation.question_context)}</p><p>保留原网站/租户、对象和筛选范围。选择正确字段；资料答案及历史不随此操作改写。</p><label>问题所在岗位<select name="context">${contexts.map((c,i)=>`<option value="${i}">${escapeHtml(c.session.website?.title||c.session.id)} · ${escapeHtml(c.question.label)}</option>`).join('')}</select></label><label>正确字段（组合可多选）<select name="fields" multiple required>${fields.map(f=>`<option value="${f.id}" ${relation.field_ids.includes(f.id)?'selected':''}>${escapeHtml(f.label)}</option>`).join('')}</select></label><label>取用方式<select name="plan">${Object.entries(methods).map(([id,label])=>`<option value="${id}" ${(relation.plan.transform||relation.plan.kind)===id?'selected':''}>${label}</option>`).join('')}</select></label><label class="checkbox-label"><input name="confirmed" type="checkbox" required>已核对原问题、正确字段及取用方式</label>`,async data=>{
        const selected=data.getAll('fields'),context=contexts[Number(data.get('context'))],same=JSON.stringify(selected)===JSON.stringify(relation.field_ids)&&data.get('plan')===(relation.plan.transform||relation.plan.kind);
        if(same&&relation.state!=='needs_review')throw Error('对应未改变；如需停止复用，请使用停用');
        await api('/api/mapping/relations',{request_id:crypto.randomUUID(),operation:same?'reconfirm':'correct',session_id:context.session.id,question_id:context.question.id,relation_id:relation.id,field_ids:selected,plan_kind:data.get('plan'),scope:relation.scope.level,exclusion_match:JSON.stringify(selected)===JSON.stringify(relation.field_ids)?'plan':'target',expected_revision:relation.revision,expected_relation_revision:this.library.relation_revision,confirmed:data.has('confirmed')});await refresh();toast('对应已保存；相关材料需重新读取并核对');
      });
    });
  }
  async save(e,unit,extra={}){
    const key=this.key(e,unit),draft=this.draft(e,unit);await this.queues.get(key);
    if(this.errors.has(key))throw this.errors.get(key);
    draft.request_id||=crypto.randomUUID();this.persist();
    const result=await api('/api/profile/record',{...draft,...extra,draft_key:key,draft_revision:draft.draftRevision});
    if(extra.mode==='new')this.selected.set(result.record.id,result.set_id);
    delete this.drafts[key];this.persist();this.open.add(result.record.id);await refresh();toast('已保存并回读');
  }
  async add(){
    const cat=selectedCategory;
    this.owner.ask('新增'+(labels[cat]||'资料'),state.profile_record_types?.[cat]?`<label>类型<select name="type">${state.profile_record_types[cat].map(([id,label])=>`<option value="${id}">${label}</option>`).join('')}</select></label>`:'<p>可先保存空白对象，再逐项填写。</p>',async data=>{
      const result=await api('/api/profile/record',{request_id:crypto.randomUUID(),category:cat,record_type:data.get('type')||'',values:{}});this.open.add(result.record.id);await refresh();
    });
  }
  render(){
    document.body.classList.add('flat-profile');
    const top=$('.library-topbar'),search=$('#profile-search'),add=$('#profile-add-controls');
    if(search.parentElement!==top){top.prepend(search);top.append(add);search.setAttribute('aria-label','搜索全部资料与字段');search.placeholder='搜索全部资料、字段或别名';}
    if(!$('#flat-more')){const more=document.createElement('details');more.id='flat-more';more.innerHTML='<summary>更多</summary><button data-flat-custom>新增自定义字段</button><button data-flat-hidden>显示隐藏字段</button><button data-flat-pending>旧值待核对</button><button data-flat-relations>字段对应</button><button data-flat-old-drafts>旧版未保存草稿</button>';top.append(more);$('[data-flat-old-drafts]',more).onclick=()=>this.showOldDrafts();$('[data-flat-custom]',more).onclick=()=>this.addField();$('[data-flat-hidden]',more).onclick=()=>this.showHidden();$('[data-flat-pending]',more).onclick=()=>{this.pending=true;this.relations=false;this.owner.archive=false;this.render();};$('[data-flat-relations]',more).onclick=()=>{this.relations=true;this.pending=false;this.owner.archive=false;this.render();};}
    $('#archive-profile').textContent='回收站';
    $('#category-nav').innerHTML=Object.entries(labels).map(([id,label])=>`<button data-theme="${id}" class="${selectedCategory===id?'active':''}">${label}</button>`).join('');
    $$('[data-theme]').forEach(b=>b.onclick=()=>{selectedCategory=b.dataset.theme;history.replaceState(null,'','#profile/'+selectedCategory);this.owner.archive=false;this.pending=false;this.relations=false;this.owner.search='';search.value='';this.render();});
    const direct=['basic','contact','subjective','attachments'].includes(selectedCategory);
    add.innerHTML=direct?'':`<button data-flat-add>＋ 新增${escapeHtml(labels[selectedCategory]||'资料')}</button>`;
    $('[data-flat-add]')?.addEventListener('click',safe(()=>this.add()));
    const area=$('#profile-fields');$('#profile-foot').replaceChildren();
    if(this.owner.archive){
      area.innerHTML='<h2>回收站</h2>'+this.library.trash.map(item=>`<section class="flat-scalar"><p>${escapeHtml(item.kind==='attachment'?state.files.find(f=>f.id===item.file_id)?.name||'附件':this.title(this.library.records.find(e=>e.id===item.entry_id)||{}))} · ${item.kind==='version'?'表达版本':item.kind==='attachment'?'附件记录':'对象'}</p><p>恢复截止：${new Date(item.expires_at*1000).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}</p><button data-restore="${escapeHtml(item.id)}" ${Date.now()>=item.expires_at*1000?'disabled':''}>${Date.now()>=item.expires_at*1000?'已到期 · 待清理':'恢复'}</button>${item.cleanup_blocked?`<p>${escapeHtml(item.cleanup_blocked)}</p>`:''}</section>`).join('');
      $$('[data-restore]',area).forEach(b=>b.onclick=safe(async()=>{const item=this.library.trash.find(t=>t.id===b.dataset.restore);let result;if(item.kind==='attachment'){const file=state.files.find(f=>f.id===item.file_id);result=await api('/api/profile/attachment',{file_id:file.id,revision:file.profile_revision||0,action:'restore'});}else{const e=this.library.records.find(x=>x.id===item.entry_id);result=await api(item.kind==='version'?'/api/profile/version':'/api/profile/archive',{entry_id:e.id,edit_token:e.edit_token,version_id:item.version_id,action:'restore',archived:false});}await refresh();if(result.conflicts?.length)this.owner.ask('资料已恢复，部分关系待核对',result.conflicts.map(c=>`<p>${escapeHtml(c.reason)}</p>`).join(''),async()=>{});}));return;
    }
    if(this.pending){this.pendingList(area);return;}
    if(this.relations){this.relationList(area);return;}
    if(selectedCategory==='attachments'){this.files(area);return;}
    const q=this.owner.search.trim().toLowerCase();
    const records=this.library.records.filter(e=>!e.profile_archived&&(q?[this.title(e),...Object.values(e.values||{}),...this.fields(e).flatMap(f=>[f.label,...(f.aliases||[])])].some(v=>String(v).toLowerCase().includes(q)):e.category===selectedCategory));
    if(!this.didOpen&&records.length){this.open.add(records[0].id);this.didOpen=true;}
    area.innerHTML=records.map(e=>(q?`<p class="flat-search-context">${escapeHtml(labels[e.category])} · ${escapeHtml(this.title(e))}</p>`:'')+this.record(e)).join('')||'<p>还没有此类资料，可从新增或导入开始。</p>';
    for(const draft of Object.values(this.drafts)){
      if(!records.some(e=>e.id===(draft.entry_id||draft.id)))continue;
      for(const [fid,value] of Object.entries(draft.values||{})){
        const field=state.fields.find(f=>f.id===fid);if(!field?.merged_into)continue;
        area.insertAdjacentHTML('beforeend',`<section class="flat-scalar"><strong>被合并字段的未保存草稿：${escapeHtml(field.label)}</strong><p>原草稿保留，可复制后编辑目标“${escapeHtml(state.fields.find(f=>f.id===field.merged_into)?.label||field.merged_into)}”。</p><textarea readonly aria-label="被合并字段的未保存草稿">${escapeHtml(value)}</textarea></section>`);
      }
    }
    $$('[data-flat-record]',area).forEach(card=>{
      card.ontoggle=()=>{card.open?this.open.add(card.dataset.flatRecord):this.open.delete(card.dataset.flatRecord);localStorage.setItem('career-flat-open',JSON.stringify([...this.open]));};
      const e=records.find(x=>x.id===card.dataset.flatRecord);if(!e)return;
      $('[data-flat-version]',card)?.addEventListener('change',event=>{this.selected.set(e.id,event.target.value||'');this.render();});
      $$('[data-version-action]',card).forEach(button=>button.onclick=safe(async()=>{
        const action=button.dataset.versionAction,id=this.selected.get(e.id);
        if(action==='default'){await api('/api/profile/record-default',{entry_id:e.id,edit_token:e.edit_token,set_id:id||null});await refresh();return;}
        if(action==='delete'){this.owner.ask('删除表达版本','<p>此表达版本进入30天回收站。若它是默认版本，默认选择将清空。本次草稿与历史内容保留，受影响填写项需要重新核对。</p>',async()=>{await api('/api/profile/version',{entry_id:e.id,edit_token:e.edit_token,version_id:id,action});await refresh();});return;}
        this.owner.ask(action==='rename'?'版本名称':'保存表达版本','<label>名称<input name="name" required maxlength="180"></label>',async data=>{
          if(action==='rename')await api('/api/profile/version',{entry_id:e.id,edit_token:e.edit_token,version_id:id,action,name:data.get('name')});
          else await this.save(e,'',{mode:'new',name:data.get('name'),set_id:action==='blank'?'':id,values:action==='blank'?{}:this.draft(e,'').values});
          await refresh();
        });
      }));
    });
    $$('[data-flat-form]',area).forEach(form=>{
      const e=records.find(x=>x.id===form.dataset.flatForm),unit=form.dataset.unit;
      form.oninput=event=>{
        const target=event.target,draft=this.draft(e,unit),components=target.closest('[data-components]');
        if(components)draft.values[components.dataset.components]=JSON.stringify($$('[data-component-row]',components).map(row=>Object.fromEntries($$('[data-part]',row).map(i=>[i.dataset.part,i.value]))).filter(row=>Object.values(row).some(Boolean)));
        else if(target.dataset.flatField)draft.values[target.dataset.flatField]=target.multiple?[...target.selectedOptions].map(o=>o.value).filter(Boolean).join('\n'):target.value;
        else return;
        $('[data-flat-status]',form).textContent='未保存 · 草稿暂存';this.stage(e,unit).catch(()=>{});
      };
      form.onsubmit=safe(async event=>{event.preventDefault();const button=$('[type=submit]',form);button.disabled=true;try{await this.save(e,unit);}finally{button.disabled=false;}});
      $('[data-cancel-draft]',form).onclick=safe(async()=>{const key=this.key(e,unit);await this.queues.get(key);const d=this.drafts[key];if(d)await api('/api/profile/draft',{key,revision:d.draftRevision||0,discard:true});delete this.drafts[key];this.persist();this.render();});
      $$('[data-flat-file-upload]',form).forEach(button=>button.onclick=()=>{
        const picker=document.createElement('input');picker.type='file';picker.onchange=safe(async()=>{const file=picker.files[0];if(!file)return;if(file.size>8*1024*1024)throw Error('请选择不超过8 MiB的原文件');const encoded=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(file);});const result=await api('/api/profile/attachment-upload',{filename:file.name,base64:encoded,attachment_type:''});const fid=button.dataset.flatFileUpload,field=this.fields(e).find(f=>f.id===fid),d=this.draft(e,unit),old=d.values[fid]??this.values(e)[fid]??'';d.values[fid]=field.widget==='files'?[...new Set([...old.split('\n').filter(Boolean),result.id])].join('\n'):result.id;await this.stage(e,unit);await refresh();toast('原件已保留，保存此字段后更新引用');});picker.click();
      });
      $$('[data-hide]',form).forEach(button=>button.onclick=safe(async()=>{await api('/api/profile/visibility',{entry_id:e.id,field_id:button.dataset.hide,hidden:true,revision:this.hidden[e.id]?.revision||0});await refresh();}));
      $$('[data-rename-field]',form).forEach(button=>button.onclick=safe(()=>this.renameField(button.dataset.renameField)));
      $$('[data-merge-field]',form).forEach(button=>button.onclick=safe(()=>this.mergeField(button.dataset.mergeField)));
    });
    $$('[data-custom-field]',area).forEach(b=>b.onclick=()=>this.addField(records.find(x=>x.id===b.dataset.customField)));
    $$('[data-delete-object]',area).forEach(b=>b.onclick=()=>{const e=records.find(x=>x.id===b.dataset.deleteObject),links=this.library.links.filter(l=>l.active&&[l.ability_id,l.exam_id].includes(e.id)).length;this.owner.ask('删除资料对象',`<p>将“${escapeHtml(this.title(e))}”及其表达版本移入30天回收站。${links?'同时解除 '+links+' 条考试关联；恢复时按当前状态核对。':''}对象专属字段对应暂停使用；草稿、历史内容和原件保留。</p>`,async()=>{await api('/api/profile/archive',{entry_id:e.id,edit_token:e.edit_token,archived:true});await refresh();});});
    $$('[data-exam-links]',area).forEach(form=>{
      const e=records.find(x=>x.id===form.dataset.examLinks);
      const add=document.createElement('button');add.type='button';add.textContent='新增考试并关联';form.append(add);
      const draft=this.drafts[this.key(e,'')];
      if(draft?.new_exams?.length){const note=document.createElement('p');note.textContent='待保存的新考试：'+draft.new_exams.map(x=>x.exam_name).join('、');form.append(note);}
      add.onclick=()=>this.owner.ask('新增考试并关联','<p>保存能力与考试关联时一并创建。已有同名考试请直接选择关联。</p>'+['exam_name','exam_language','language_score','exam_scale','exam_level','obtained_date'].filter(id=>state.fields.some(f=>f.id===id)).map(id=>{const f=state.fields.find(f=>f.id===id);return `<label>${escapeHtml(f.label)}<input name="${id}" ${id==='exam_name'?'required':''} value="${id==='exam_language'?escapeHtml(this.values(e).language_name||''):''}"></label>`;}).join(''),async data=>{const d=this.draft(e,'');d.new_exams||=[];d.new_exams.push(Object.fromEntries([...data].filter(([key])=>key.startsWith('exam_')||['language_score','obtained_date'].includes(key))));await this.stage(e,'');this.render();});
      $('select',form).onchange=()=>{const d=this.draft(e,'');d.exam_ids=[...$('select',form).selectedOptions].map(o=>o.value);this.stage(e,'').catch(()=>{});this.render();};
      $$('[data-exam-field]',form).forEach(input=>input.oninput=()=>{
        const eid=input.closest('[data-linked-exam]').dataset.linkedExam,exam=this.library.records.find(x=>x.id===eid),d=this.draft(e,'');d.exam_edits||=[];let edit=d.exam_edits.find(x=>x.entry_id===eid);
        if(!edit){edit={entry_id:eid,edit_token:exam.edit_token,values:{}};d.exam_edits.push(edit);}edit.values[input.dataset.examField]=input.value;this.stage(e,'').catch(()=>{});
      });
      form.onsubmit=safe(async event=>{event.preventDefault();const d=this.draft(e,''),ids=[...$('select',form).selectedOptions].map(o=>o.value),edits=(d.exam_edits||[]).filter(x=>ids.includes(x.entry_id)),changed=edits.length+(d.new_exams?.length||0);if(changed&&!$('[name=confirm]',form).checked)throw Error('请确认对所关联考试的新增或修改');await this.save(e,'',{exam_ids:ids,exam_edits:edits,new_exams:d.new_exams||[],links_revision:e.links_revision||0,confirm_exam_updates:changed>0});});
    });
  }
}
proto.hydrate=function(library){if(library.contract!==30)return legacyHydrate.call(this,library);this.library=library;this.flat||=new FlatProfile(this);this.flat.hydrate(library);};
proto.render=function(){if(this.library.contract!==30)return legacyRender.call(this);this.flat.render();};
window.showDerivedMaterial=async function(wid,entry_ids){
 const sid=sessionId,preview=await api('/api/mapping/derived-preview',{session_id:sid,website_id:wid,entry_ids});
 const dialog=document.createElement('dialog');dialog.className='library-dialog';
 dialog.innerHTML=`<form><h3>核对本次组合或摘取内容</h3><p>${escapeHtml(preview.label)}</p>${preview.options.length>1?`<label>来源对象<select name="entries" multiple>${preview.options.map(o=>`<option value="${o.id}" ${preview.selected_ids.includes(o.id)?'selected':''}>${escapeHtml(o.values.company||o.values.project_name||o.values.school||o.values.language_name||o.id)}</option>`).join('')}</select></label><button type="button" data-rebuild>按选择重新核对来源</button>`:''}<details open><summary>来源字段与当前值</summary>${preview.sources.map(s=>`<p><b>${escapeHtml(s.label)}</b>：${escapeHtml(s.value)}</p>`).join('')}</details>${preview.issues.map(i=>`<p class="notice">${escapeHtml(i)}</p>`).join('')}<label>本次草稿<textarea name="value" rows="8">${escapeHtml(preview.suggestion)}</textarea></label><label><input name="confirmed" type="checkbox" required>已核对来源，确认用于本次填写</label><button type="button" data-close>取消</button><button class="primary" ${preview.issues.length?'disabled':''}>确认本次内容</button></form>`;
 document.body.append(dialog);dialog.onclose=()=>dialog.remove();$('[data-close]',dialog).onclick=()=>dialog.close();
 $('[data-rebuild]',dialog)?.addEventListener('click',safe(async()=>{const ids=[...$('[name=entries]',dialog).selectedOptions].map(o=>o.value);dialog.close();await window.showDerivedMaterial(wid,ids);}));
 if(preview.needs_excerpt){
  $('button.primary',dialog).disabled=true;$('[name=value]',dialog).value='';
  const area=document.createElement('section');area.innerHTML='<p>在一个来源字段中选中需要模型核对的最小片段。只发送选中的文字，结果仍需你确认。</p>'+preview.sources.map((source,index)=>`<label>${escapeHtml(source.label)}<textarea data-excerpt="${index}" readonly rows="5">${escapeHtml(source.value)}</textarea></label><button type="button" data-request-excerpt="${index}">仅发送所选片段，请求摘取草稿</button>`).join('');$('form',dialog).prepend(area);
  $$('[data-request-excerpt]',area).forEach(button=>button.onclick=safe(async()=>{const index=Number(button.dataset.requestExcerpt),source=preview.sources[index],input=$(`[data-excerpt="${index}"]`,area),start=Array.from(input.value.slice(0,input.selectionStart)).length,end=Array.from(input.value.slice(0,input.selectionEnd)).length;if(start===end)throw Error('请先在来源原文中选中需要核对的片段');button.disabled=true;try{await api('/api/mapping/extract-request',{session_id:sid,website_id:wid,entry_ids:preview.selected_ids,token:preview.token,entry_id:source.entry_id,field_id:source.field_id,start,end,confirmed_excerpt:true});dialog.close();await refresh();await window.showDerivedMaterial(wid);}finally{button.disabled=false;}}));
 }
 $('form',dialog).onsubmit=safe(async event=>{event.preventDefault();if(sid!==sessionId)throw Error('岗位已切换');await api('/api/mapping/derived-confirm',{session_id:sid,website_id:wid,entry_ids:preview.selected_ids,token:preview.token,value:$('[name=value]',dialog).value,confirmed:$('[name=confirmed]',dialog).checked});dialog.close();await refresh();toast('组合内容仅保存为本次材料');});dialog.showModal();
};
window.renderMappingRelationPanel=function(){
 const old=$('#mapping-relation-panel');if(state?.profile_contract!==30){old?.remove();return;}
 const session=state.sessions.find(s=>s.id===sessionId),skill=session?.mapping_skill;if(!skill){old?.remove();return;}
 const panel=old||document.createElement('details');panel.id='mapping-relation-panel';if(!old)$('#practice-view').append(panel);
 const candidates=skill.response.decisions.filter(d=>!d.relation_id&&['equivalent','transform','compose'].includes(d.semantic_status));
 panel.innerHTML='<summary>字段对应与复用范围</summary>'+candidates.map(d=>{const q=skill.request.questions.find(q=>q.id===d.question_id);return `<form data-confirm-relation="${escapeHtml(d.question_id)}"><p>${escapeHtml(q.label)} → ${d.sources.map(s=>escapeHtml(state.fields.find(f=>f.id===s.field_id)?.label||s.field_id)).join('＋')}</p><label>复用范围<select name="scope"><option value="site" ${skill.request.site.tenant?'':'disabled'}>本站、当前租户及表单</option><option value="general">明确确认为通用含义</option></select></label><button>确认保存此对应</button></form>`;}).join('');
 for(const decision of skill.response.decisions.filter(d=>['compose','extract_candidate','unresolved','ambiguous'].includes(d.semantic_status)&&d.sources.length)){const button=document.createElement('button');button.type='button';button.textContent='核对组合/摘取草稿：'+skill.request.questions.find(q=>q.id===decision.question_id).label;button.onclick=safe(()=>window.showDerivedMaterial(decision.question_id));panel.append(button);}
 $$('[data-confirm-relation]',panel).forEach(form=>form.onsubmit=safe(async event=>{event.preventDefault();await api('/api/mapping/relations',{request_id:crypto.randomUUID(),operation:'confirm',session_id:sessionId,question_id:form.dataset.confirmRelation,expected_revision:0,expected_relation_revision:state.profile_relation_revision||0,scope:$('[name=scope]',form).value,confirmed:true});await refresh();toast('对应关系已保存；资料答案未修改');}));
};
})();
