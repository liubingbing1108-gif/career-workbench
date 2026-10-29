const {chromium}=require('playwright'),{spawn}=require('node:child_process'),assert=require('node:assert/strict');
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','test_current_material_fixture.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const url=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(d.toString().trim()));server.once('exit',()=>reject(Error('fixture stopped')));server.stderr.on('data',d=>process.stderr.write(d));});
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1366,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.locator('[data-material-module="row"]').waitFor();
  const linked=page.locator('[data-linked-sources] [data-version-content]');assert.equal(await linked.inputValue(),'英语');
  await linked.fill('英文');await page.locator('[data-linked-sources] [data-version-mode="session"]').click();await page.waitForFunction(()=>document.querySelector('#toast').textContent==='仅供本次使用已完成');
  const scalar=page.locator('[data-scalar-material="name"]');await scalar.locator('summary').click();await scalar.locator('[data-version-content]').fill('林晓更正');await scalar.locator('[data-single-sync]').click();
  const dialog=page.locator('#library-structure-dialog');await dialog.getByText('原值：林晓',{exact:true}).waitFor();await dialog.locator('[name="save_relation"]').check();await dialog.locator('[type="submit"]').click();await dialog.waitFor({state:'hidden'});
  const row=page.locator('[data-material-module="row"]');await row.locator('[data-set-details] summary').click();await row.locator('[data-set-value="language_score"]').fill('550');await row.locator('[data-set-value="exam_name"]').fill('未选考试名称草稿');await row.locator('[data-set-save="update"]').click();
  await dialog.locator('[name="field"][value="0/exam_name"]').uncheck();await dialog.locator('details summary').click();await dialog.locator('[name="relation"][value="0/score"]').check();await dialog.locator('[type="submit"]').click();await dialog.waitFor({state:'hidden'});
  assert.equal(await row.locator('[data-set-value="exam_name"]').inputValue(),'未选考试名称草稿');
  await page.locator('#mapping-relation-panel summary').click();await page.getByRole('button',{name:'核对组合/摘取草稿：姓与名',exact:true}).click();
  const derived=page.locator('dialog.library-dialog');await derived.locator('[name="value"]').fill('林 晓');await derived.locator('[name="confirmed"]').check();await derived.locator('button.primary').click();await derived.waitFor({state:'detached'});
  assert(await page.locator('#prep-live-preview').textContent().then(t=>t.includes('林 晓')));
  await page.reload();await page.locator('[data-material-module="row"]').waitFor();assert.equal(await page.locator('[data-linked-sources] [data-version-content]').inputValue(),'英文');
  const state=await page.evaluate(async()=>{const r=await fetch('/api/state');return r.json();});
  assert(state.entries.some(e=>e.values?.name==='林晓更正'));assert(state.entries.some(e=>e.record_type==='ability'&&e.values?.language_name==='英语'));assert(state.entries.some(e=>e.record_type==='exam'&&e.values?.language_score==='550'&&e.values?.exam_name==='示例考试'));assert.equal(state.profile_relations.length,2);assert.deepEqual(errors,[]);
  await page.evaluate(async()=>{await api('/api/website/scan',{session_id:sessionId,manifest:{url:'https://fictional.example/form',title:'虚构关系纠正',fields:[{id:'name',label:'姓名'}]}});});
  await page.goto(url.split('#')[0]+'#profile/basic');await page.locator('#flat-more summary').click();await page.locator('[data-flat-relations]').click();await page.locator(`[data-correct-relation="${state.profile_relations.find(r=>r.question_label==='姓名').id}"]`).click();
  await dialog.locator('[name="fields"]').selectOption('surname');await dialog.locator('[name="confirmed"]').check();await dialog.locator('[type="submit"]').click();await dialog.waitFor({state:'hidden'});
  const corrected=await page.evaluate(async()=>{const r=await fetch('/api/state');return r.json();});
  assert.equal(corrected.profile_relations.length,3);assert.equal(corrected.profile_relations[0].state,'superseded');assert.deepEqual(corrected.profile_relations[2].field_ids,['surname']);
  assert.deepEqual(corrected.entries,state.entries);assert.deepEqual(errors,[]);
  console.log('PASS current material UI: linked source edit, scalar and selected batch joint writeback, unselected draft preserved, compose, reload, relation correction; fictional data only');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(error=>{console.error(error);process.exitCode=1;});
