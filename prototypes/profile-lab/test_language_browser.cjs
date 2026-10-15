/* D94: fictional local data; does not connect to a website/model/extension. */
const {chromium}=require('playwright');
const {spawn}=require('child_process'),assert=require('node:assert/strict');
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','test_language_mapping.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const base=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(d.toString().trim()));server.once('exit',()=>reject(Error('fixture stopped')));});
  const read=async()=>await(await fetch(base+'/api/state')).json(),before=await read(),sid=before.sessions[0].id;
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:900}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#practice/'+sid);await page.locator('#prep-live-preview').waitFor();
  const module=page.locator('[data-material-module="languages"]');
  assert.equal(await module.locator('[data-experience]:checked').count(),1);
  assert((await page.locator('#prep-live-preview').textContent()).includes('测试语种'));
  assert((await page.locator('#prep-live-preview').textContent()).includes('熟练'));
  const inputs=module.locator('[data-missing-value]');assert.equal(await inputs.count(),2);
  await module.getByLabel('听说',{exact:true}).selectOption('良好');
  await module.getByLabel('读写',{exact:true}).selectOption('精通');
  await page.waitForFunction(()=>document.querySelector('#preview-save-state').textContent.includes('待确认使用'));
  await module.getByRole('button',{name:'仅供本次使用',exact:true}).click();
  await page.waitForFunction(()=>!document.querySelector('[data-material-module="languages"] [data-missing-value]'));
  await page.reload();await page.locator('#prep-live-preview').waitFor();
  const preview=await page.locator('#prep-live-preview').textContent();assert(preview.includes('良好'));assert(preview.includes('精通'));
  assert(await page.locator('#prep-confirm-inline').isEnabled());
  const after=await read();for(const key of ['entries','versions','answer_versions','files'])assert.deepEqual(after[key],before[key]);
  assert.deepEqual(after.sessions[1],before.sessions[1]);assert.deepEqual(errors,[]);
  console.log('PASS D94: existing language auto-filled, exams excluded, actual dropdown inputs save and survive reload, shared facts and other job unchanged; 0 UI errors');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
