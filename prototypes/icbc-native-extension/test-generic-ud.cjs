const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const {chromium}=require('playwright');
test('modern ATS repeat groups, required controls, dates, popup scope and finished original attachment',async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage();await page.route('**/*',route=>route.fulfill({contentType:'text/html; charset=utf-8',body:`<main>
  <div class="applyFormModuleWrapper__fixture"><div class="applyFormModuleWrapper-left"><p class="applyFormModuleWrapper-text">教育经历</p></div><div class="applyFormModuleWrapper-right">
   <div class="apply-form-array-card__fixture"><div class="ud-formily-item" data-form-field-i18n-name="学历"><div class="ud-formily-item-label"><span class="ud-formily-item-label-required">*</span>学历</div><div class="ud__select"><div class="ud__select__selector__content"><span class="ud__select__selector__selected-item"></span><input type="search" readonly class="ud__select__selector__search__input"></div></div></div>
    <div class="ud-formily-item" data-form-field-i18n-name="起止时间"><div class="throne-biz-date-range-picker-wrapper"><div class="throne-biz-date-range-picker-input"><input></div><div class="throne-biz-date-range-picker-input"><input></div></div></div></div><button>添加</button></div></div>
  <div class="applyFormModuleWrapper__fixture"><p class="applyFormModuleWrapper-text">实习经历</p><button>添加</button></div>
  <div class="applyFormModuleWrapper__fixture"><p class="applyFormModuleWrapper-text">简历</p><div class="uploadResume__fixture"><div class="uploadResume__nested"><input type="file" style="display:none"></div><span class="filename">fictional.pdf</span><span>上次上传: 2026-01-01</span><span>更新 删除</span></div></div>
  <div class="ud-formily-item" data-form-field-i18n-name="学校名称"><div class="ud__select" id="school"><input><span class="ud__select__selector__selected-item"></span></div></div>
  <div class="ud__select__dropdown ud-slide-up-leave ud-slide-up-leave-start" style="position:absolute;top:-9999px"><div class="ud__select__list__item">旧字段隐藏选项，不能混入</div></div>
  <div class="school-popup" style="display:none"><div class="ud__select__list__item">虚构大学</div></div>
  <div class="ud__select__dropdown" style="display:none"><div class="ud__select__list__item">硕士</div><div class="ud__select__list__item">本科</div></div>
  <script>const root=document.querySelector('.ud__select'),popup=document.querySelector('.ud__select__dropdown:not(.ud-slide-up-leave)');root.onclick=()=>popup.style.display='block';document.addEventListener('pointerdown',e=>{if(!root.contains(e.target)&&!popup.contains(e.target))popup.style.display='none';});for(const item of popup.children)item.onclick=()=>{root.querySelector('span').textContent=item.textContent;popup.style.display='none';};const school=document.querySelector('#school'),schools=document.querySelector('.school-popup');school.querySelector('input').oninput=e=>schools.style.display=e.target.value==='虚构大学'?'block':'none';schools.firstElementChild.onclick=()=>{school.querySelector('span').textContent='虚构大学';schools.style.display='none';};</script></main>`}));
  await page.goto('https://fictional.example/apply');
  await page.evaluate(()=>{window.JobFillNativeChannel='fixture';window.chrome={runtime:{async sendMessage(p){const e=document.querySelector('[data-jobfill-native-field="'+p.marker+'"]');e.value=p.value;e.dispatchEvent(new Event('input',{bubbles:true}));return {ok:true,result:{value:e.value}};}}};});
  for(const file of ['dom-utils.js','generic-adapter.js','executor-core.js','bootstrap.js'])await page.addScriptTag({path:path.join(__dirname,file)});
  let scan=await page.evaluate(()=>window.JobFillExecutor.dispatch('scan'));
  const section=scan.result.sections.find(s=>s.label==='教育经历'),empty=scan.result.sections.find(s=>s.label==='实习经历');
  assert.ok(section,JSON.stringify(scan));assert.equal(section.count,1);assert.equal(empty.count,0);assert.equal(empty.canAdd,true);
  const degree=scan.result.fields.find(f=>f.label==='学历');assert.equal(degree.disabled,false);assert.equal(degree.required,true);
  assert.deepEqual(scan.result.fields.filter(f=>f.kind==='month').map(f=>f.label),['起止时间（开始）','起止时间（结束）']);
  const options=await page.evaluate(args=>window.JobFillExecutor.dispatch('readOptions',args),{snapshotId:scan.result.snapshotId,fieldId:degree.fieldId});assert.deepEqual(options.result.items,['硕士','本科']);
  assert.equal(await page.locator('.ud__select__dropdown:not(.ud-slide-up-leave)').isVisible(),false);
  await page.evaluate(async()=>{const adapter=window.JobFillAdapters.generic;const f=adapter.fields().find(x=>x.label==='学校名称');await adapter.write(f,'虚构大学',{check(){}});});
  assert.equal(await page.locator('#school span').textContent(),'虚构大学');
  scan=await page.evaluate(()=>window.JobFillExecutor.dispatch('scan'));assert.deepEqual(scan.result.attachments[0].fileNames,['fictional.pdf']);
  const uploaded=await page.evaluate(args=>window.JobFillExecutor.dispatch('uploadAttachment',args),{schemaVersion:1,requestId:'fictional-original',snapshotId:scan.result.snapshotId,attachmentId:scan.result.attachments[0].attachmentId,fileName:'fictional.pdf',mimeType:'application/pdf',base64:'eA==',sourceRef:'fictional-file'});assert.equal(uploaded.ok,true);
  let status;for(let n=0;n<60;n++){status=await page.evaluate(()=>window.JobFillExecutor.dispatch('status',{requestId:'fictional-original'}));if(status.result.status!=='running')break;await new Promise(r=>setTimeout(r,25));}
  assert.equal(status.result.status,'complete');assert.equal(await page.locator('input[type=file]').evaluate(e=>e.files.length),0);
 }finally{await browser.close();}
});
