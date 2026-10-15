/* D95: fictional localhost retry; opener stub means no official website is touched. */
const {chromium}=require('playwright');
const {spawn}=require('child_process'),assert=require('node:assert/strict');
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','test_retry_fixture.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser,stderr='';server.stderr.on('data',d=>stderr+=d);
 try{
  const base=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(d.toString().trim()));server.once('exit',()=>reject(Error('fixture stopped: '+stderr)));});
  const read=async()=>await(await fetch(base+'/api/state')).json(),before=await read(),sid=before.sessions[0].id,old=before.sessions[0].preparation.execution;
  browser=await chromium.launch({headless:true});const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#practice/'+sid);await page.locator('#show-execution').click();
  const retry=page.locator('#execution-retry');await retry.waitFor();assert.equal(await retry.textContent(),'重试填写');assert(await retry.isEnabled());
  await retry.click();await page.waitForFunction(()=>document.querySelector('#execution-current').textContent.includes('等待连接'));
  const after=await read(),session=after.sessions.find(s=>s.id===sid),execution=session.preparation.execution;
  assert.notEqual(execution.id,old.id);assert.equal(execution.status,'awaiting_executor');assert.equal(execution.confirmed_materials.retry,true);assert.equal(execution.digest,old.digest);
  assert(session.preparation.execution_history.some(e=>e.id===old.id&&e.filled===2));
  assert.equal(await retry.isVisible(),false);
  for(const key of ['entries','versions','answer_versions','files'])assert.deepEqual(after[key],before[key]);
  assert.deepEqual(after.sessions[1],before.sessions[1]);assert.deepEqual(errors,[]);
  console.log('PASS D95 retry UI: failed -> reconnect -> new scoped execution, same confirmed materials, old progress and unrelated records retained; zero page errors');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
