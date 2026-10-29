/* D88: isolated real UI operations with fictional materials; no external websites/models. */
const {chromium}=require('playwright');
const {spawn}=require('child_process');const assert=require('node:assert/strict');
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','test_product_fixture.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const base=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(d.toString().trim()));server.once('exit',()=>reject(Error('fixture stopped')));});
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:900}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const state=async()=>await(await fetch(base+'/api/state')).json();
  const before=await state();const sid=before.sessions[0].id;
  await page.addInitScript(()=>document.addEventListener('workbench-ready',()=>{window.testWorkbenchReady=true;},{once:true}));
  await page.goto(base+'/#practice/'+sid);await page.waitForFunction(()=>window.testWorkbenchReady===true);await page.locator('#prep-live-preview').waitFor();
  const module=page.locator('[data-material-module="internships"]');
  const saved=()=>page.waitForFunction(()=>document.querySelector('#preview-save-state').textContent.includes('预览已更新'));
  const remove=async(root,action)=>{const response=page.waitForResponse(r=>r.url().endsWith('/api/website/material-control')&&r.request().method()==='POST'&&r.request().postDataJSON().action===action);await root.locator('[data-material-action="'+action+'"]').click();const result=await response;assert.equal(result.status(),200,await result.text());await page.waitForFunction(()=>!preparationQueue().busy(sessionId));};
  // All groups, even automatic education, and missing single fields offer controls.
  const edu=page.locator('[data-material-module="edu"]');assert.equal(await edu.locator('[data-experience]').count(),2);
  const scalar=page.locator('[data-scalar-material="new"]');assert(await scalar.locator('[data-include-scalar]').isVisible());
  await scalar.locator('[data-include-scalar]').uncheck();await saved();assert((await page.locator('#prep-readiness').textContent()).includes('语言程度'));
  await remove(scalar,'remove-module');await saved();assert.equal(await scalar.count(),0);
  await edu.locator('[data-experience]').first().uncheck();await saved();assert((await page.locator('#prep-live-preview').textContent()).includes('本次不填写'));
  await edu.locator('[data-experience]').first().check();await saved();assert((await page.locator('#prep-live-preview').textContent()).includes('硕士'));
  const firstId=await module.locator('[data-material-entry]').first().getAttribute('data-material-entry');
  let record=module.locator('[data-material-entry="'+firstId+'"]');
  await remove(record,'remove-record');await saved();assert.equal(await record.count(),0);assert.equal(await module.locator('[data-restore-entry]').count(),0);
  assert(!JSON.stringify((await(await fetch(base+'/api/preparation/bundle?session='+sid)).json()).preparation.current.rows).includes(firstId));
  await page.reload();await page.waitForFunction(()=>window.testWorkbenchReady===true);await page.locator('#prep-live-preview').waitFor();assert.equal(await record.count(),0);
  assert.equal(await scalar.count(),0);assert.equal(await page.getByText('已删除本次记录',{exact:false}).count(),0);
  record=module.locator('[data-material-entry]').first();
  // A version removal hides the local option and keeps both shared data and current values.
  const vid=await record.locator('[data-set-version] option').last().getAttribute('value');
  await record.locator('[data-set-version]').selectOption(vid);await saved();
  await remove(record,'remove-version');await saved();assert.equal(await record.locator('[data-set-version] option[value="'+vid+'"]').count(),0);
  await remove(record,'restore-versions');await saved();assert.equal(await record.locator('[data-set-version] option[value="'+vid+'"]').count(),1);
  // Draft edits and scroll survive unrelated choice changes.
  await record.locator('[data-set-details]>summary').click();const input=record.locator('[data-set-value="role"]');await input.fill('虚构未确认草稿');
  await page.waitForFunction(()=>document.querySelector('#preview-save-state').textContent.includes('草稿已自动保存'));
  await module.locator('[data-include-module]').uncheck();await page.waitForFunction(()=>!document.querySelector('#preview-save-state').textContent.includes('正在保存'));
  assert.equal(await input.inputValue(),'虚构未确认草稿');assert(await record.locator('[data-set-details]').getAttribute('open')!==null);
  await module.locator('[data-include-module]').check();await page.waitForFunction(()=>!document.querySelector('#preview-save-state').textContent.includes('正在保存'));
  const removedId=await record.getAttribute('data-material-entry');await remove(record,'remove-record');await saved();assert.equal(await module.locator('[data-material-entry="'+removedId+'"]').count(),0);
  await remove(module,'remove-module');await saved();assert.equal(await module.count(),0);
  assert(!(await page.locator('#prep-live-preview').textContent()).includes('实习经历 · 本次不填写'));
  await page.reload();await page.waitForFunction(()=>window.testWorkbenchReady===true);await page.locator('#prep-live-preview').waitFor();assert.equal(await module.count(),0);assert.equal(await scalar.count(),0);
  await page.locator('#remove-attachment').click();await saved();assert.equal(await page.locator('#prep-attachment').inputValue(),'');
  const after=await state();for(const key of ['entries','versions','answer_versions','files'])assert.deepEqual(after[key],before[key]);assert.deepEqual(after.sessions[1],before.sessions[1]);
  if(process.env.UI_EVIDENCE){require('fs').mkdirSync(process.env.UI_EVIDENCE,{recursive:true});await page.screenshot({path:process.env.UI_EVIDENCE+'/material-controls.png'});}
  assert.deepEqual(errors,[]);console.log('PASS D88 controls: groups/scalars, required validation, record deletion without history/reload, version hide/restore, drafts, attachments and shared/other-job isolation; 0 page errors');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
