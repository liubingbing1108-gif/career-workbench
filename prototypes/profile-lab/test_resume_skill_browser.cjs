const {chromium}=require('playwright'),{spawn}=require('child_process'),assert=require('node:assert/strict');
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','test_resume_skill_fixture.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const base=await new Promise((resolve,reject)=>{server.stdout.on('data',d=>{const m=d.toString().match(/http:\/\/127\.0\.0\.1:\d+/);if(m)resolve(m[0]);});server.on('exit',()=>reject(Error('fixture stopped')));server.stderr.on('data',d=>process.stderr.write(d));});
  browser=await chromium.launch({headless:true});const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#profile/honors');await page.locator('#pending-profile').click();
  const unit=page.locator('[data-skill-import]').first();await unit.waitFor();
  const initial=await(await page.request.get(base+'/api/state')).json(),entry=initial.entries.find(e=>e.category==='honors');
  await unit.locator('[data-identity-choice]').selectOption(entry.id);await unit.locator('[data-confirm-identity]').click();
  await unit.getByRole('button',{name:'都保留（同一条资料的不同版本）',exact:true}).waitFor();
  assert.ok((await unit.textContent()).includes('校奖学金一等奖'));assert.ok((await unit.textContent()).includes('示例大学校级奖学金一等奖'));
  await unit.getByRole('button',{name:'都保留（同一条资料的不同版本）',exact:true}).click();await page.locator('#import-dialog').waitFor({state:'hidden'});
  await page.reload();await page.locator('[data-category=honors]').click();
  let card=page.locator(`[data-library-record="${entry.id}"]`);await card.waitFor();if(!await card.evaluate(e=>e.open))await card.locator(':scope > summary').click();
  const select=card.locator('[data-record-version]');assert.equal(await select.locator('option').count(),2);
  const versionId=await select.locator('option').last().getAttribute('value');await select.selectOption(versionId);
  assert.equal(await card.locator('[data-library-field=award_name]').inputValue(),'示例大学校级奖学金一等奖');
  assert.equal(await card.locator('[data-library-field=award_details]').inputValue(),'经学校评定。');
  await select.selectOption('default');assert.equal(await card.locator('[data-library-field=award_name]').inputValue(),'校奖学金一等奖');
  const saved=await(await page.request.get(base+'/api/state')).json();assert.equal(saved.entries.filter(e=>e.category==='honors').length,1);assert.equal(saved.files.length,2);
  assert.equal(saved.entries.find(e=>e.id===entry.id).values.award_name,entry.values.award_name);assert.deepEqual(errors,[]);
  console.log('PASS: identity confirmation, A/B preview, keep both, refresh, two usable whole-record versions, original default and files retained, no page errors');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
