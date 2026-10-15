const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require('playwright');
test('Sugar search-first school and major, exact selection, paired year/month and preserved neighbours',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();
  const control=(id,placeholder,options)=>`<label class="sd-Select-container-fixture" data-options="${options}"><span class="sd-Input-display-value-fixture"></span><input id="${id}" placeholder="${placeholder}" ${placeholder?'':'readonly'}></label>`;
  await page.route('**/*',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:`<input placeholder="输入职位关键字"><main class="apply-block-fixture"><h2 class="blockTitle-fixture">教育经历</h2><div class="apply-fields-fixture">
   <div class="apply-field-fixture"><div class="title-fixture">学校名称</div>${control('school','请输入就读学校','虚构大学分校,虚构大学')}</div>
   <div class="apply-field-fixture"><div class="title-fixture">专业名称</div>${control('major','请输入专业名称','测试学,测试学方向')}</div>
   <div class="apply-field-fixture"><div class="title-fixture">起止时间</div><div class="date_info">${control('sy','','2021,2022')}${control('sm','','1,7,12')}${control('ey','','2024,2025')}${control('em','','1,7,12')}</div></div>
  </div><div id="popup" style="display:none"></div><button id="save">保存</button><script>
   const popup=document.querySelector('#popup');let owner;document.querySelector('#save').onclick=()=>{const notice=document.createElement('div');notice.textContent='更新简历信息成功';document.body.appendChild(notice);};
   function open(input){owner=input.closest('label');const search=input.placeholder;if(search&&!input.value){popup.style.display='none';return;}popup.innerHTML='';for(const name of owner.dataset.options.split(',')){const option=document.createElement('div');option.className='sd-Menu-content-item-fixture';option.textContent=name;option.onclick=()=>{owner.querySelector('span').textContent=name;owner.querySelector('input').placeholder='';popup.style.display='none';};popup.appendChild(option);}popup.style.display='block';}
   for(const input of document.querySelectorAll('input')){input.onclick=()=>open(input);input.oninput=()=>open(input);}
   document.querySelector('h2').onclick=()=>popup.style.display='none';for(const t of document.querySelectorAll('.title-fixture'))t.onclick=()=>popup.style.display='none';
  </script></main>`}));
  await page.goto('https://fictional.example/apply#/candidateHome/resume');
  await page.evaluate(()=>{window.JobFillNativeChannel='fixture';window.chrome={runtime:{async sendMessage(p){const e=document.querySelector('[data-jobfill-native-field="'+p.marker+'"]');e.value=p.value;e.dispatchEvent(new Event('input',{bubbles:true}));return {ok:true,result:{value:e.value}};}}};});
  for(const file of ['dom-utils.js','generic-adapter.js','executor-core.js','bootstrap.js'])await page.addScriptTag({path:path.join(__dirname,file)});
  const result=await page.evaluate(async()=>{
   const a=window.JobFillAdapters.generic,ctx={check(){}},fields=a.fields();
   const school=fields.find(f=>f.label==='学校名称'),major=fields.find(f=>f.label==='专业名称');
   if(school.kind!=='autocomplete'||major.kind!=='autocomplete')throw Error('search controls not recognized');
   await a.write(school,'虚构大学',ctx);await a.write(major,'测试学',ctx);
   const start=fields.find(f=>f.label==='起止时间（开始）'),end=fields.find(f=>f.label==='起止时间（结束）');
   await a.write(start,'2021-12',ctx);await a.write(end,'2024-07',ctx);
   return a.fields().map(f=>[f.label,f.current]);
  });
  assert.deepEqual(result,[['学校名称','虚构大学'],['专业名称','测试学'],['起止时间（开始）','2021-12'],['起止时间（结束）','2024-07']]);
  assert.equal(await page.locator('#popup').isVisible(),false);
  assert.deepEqual(await page.evaluate(()=>window.JobFillAdapters.generic.fields().filter(f=>['学校名称','专业名称'].includes(f.label)).map(f=>f.kind)),['autocomplete','autocomplete']);
  // Real core checks kind again after each write. A disappearing placeholder
  // must not abort the rest of the batch as STALE_FIELD.
  await page.locator('#school').evaluate(e=>{e.placeholder='请输入就读学校';e.closest('label').querySelector('span').textContent='';});
  const scan=await page.evaluate(()=>window.JobFillExecutor.dispatch('scan'));
  const field=scan.result.fields.find(f=>f.label==='学校名称');
  const plan={schemaVersion:1,requestId:'placeholder-change',snapshotId:scan.result.snapshotId,assignments:[{fieldId:field.fieldId,value:'虚构大学'}]};
  assert.equal((await page.evaluate(p=>window.JobFillExecutor.dispatch('execute',p),plan)).ok,true);
  let status;for(let n=0;n<100;n++){status=await page.evaluate(()=>window.JobFillExecutor.dispatch('status',{requestId:'placeholder-change'}));if(status.result.status!=='running')break;await new Promise(r=>setTimeout(r,25));}
  assert.equal(status.result.status,'complete',JSON.stringify(status));
  assert.equal(await page.evaluate(()=>window.JobFillAdapters.generic.canSaveDraft()),true);
  assert.equal(await page.evaluate(()=>window.JobFillAdapters.generic.saveDraft({check(){}})),'更新简历信息成功');
  // Duplicate exact candidates must not be guessed.
  await page.locator('#school').evaluate(e=>{e.closest('label').dataset.options='虚构大学,虚构大学';});
  const failure=await page.evaluate(async()=>{try{const a=window.JobFillAdapters.generic;await a.write(a.fields().find(f=>f.label==='学校名称'),'虚构大学',{check(){}});return '';}catch(e){return e.message;}});
  assert.match(failure,/2|唯一/);
 }finally{await browser.close();}
});
test('Sugar resume upload is recognized, serialized without DOM, and waits for a completed file card',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();await page.route('**/*',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:`<div class="apply-field-fixture"><div class="title-fixture">上传简历</div><div class="file_upload"><button class="file_upload-btn">上传简历</button><input style="display:none" type="file" name="resumeKey"></div></div><script>document.querySelector('input').onchange=e=>{const parent=e.target.closest('.apply-field-fixture');const b=parent.querySelector('button');b.innerHTML='<span>'+e.target.files[0].name+'</span>';b.disabled=true;const busy=document.createElement('p');busy.textContent='正在解析';parent.appendChild(busy);setTimeout(()=>{b.disabled=false;busy.remove();},250);};document.querySelector('.apply-field-fixture').circular={node:document.querySelector('.apply-field-fixture')};</script>`}));
  await page.goto('https://fictional.example/apply');for(const file of ['dom-utils.js','generic-adapter.js','executor-core.js','bootstrap.js'])await page.addScriptTag({path:path.join(__dirname,file)});
  const result=await page.evaluate(async()=>{const a=window.JobFillAdapters.generic,scan=await window.JobFillExecutor.dispatch('scan');if(!scan.ok)throw Error(JSON.stringify(scan));const attachment=a.attachments()[0];await a.uploadAttachment(attachment,{fileName:'fictional.pdf',mimeType:'application/pdf',base64:'eA=='},{check(){}});return {autoFill:scan.result.attachments[0].autoFill,names:a.attachments()[0].fileNames};});
  assert.equal(result.autoFill,true);assert.deepEqual(result.names,['fictional.pdf']);
 }finally{await browser.close();}
});
test('Sugar multiselect reads tags, adds exact choices and closes the menu',async()=>{
 const browser=await chromium.launch({headless:true});try{
 const page=await browser.newPage();await page.route('**/*',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:`<div class="apply-field-fixture"><div class="title-fixture">渠道</div><label class="sd-Select-container-fixture multi_select_info"><div id="tags"></div><input readonly placeholder="请选择"></label></div><div id="popup" style="display:none"><div class="sd-Menu-content-item-fixture">虚构官网</div><div class="sd-Menu-content-item-fixture">虚构学校</div></div><script>const popup=document.querySelector('#popup');document.querySelector('input').onclick=()=>popup.style.display='block';document.querySelector('.title-fixture').onclick=()=>popup.style.display='none';for(const option of popup.children)option.onclick=()=>{const tag=document.createElement('span');tag.className='sd-Tag-container-fixture';tag.innerHTML='<span class="sd-Tag-text-fixture">'+option.textContent+'</span><span class="sd-Tag-close-fixture">x</span>';tag.querySelector('.sd-Tag-close-fixture').onclick=()=>tag.remove();document.querySelector('#tags').appendChild(tag);};</script>`}));await page.goto('https://fictional.example/apply');for(const file of ['dom-utils.js','generic-adapter.js'])await page.addScriptTag({path:path.join(__dirname,file)});
 const result=await page.evaluate(async()=>{const a=window.JobFillAdapters.generic,f=a.fields()[0];if(f.kind!=='multiselect')throw Error(f.kind);a.validate(f,['虚构官网']);await a.write(f,['虚构官网'],{check(){}});return a.fields()[0].current;});assert.deepEqual(result,['虚构官网']);assert.equal(await page.locator('#popup').isVisible(),false);
 }finally{await browser.close();}
});
test('Sugar offers an explicit full-name addition when exact search has no candidates',async()=>{
 const browser=await chromium.launch({headless:true});try{const page=await browser.newPage();await page.route('**/*',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:`<div class="apply-field-fixture"><div class="title-fixture">学校名称</div><label class="sd-Select-container-fixture"><span class="sd-Input-display-value-fixture"></span><input id="school" placeholder="请输入就读学校"></label><div class="sd-Dropdown-dropdown-fixture" style="display:none"><span>暂无选项</span><button id="custom">添加学校全称</button><div id="adder" style="display:none"><input class="option-input-fixture" placeholder="请输入就读学校全称"><button id="add">添加</button></div></div></div><script>const panel=document.querySelector('.sd-Dropdown-dropdown-fixture');document.querySelector('#school').oninput=()=>panel.style.display='block';document.querySelector('#custom').onclick=()=>document.querySelector('#adder').style.display='block';document.querySelector('#add').onclick=()=>{document.querySelector('.sd-Input-display-value-fixture').textContent=document.querySelector('.option-input-fixture').value;panel.style.display='none';};</script>`}));await page.goto('https://fictional.example/apply');await page.evaluate(()=>{window.JobFillNativeChannel='fixture';window.chrome={runtime:{async sendMessage(p){const e=document.querySelector('[data-jobfill-native-field="'+p.marker+'"]');e.value=p.value;e.dispatchEvent(new Event('input',{bubbles:true}));return {ok:true,result:{value:e.value}};}}};});for(const file of ['dom-utils.js','generic-adapter.js'])await page.addScriptTag({path:path.join(__dirname,file)});
 const result=await page.evaluate(async()=>{const a=window.JobFillAdapters.generic;await a.write(a.fields()[0],'虚构中学',{check(){}});return a.fields().map(f=>[f.label,f.current]);});assert.deepEqual(result,[['学校名称','虚构中学']]);
 }finally{await browser.close();}
});
