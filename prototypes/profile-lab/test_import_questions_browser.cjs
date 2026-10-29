const {chromium}=require('playwright');
const {spawn}=require('child_process');
const assert=require('node:assert/strict');

let currentProfile=false;
async function fixture(source,check){
 const server=spawn(process.env.PYTHON||'python3',['-u','test_import_questions_fixture.py',...(source?['--source']:[]),...(currentProfile?['--current']:[])],{cwd:__dirname,stdio:['ignore','pipe','pipe']});
 let browser;
 try{
  const base=await new Promise((resolve,reject)=>{
   const timeout=setTimeout(()=>reject(Error('fixture startup timed out')),30000);
   server.stdout.on('data',d=>{const m=d.toString().match(/http:\/\/127\.0\.0\.1:\d+/);if(m){clearTimeout(timeout);resolve(m[0]);}});
   server.on('exit',()=>{clearTimeout(timeout);reject(Error('fixture stopped'));});
   server.stderr.on('data',d=>process.stderr.write(d));
  });
  browser=await chromium.launch({headless:true});const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#profile/honors');await page.locator('#pending-profile').click();
  await page.locator('[data-review-form]').waitFor();
  await check(page,async()=>await(await page.request.get(base+'/api/state')).json());
  assert.deepEqual(errors,[]);
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
}

(async()=>{
 for(const current of [false,true]){
 currentProfile=current;
 await fixture(false,async(page,state)=>{
  const form=page.locator('[data-review-form]');assert.equal(await form.locator('[data-review-question]').count(),3);
  const meaning=form.locator('[data-review-question]').filter({hasText:'国家级二等奖'});
  // Editing a suggested value must select adoption without an extra hidden step.
  await meaning.locator('[data-review-field=award_prize]').fill('二等奖');
  assert.equal(await meaning.locator('[data-review-action]').inputValue(),'apply');
  await meaning.locator('[data-review-note]').fill('确认该简称的含义');
  await form.locator('[data-complete-review]').click();
  await page.getByText('识别确认已完成 · fiction.txt',{exact:true}).waitFor();
  let s=await state();assert.equal(s.entries.filter(e=>e.category==='honors').length,0);
  const p=s.imports[0];assert.equal(p.candidates.find(c=>c.field_id==='award_prize').value,'二等奖');assert.ok(!p.candidates.some(c=>c.field_id==='award_date'));
  await page.reload();await page.locator('#pending-profile').click();
  await page.getByText('识别确认已完成 · fiction.txt',{exact:true}).waitFor();
  await page.getByRole('button',{name:'保存此组',exact:true}).click();await page.locator('#import-dialog').waitFor({state:'hidden'});
  s=await state();const e=s.entries.find(e=>e.category==='honors');assert.equal(e.values.award_level,'国家级');assert.equal(e.values.award_prize,'二等奖');assert.ok(!e.values.award_date);
  console.log('PASS optional form: accept meaning, skip date, note retained, no shared write before explicit save, reload and save verified');
 });
 await fixture(true,async(page,state)=>{
  await page.locator('[data-complete-review]').click();await page.getByText('识别确认已完成 · fiction.txt',{exact:true}).waitFor();
  const unresolved=page.locator('[data-skill-import]').filter({hasText:'虚构创新赛'});
  assert.ok(await unresolved.locator('[data-unit-import=replace]').isDisabled());
  await page.locator('[data-skill-import]').filter({hasText:'另一次校级奖'}).locator('[data-unit-import=replace]').click();
  assert.equal((await state()).entries.filter(e=>e.category==='honors').length,1);
  await page.reload();await page.locator('#pending-profile').click();await page.locator('[data-edit-review]').click();
  const form=page.locator('[data-review-form]'),question=form.locator('[data-review-question]').filter({hasText:'归属仍不清楚'});
  await question.locator('[data-review-action]').selectOption('confirm');
  assert.ok(await form.locator('[data-review-question]').filter({hasText:'另一次校级奖'}).locator('[data-review-action]').isDisabled());
  await page.locator('[data-complete-review]').click();await page.getByText('识别确认已完成 · fiction.txt',{exact:true}).waitFor();
  assert.equal((await state()).entries.filter(e=>e.category==='honors').length,1);
  await page.locator('[data-skill-import]').filter({hasText:'虚构创新赛'}).locator('[data-unit-import=replace]').click();
  await page.locator('#import-dialog').waitFor({state:'hidden'});
  assert.equal((await state()).entries.filter(e=>e.category==='honors').length,2);
  console.log('PASS unresolved source skip blocks only its group; other group saves; reload, explicit source confirmation and remaining save work; saved answers locked');
 });
 console.log('PASS source review contract '+(currentProfile?'30':'legacy'));
 }
})().catch(e=>{console.error(e);process.exitCode=1;});
