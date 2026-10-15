/* Fictional local fixture: user-driven removal and application confirmation. */
const {chromium}=require('playwright');
const {spawn}=require('child_process');const assert=require('node:assert/strict');
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','test_product_fixture.py'],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const base=(await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(d.toString().trim()));server.once('exit',()=>reject(Error('fixture stopped')));})).replace(/\/$/,'');
  const api=async(path,body)=>{const r=await fetch(base+path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json','Origin':base},body:body?JSON.stringify(body):undefined});const result=await r.json();assert(r.ok,JSON.stringify(result));return result;};
  const state=await api('/api/state'),session=state.sessions[0],sid=session.id;
  const manifest=structuredClone(session.website),mappings=manifest.mappings;delete manifest.mappings;delete manifest.engine;delete manifest.contract_version;
  manifest.fields.find(f=>f.id==='new').decision_required=false;
  manifest.fields.find(f=>f.id==='edu').children.push({id:'advisor',label:'导师',required:false});
  mappings.find(m=>m.website_id==='edu').members.push({website_id:'advisor',field_id:null,new_field:{label:'导师',category:'education',type:'text'}});
  await api('/api/preparation/mapping',{session_id:sid,manifest,interpretation:{engine:'fictional',mappings}});
  const jobsBefore=(await api('/management/api/bootstrap')).jobs;
  browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/#practice/'+sid);await page.locator('#prep-live-preview').waitFor();
  const first=page.locator('[data-missing-key]').filter({has:page.getByRole('combobox',{name:'语言程度',exact:true})});
  await first.locator('[data-remove-optional]').click();await first.waitFor({state:'detached'});
  assert.equal(await page.locator('[data-scalar-material="new"]').count(),0);
  const mentor=page.locator('[data-missing-key]').filter({has:page.getByRole('textbox',{name:'导师',exact:true})});
  await mentor.locator('[data-missing-value]').fill('虚构未保存导师');
  await mentor.locator('[data-remove-optional]').click();await mentor.waitFor({state:'detached'});
  assert(!(await page.locator('#prep-live-preview').textContent()).includes('导师'));
  // Removing a suggestion must not break saving the remaining complete record.
  const record=page.locator('[data-material-module="edu"] [data-material-entry]').first();
  await record.locator('[data-set-details]>summary').click();
  await record.locator('[data-set-save="session"]').click();
  await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('整组资料已保存'));

  await page.reload();await page.locator('#prep-live-preview').waitFor();assert.equal(await page.locator('[data-remove-optional]').count(),0);
  assert.equal((await api('/management/api/bootstrap')).jobs.find(j=>j.id===session.management_job_id).application_status,'未投递');
  // Going back alone is not confirmation and creates no dates.
  await page.locator('#back-management').click();await page.goto(base+'/#practice/'+sid);await page.locator('#prep-live-preview').waitFor();
  assert.equal((await api('/management/api/bootstrap')).jobs.find(j=>j.id===session.management_job_id).timeline.length,0);
  await page.locator('.practice-toolbar [data-confirm-application]').click();
  await page.locator('#application-confirmation-status').filter({hasText:'已投递'}).waitFor();
  const jobsAfter=(await api('/management/api/bootstrap')).jobs,job=jobsAfter.find(j=>j.id===session.management_job_id);
  assert.equal(job.application_status,'已投递');assert.equal(job.timeline.filter(i=>i.label==='投递日期').length,1);
  assert.deepEqual(jobsAfter.find(j=>j.id!==job.id),jobsBefore.find(j=>j.id!==job.id));
  await page.reload();await page.locator('#application-confirmation-status').filter({hasText:'已投递'}).waitFor();assert(!(await page.locator('.practice-toolbar [data-confirm-application]').isVisible()));
  const after=await api('/api/state');for(const key of ['entries','versions','answer_versions','files'])assert.deepEqual(after[key],state[key]);assert.deepEqual(after.sessions[1],state.sessions[1]);
  if(process.env.UI_EVIDENCE){require('fs').mkdirSync(process.env.UI_EVIDENCE,{recursive:true});await page.screenshot({path:process.env.UI_EVIDENCE+'/confirmed-application.png'});}
  assert.deepEqual(errors,[]);console.log('PASS D90 optional blank deletion, draft clearing, reload, no implicit submission, explicit confirmation/status/date, other job/shared data isolation; 0 page errors');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
