/* Fictional correction through real local UI/API; no external website. */
const {chromium}=require('playwright'),{spawn}=require('node:child_process'),assert=require('node:assert/strict');
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','test_correction_browser_fixture.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser,stderr='';server.stderr.on('data',d=>stderr+=d);
 try{
  const url=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(d.toString().trim()));server.once('exit',()=>reject(Error(stderr)));});
  const base=url.split('#')[0],read=async()=>await(await fetch(base+'api/state')).json();
  const before=await read(),sid=before.sessions[0].id,old=before.sessions[0].preparation.execution;
  browser=await chromium.launch({headless:true});const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);await page.locator('#show-execution').click();await page.locator('[data-edit-issue]').click();
  let dialog=page.locator('dialog.library-dialog');await dialog.locator('[name="value"]').fill('本次修正姓名');await dialog.locator('button.primary').click();await dialog.waitFor({state:'detached'});
  await page.locator('[data-retry-issue]').click();dialog=page.locator('dialog.library-dialog');
  assert((await dialog.textContent()).includes('官网旧值'));assert((await dialog.textContent()).includes('本次修正姓名'));
  await dialog.locator('button.primary').click();await dialog.waitFor({state:'detached'});
  const after=await read(),execution=after.sessions.find(s=>s.id===sid).preparation.execution;
  assert.notEqual(execution.id,old.id);assert.equal(execution.status,'awaiting_executor');
  assert.equal(execution.confirmed_materials.corrections[0].value,'本次修正姓名');
  assert.equal(execution.confirmed_materials.corrections[0].expected_current,'官网旧值');
  for(const key of ['entries','versions','answer_versions','files'])assert.deepEqual(after[key],before[key]);
  assert(after.sessions[0].preparation.execution_history.some(e=>e.id===old.id));assert.deepEqual(errors,[]);
  console.log('PASS correction UI: structured issue -> session edit -> old/new preview -> confirmed local retry; shared facts and history preserved');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
