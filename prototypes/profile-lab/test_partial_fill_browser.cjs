/* D93: fictional local fixture; never connect a real browser extension or model. */
const {chromium}=require('playwright');
const {spawn}=require('child_process'),assert=require('node:assert/strict');
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','test_partial_fill_fixture.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const base=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(d.toString().trim()));server.once('exit',()=>reject(Error('fixture stopped')));});
  const read=async()=>await(await fetch(base+'/api/state')).json(),before=await read(),sid=before.sessions[0].id;
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#practice/'+sid);await page.locator('#prep-live-preview').waitFor();
  const language=page.locator('.decision-column [data-missing-key^="languages/"]');
  assert.equal(await language.count(),1);assert((await language.textContent()).includes('语言能力'));
  await page.locator('#prep-readiness [data-focus-task^="languages/"]').click();
  await page.waitForFunction(()=>{const e=document.querySelector('.decision-column [data-missing-key^="languages/"]'),r=e.getBoundingClientRect(),p=e.closest('.decision-column').getBoundingClientRect();return r.top>=p.top&&r.bottom<=p.bottom;},null,{timeout:5000});
  assert.equal(await language.evaluate(e=>e.contains(document.activeElement)),true);
  assert((await page.locator('#prep-live-preview').textContent()).includes('本次留空'));
  assert((await page.locator('#prep-start-hint').textContent()).includes('留空或跳过'));
  const version=page.locator('[data-material-module="internships"] [data-material-action="remove-version"]').first();
  assert.equal(await version.textContent(),'删除');
  assert((await version.getAttribute('title')).includes('资料库版本和当前内容保留'));
  assert(await page.locator('#prep-confirm-inline').isEnabled());
  await page.locator('#prep-confirm-inline').click();
  await page.waitForFunction(()=>document.querySelector('#execution-current').textContent.includes('等待连接'));
  const after=await read(),execution=after.sessions.find(s=>s.id===sid).preparation.execution;
  assert.equal(execution.status,'awaiting_executor');assert.equal(execution.filled,0);
  assert.equal(execution.confirmed_materials.attachment,null);
  assert(!execution.confirmed_materials.rows.some(r=>['languages','new'].includes(r.website_id)));
  assert(execution.confirmed_materials.rows.some(r=>r.website_id==='edu'));
  assert(execution.confirmed_materials.skipped.some(t=>t.website_id==='languages'));
  for(const key of ['entries','versions','answer_versions','files'])assert.deepEqual(after[key],before[key]);
  assert.deepEqual(after.sessions[1],before.sessions[1]);assert.deepEqual(errors,[]);
  console.log('PASS D93: ambiguous collection visible and focusable, blank items do not block, renamed deletion, only known nonempty materials queued, original data and other job unchanged; 0 UI errors');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
