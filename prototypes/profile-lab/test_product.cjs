/* Unified product navigation, with fictional records only. */
const {chromium}=require('playwright');
const {spawn}=require('child_process');const assert=require('node:assert/strict');
const python=process.env.PYTHON || 'python3';
const source=`from server import make_server
from test_product_fixture import make_fixture
f,app,m=make_fixture()
server=make_server(f.lab,management_app=app,management_handler=m.handler(app),browser_opener=lambda url:None)
print(server.server_port,flush=True)
try:server.serve_forever()
finally:server.server_close();f.tearDown()
`;

(async()=>{
 const server=spawn(python,['-u','-c',source],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const port=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(Number(d.toString().trim())));server.once('exit',()=>reject(Error('fixture server stopped')));});
  const base='http://127.0.0.1:'+port;browser=await chromium.launch({...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{}),headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base);const frame=page.frameLocator('#management-frame');await frame.getByRole('row',{name:'查看 示例公司 产品岗位甲 详情',exact:true}).waitFor();
  assert.equal(await page.locator('.main-tabs button').count(),2);assert.equal(await frame.locator('.site-header').isVisible(),false);
  await frame.getByRole('row',{name:'查看 示例公司 产品岗位甲 详情',exact:true}).click();await frame.getByRole('dialog').waitFor();assert((await frame.getByRole('dialog').textContent()).includes('示例公司'));
  await frame.getByRole('button',{name:'继续投递',exact:true}).last().click();await page.locator('#prep-live-preview').waitFor();
  assert.equal(new URL(page.url()).origin,base);assert.equal(await page.locator('#application-url').inputValue(),'https://example.com/apply');
  const left=await page.locator('.decision-column').boundingBox(),right=await page.locator('.preview-column').boundingBox();assert(left.x<right.x);assert(Math.abs(left.y-right.y)<3);
  assert((await page.locator('#prep-live-preview').textContent()).includes('硕士'));assert(await page.locator('#prep-confirm-inline').isEnabled(),'missing fields do not block known materials');
  for(const viewport of [{width:1440,height:900},{width:1280,height:720},{width:900,height:700},{width:390,height:844}]){
    await page.setViewportSize(viewport);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'no horizontal clipping');
    assert.equal(await page.evaluate(()=>document.scrollingElement.scrollHeight<=innerHeight+1),true,'document stays fixed');
    const left=page.locator('.decision-column'),right=page.locator('.preview-column');
    assert((await left.boundingBox()).height>280);assert((await right.boundingBox()).height>280);
    await left.evaluate(e=>e.scrollTop=e.scrollHeight);
    assert(await left.evaluate(e=>e.scrollTop>0),'left independently scrolls');
    const leftTop=await left.evaluate(e=>e.scrollTop);
    await right.evaluate(e=>e.scrollTop=e.scrollHeight);
    assert(await right.evaluate(e=>e.scrollTop>0),'right independently scrolls');
    assert.equal(await left.evaluate(e=>e.scrollTop),leftTop,'right scrolling does not move left');
    assert.equal(await page.evaluate(()=>scrollY),0);
    await left.evaluate(e=>e.scrollTop=0);await right.evaluate(e=>e.scrollTop=0);
  }
  await page.setViewportSize({width:1440,height:900});
  if(process.env.UI_EVIDENCE){require('fs').mkdirSync(process.env.UI_EVIDENCE,{recursive:true});await page.screenshot({path:process.env.UI_EVIDENCE+'/preparation-layout.png'});}
  let jobs=await(await fetch(base+'/management/api/jobs')).json();assert.equal(jobs.jobs.length,2);
  await page.getByRole('button',{name:'投递管理',exact:true}).click();assert(await page.locator('#management-view').isVisible());
  assert.deepEqual(await page.locator('.main-tabs button').allTextContents(),['投递管理','我的资料']);
  const before=await(await fetch(base+'/api/state')).json();
  await frame.getByRole('row',{name:'查看 示例公司 产品岗位甲 详情',exact:true}).getByRole('button',{name:'继续投递',exact:true}).click();
  await page.locator('#prep-live-preview').waitFor();
  const after=await(await fetch(base+'/api/state')).json();assert.equal(after.sessions.length,before.sessions.length);
  assert.equal(await page.locator('[data-material-module="internships"] [data-choice-entry]').count(),3);
  assert.equal(await page.locator('[data-material-module="internships"] [data-set-version]').count(),3);
  const education=page.locator('[data-material-module="edu"]');assert(await education.isVisible());
  const module=page.locator('[data-material-module="internships"]'),record=module.locator('[data-material-entry]').first();
  await record.locator('[data-set-details]>summary').click();
  assert.deepEqual((await record.locator('[data-set-value]').evaluateAll(es=>es.map(e=>e.dataset.setValue))).sort(),after.fields.filter(f=>f.category==='employment').map(f=>f.id).sort());
  assert(await record.getByLabel('经历性质',{exact:true}).isVisible());
  await record.locator('[data-new-set-version]').click();
  await page.locator('#set-version-dialog').waitFor({state:'visible'});
  assert((await page.locator('#set-version-dialog [data-set-value]').evaluateAll(es=>es.every(e=>e.value===''))),'new versions start empty');
  await page.locator('#set-version-name').fill('虚构整组新版');
  await page.locator('#set-version-dialog [data-set-value="company"]').fill('新版示例公司');
  await page.locator('#set-version-dialog [data-set-value="employment_type"]').fill('实习');
  await page.waitForFunction(()=>document.querySelector('#preview-save-state').textContent.includes('草稿已自动保存'));
  await page.reload();await page.locator('#prep-live-preview').waitFor();
  await record.locator('[data-new-set-version]').click();await page.locator('#set-version-dialog').waitFor({state:'visible'});
  assert.equal(await page.locator('#set-version-name').inputValue(),'虚构整组新版');
  assert.equal(await page.locator('#set-version-dialog [data-set-value="company"]').inputValue(),'新版示例公司');
  await page.locator('#set-version-submit').click();
  await page.locator('#set-version-dialog').waitFor({state:'hidden'});
  await page.waitForFunction(()=>document.querySelector('#prep-live-preview').textContent.includes('新版示例公司'));
  assert.equal(await record.locator('[data-set-value="description"]').inputValue(),'');
  await record.locator('[data-set-version]').selectOption('default');
  await page.waitForFunction(()=>!document.querySelector('#prep-live-preview').textContent.includes('新版示例公司'));
  const eid=await record.getAttribute('data-material-entry');const original=(await(await fetch(base+'/api/state')).json()).entries.find(e=>e.id===eid);
  assert.notEqual(original.values.company,'新版示例公司','new version does not overwrite defaults');
  assert.equal(await module.locator('[data-new-module-version],[data-composition-version]').count(),0);
  await page.reload();await page.locator('#prep-live-preview').waitFor();
  await page.getByRole('button',{name:'投递管理',exact:true}).click();
  const link='https://sample.jobs.feishu.cn/123456/resume/1234567890123456789/apply';
  await frame.locator('#intake-text').fill(link+'\n示例科技 用户增长产品经理（平台运营）');
  await frame.locator('#intake-preview').click();
  await frame.getByRole('dialog',{name:'确认录入岗位'}).waitFor();
  assert.equal(await frame.locator('[data-input-key="company"]').inputValue(),'示例科技');
  assert.equal(await frame.locator('[data-input-key="role"]').inputValue(),'用户增长产品经理（平台运营）');
  assert.equal(await frame.locator('[data-input-key="source_url"]').inputValue(),link);
  assert.equal((await(await fetch(base+'/management/api/jobs')).json()).jobs.length,2);
  await frame.locator('#confirm-input').click();
  await frame.getByRole('row',{name:'查看 示例科技 用户增长产品经理（平台运营） 详情',exact:true}).waitFor();
  await page.reload();
  await frame.getByRole('row',{name:'查看 示例科技 用户增长产品经理（平台运营） 详情',exact:true}).waitFor();
  const saved=(await(await fetch(base+'/management/api/jobs')).json()).jobs.find(j=>j.company==='示例科技');
  assert.equal(saved.source_url,link);assert.equal(saved.official_url,'');assert.deepEqual(saved.timeline,[]);
  assert.equal(saved.application_status,'未投递');assert.equal(saved.role,'用户增长产品经理（平台运营）');
  assert.equal((await(await fetch(base+'/api/state')).json()).sessions.length,before.sessions.length);
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
  assert.deepEqual(errors,[]);console.log('PASS unified origin, two tabs, real table/detail navigation, one local table, left/right preview, managed session reuse and all record versions, reload, mobile width; 0 page errors');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
