/* Fictional pages and localhost only; no real applicant account. */
const {chromium}=require('playwright');
const {spawn}=require('child_process');const assert=require('node:assert/strict');const fs=require('fs');const path=require('path');
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','test_product_fixture.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const base=(await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(d.toString().trim()));server.once('exit',()=>reject(Error('fixture stopped')));})).replace(/\/$/,'');
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});
  await page.goto(base);const frame=page.frameLocator('#management-frame');await frame.getByRole('row',{name:'查看 示例公司 产品岗位甲 详情',exact:true}).click();
  await frame.locator('#manual-application-url').fill('https://app.mokahr.com/campus_apply/fictional/123#/candidateHome/resume');
  await frame.locator('#save-application-url').click();await frame.getByText('投递链接已保存，可直接开始',{exact:true}).waitFor();
  assert.equal(await frame.locator('#manual-application-url').inputValue(),'https://app.mokahr.com/campus_apply/fictional/123#/candidateHome/resume');
  await frame.locator('#detail-query').waitFor();assert.equal(await frame.locator('#detail-query').textContent(),'查询官网投递进度');
  await page.route('**/api/jobs/*/query',route=>route.fulfill({json:{status:'needs_user',changed:false,message:'请在Chrome完成该官网登录或验证码，然后重新点击查询。'}}));
  await frame.locator('#detail-query').click();await frame.locator('#query-result').getByText('请在Chrome完成该官网登录或验证码，然后重新点击查询。').waitFor();
  const url='https://app.mokahr.com/campus_apply/fictional/123#/candidateHome/applications';
  await page.route('https://app.mokahr.com/**',route=>route.fulfill({body:'<html><body></body></html>',contentType:'text/html'}));await page.goto(url);
  const script=fs.readFileSync(path.join(__dirname,'../icbc-native-extension/progress-reader.js'),'utf8');
  const read=async html=>{await page.setContent(html);await page.addScriptTag({content:script});return page.evaluate(url=>JobProgressReader.read({url,role:'产品经理'}),url);};
  assert.deepEqual((await read('<div class="application-card"><h3>产品经理</h3><span class="status">面试中</span></div>')).records,[{role:'产品经理',stage:'面试中'}]);
  assert.equal((await read('<div class="application-card"><h3>产品经理</h3><span class="status">面试中</span></div>'.repeat(2))).records.length,2);
  assert.deepEqual((await read('<div class="abc123"><div>第 1 志愿 产品经理</div><a href="#">修改申请</a><div>状态 : 等待筛选 项目 : -</div></div>')).records,[{role:'第 1 志愿 产品经理',stage:'等待筛选'}]);
  assert.equal((await read('<form><h3>产品经理</h3><span class="status">已提交</span><input value="未保存"></form>')).records.length,0);
  assert.equal((await read('<div class="application-card"><h3>AI产品经理</h3><span class="status">Offer</span></div>')).records.length,0);
  assert.equal((await read('<p>请先登录</p><input type="password">')).status,'needs_user');
  assert.equal((await read('<div class="application-card"><h3>其他岗位</h3><span>状态 : 等待筛选</span></div>')).status,'records');
  await read('<div onclick="document.body.dataset.clicked=\'records\'">我的投递</div><button onclick="document.body.dataset.clicked=\'submit\'">提交申请</button>');
  await page.evaluate(url=>JobProgressReader.navigate({url},'我的投递',location.href),url);assert.equal(await page.locator('body').getAttribute('data-clicked'),'records');
  await assert.rejects(page.evaluate(url=>JobProgressReader.navigate({url},'提交申请',location.href),url));
  console.log('PASS D91 manual URL UI, query feedback, record reading, ambiguity and read-only navigation');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
