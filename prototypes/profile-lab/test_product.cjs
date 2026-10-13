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
  await frame.getByRole('button',{name:'开始投递',exact:true}).last().click();await page.locator('#prep-live-preview').waitFor();
  assert.equal(new URL(page.url()).origin,base);assert.equal(await page.locator('#application-url').inputValue(),'https://example.com/apply');
  const left=await page.locator('.decision-column').boundingBox(),right=await page.locator('.preview-column').boundingBox();assert(left.x<right.x);assert(Math.abs(left.y-right.y)<3);
  assert((await page.locator('#prep-live-preview').textContent()).includes('硕士'));assert(await page.locator('#prep-confirm-inline').isDisabled());
  let jobs=await(await fetch(base+'/management/api/jobs')).json();assert.equal(jobs.jobs.length,2);
  await page.getByRole('button',{name:'投递管理',exact:true}).click();assert(await page.locator('#management-view').isVisible());
  assert.deepEqual(await page.locator('.main-tabs button').allTextContents(),['投递管理','我的资料']);
  const before=await(await fetch(base+'/api/state')).json();
  await frame.getByRole('row',{name:'查看 示例公司 产品岗位甲 详情',exact:true}).getByRole('button',{name:'开始投递',exact:true}).click();
  await page.locator('#prep-live-preview').waitFor();
  const after=await(await fetch(base+'/api/state')).json();assert.equal(after.sessions.length,before.sessions.length);
  assert.equal(await page.locator('[data-choice-entry]').count(),3);
  assert.equal(await page.locator('[data-prep-version]').count(),3);
  await page.reload();await page.locator('#prep-live-preview').waitFor();
  await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
  assert.deepEqual(errors,[]);console.log('PASS unified origin, two tabs, real table/detail navigation, one local table, left/right preview, managed session reuse and all record versions, reload, mobile width; 0 page errors');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
