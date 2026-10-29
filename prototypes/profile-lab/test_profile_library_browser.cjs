/* Fictional local UI acceptance for P24; no external pages or model calls. */
const {chromium}=require('playwright');const {spawn}=require('child_process');const assert=require('node:assert/strict');
(async()=>{const server=spawn(process.env.PYTHON||'python3',['-u','test_product_fixture.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
try{
 const base=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(d.toString().trim()));server.once('exit',()=>reject(Error('fixture stopped')));server.stderr.on('data',d=>process.stderr.write(d));});
 browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 const getState=async()=>await(await fetch(base+'/api/state')).json();const before=await getState();
 await page.addInitScript(()=>document.addEventListener('workbench-ready',()=>{window.testWorkbenchReady=true;},{once:true}));
await page.goto(base+'/#profile/employment');await page.waitForFunction(()=>window.testWorkbenchReady===true);await page.locator('[data-library-record]').first().waitFor();
 assert.equal(await page.locator('#category-nav [data-category]').count(),14);assert.equal(await page.locator('.group-inventory,.education-sets').count(),0);
 const first=page.locator('[data-library-record]').first();await first.locator(':scope>summary').click();
 await first.locator('[data-library-field="description"]').fill('虚构完整原文\n保留全部指标 20%');await page.waitForFunction(()=>[...document.querySelectorAll('[data-record-status]')].some(e=>e.textContent.includes('草稿已暂存')));
 const eid=await first.getAttribute('data-library-record');const old=before.versions.find(v=>v.entry_id===eid&&v.field_id==='description').content;
 assert.equal((await getState()).versions.find(v=>v.entry_id===eid&&v.field_id==='description').content,old);
 await page.reload();await page.waitForFunction(()=>window.testWorkbenchReady===true);await page.locator(`[data-library-record="${eid}"]`).waitFor();const card=page.locator(`[data-library-record="${eid}"]`);await card.locator(':scope>summary').click();assert.equal(await card.locator('[data-library-field="description"]').inputValue(),'虚构完整原文\n保留全部指标 20%');
 const saveResponse=page.waitForResponse(r=>r.url().endsWith('/api/profile/record')&&r.request().method()==='POST');await card.locator('[data-save-record="update"]').click();const saved=await saveResponse;assert.equal(saved.status(),200,await saved.text());await page.waitForFunction(()=>document.querySelector('#toast').textContent==='已保存这条资料');
 const after=await getState();assert.equal(after.versions.find(v=>v.id===after.entries.find(e=>e.id===eid).default_versions.description).content,'虚构完整原文\n保留全部指标 20%');
 for(const entry of before.entries.filter(e=>e.category==='employment'&&e.id!==eid))assert.deepEqual(after.entries.find(e=>e.id===entry.id),entry);
 // Another version keeps default and record identity.
 await card.locator('[data-library-field="description"]').fill('虚构另一版描述');await card.locator('[data-save-record="new"]').click();await page.waitForFunction(()=>[...document.querySelectorAll('[data-record-status]')].some(e=>e.textContent==='已保存'));
 assert.equal((await getState()).entries.filter(e=>e.category==='employment').length,before.entries.filter(e=>e.category==='employment').length);
 assert.equal((await getState()).versions.find(v=>v.id===after.entries.find(e=>e.id===eid).default_versions.description).content,'虚构完整原文\n保留全部指标 20%');
 // New draft and cancel do not create a real entry.
 await page.locator('#add-entry').click();await page.locator('#library-structure-dialog button[type=submit]').click();const draft=page.locator('[data-library-record^="draft_"]');await draft.locator('[data-library-field="company"]').fill('虚构未保存公司');assert.equal((await getState()).entries.filter(e=>e.category==='employment').length,before.entries.filter(e=>e.category==='employment').length);
 await draft.locator('[data-delete-record]').click();await draft.waitFor({state:'detached'});
 // Collapse summary and reversible delete.
 await page.locator('#collapse-profile').click();assert.equal(await page.locator('[data-library-record][open]').count(),0);assert(await card.locator(':scope>summary').isVisible());
 await card.locator(':scope>summary').click();await card.locator('[data-delete-record]').click();await card.waitFor({state:'detached'});assert((await getState()).entries.find(e=>e.id===eid).profile_archived);
 await page.locator('#archive-profile').click();if(await card.getAttribute('open')===null)await card.locator(':scope>summary').click();await card.locator('[data-restore-record]').click();await card.waitFor({state:'detached'});await page.locator('#archive-profile').click();assert.equal(await card.count(),1);
 // Independent photos, no resume recognition for attachment upload.
 await page.locator('[data-category="basic"]').click();const basic=page.locator('[data-library-record]').first();await basic.locator(':scope>summary').click();
 assert.equal(await basic.locator('[data-library-field="life_photo"]').count(),1);assert.equal(await basic.locator('[data-library-field="id_photo"]').count(),1);
 const upload=async(fid,name,content)=>{const chooser=page.waitForEvent('filechooser');await basic.locator(`[data-field-upload="${fid}"]`).click();await(await chooser).setFiles({name,mimeType:'image/png',buffer:Buffer.from(content)});await page.waitForFunction(()=>document.querySelector('#toast').textContent.startsWith('文件已上传'));};
 await upload('life_photo','fiction-life.png','fake-photo-one');await upload('id_photo','fiction-id.png','fake-photo-two');
 await basic.locator('[data-save-record="update"]').click();await page.waitForFunction(()=>document.querySelector('#toast').textContent==='已保存这条资料');
 const savedBasic=(await getState()).entries.find(e=>e.category==='basic');assert(savedBasic.values.life_photo&&savedBasic.values.id_photo);assert.notEqual(savedBasic.values.life_photo,savedBasic.values.id_photo);assert.equal((await getState()).imports.length,before.imports.length);
 // File metadata drafts survive reload and archive/restore without touching bytes.
 await page.locator('[data-category="attachments"]').click();const file=page.locator(`[data-file-card="${savedBasic.values.life_photo}"]`);await file.locator(':scope>summary').click();
 await file.locator('[data-file-rename="display_name"]').click();await page.locator('#library-structure-dialog [name=label]').fill('虚构生活照名称');await page.locator('#library-structure-dialog [name=label]').press('Enter');await page.waitForFunction(()=>[...document.querySelectorAll('[data-record-status]')].some(e=>e.textContent.includes('草稿已暂存')));
 assert.notEqual((await getState()).files.find(f=>f.id===savedBasic.values.life_photo).display_name,'虚构生活照名称');
 await page.reload();await page.waitForFunction(()=>window.testWorkbenchReady===true);await file.waitFor();await file.locator(':scope>summary').click();assert.equal(await file.locator('[data-file-rename="display_name"]').locator('..').locator('[data-name-text]').textContent(),'虚构生活照名称');
 await file.locator('[data-file-archive]').click();await file.waitFor({state:'detached'});await page.locator('#archive-profile').click();await file.locator('[data-file-archive]').click();await file.waitFor({state:'detached'});await page.locator('#archive-profile').click();
 await file.locator('[data-file-save]').click();await page.waitForFunction(()=>document.querySelector('#toast').textContent==='附件信息已保存');assert.equal((await getState()).files.find(f=>f.id===savedBasic.values.life_photo).display_name,'虚构生活照名称');
 await page.locator('#collapse-profile').click();assert.equal(await page.locator('[data-file-card][open]').count(),0);await page.locator('#expand-profile').click();assert.equal(await page.locator('[data-file-card][open]').count(),(await getState()).files.length);
 await page.locator('[data-category="education"]').click();await page.locator('#expand-profile').click();assert.equal(await page.locator('[data-library-field="graduation_date"]').count(),2);assert.equal(await page.locator('[data-library-field="double_degree"]').first().inputValue(),'');
 await page.locator('[data-category="employment"]').click();await page.locator('#expand-profile').click();
 if(process.env.UI_EVIDENCE){require('fs').mkdirSync(process.env.UI_EVIDENCE,{recursive:true});await page.screenshot({path:process.env.UI_EVIDENCE+'/profile-library.png'});}
 assert.deepEqual(errors,[]);console.log('PASS profile library UI: 14 modules, no duplicated lists, direct forms, draft/reload, per-record save, versions/default isolation, add/cancel, collapse/summary, delete/restore, separate photos/raw upload, education booleans; 0 page errors');
}finally{if(browser)await browser.close();server.kill('SIGTERM');}})().catch(e=>{console.error(e);process.exitCode=1;});
