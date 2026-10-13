/* Complete education sets and in-context edits in an isolated, fictional site. */
const {chromium}=require('playwright');
const {spawn}=require('node:child_process');const assert=require('node:assert/strict');
const python=process.env.PYTHON || 'python3';
const source=`from lab import Lab
from server import make_server
from test_requirement_sets import mapping,education_rule,requirement,condition
import tempfile
class FixtureMapper:
 def map(self,fields,profile):
  mappings=[]
  for f in fields:
   if f['id']=='w_education':
    m=mapping(f['id'],None,'education',education_rule('education','高中' if '从高中' in f['instructions'] else '本科'))
    m['requirement']['summary']=f['instructions']
    m['members']=[dict(website_id=c['id'],field_id=c['id'],new_field=None) for c in f['children']]
   elif f['id']=='w_highest_school':m=mapping(f['id'],'school','education',education_rule('highest',selection='highest'))
   elif f['id']=='w_bachelor_school':m=mapping(f['id'],'school','education',requirement('bachelor','one',filters=[condition('degree',['本科'],'education_level')]))
   elif f['id']=='w_mentor':
    known=next((p for p in profile if p['label']=='导师'),None)
    m=mapping(f['id'],known['id'] if known else None,'education',requirement('mentor','one',filters=[condition('degree',['硕士'],'education_level')]))
    if not known:m.update(status='new',new_field=dict(label='导师',category='education',type='text'))
   else:raise ValueError('Unexpected fictional question')
   mappings.append(m)
  return dict(engine='离线虚构要求',mappings=mappings)
with tempfile.TemporaryDirectory(prefix='education-browser-') as folder:
 lab=Lab(folder);lab.new_session("虚构教育集合演练")
 for school,level,major in [('乙大学','本科','本科专业'),('丙大学','硕士','研究生专业')]:
  e=lab.mutate(lambda s:lab.new_entry(s,'education'))
  lab.save_profile([dict(entry_id=e['id'],field_id=k,value=v) for k,v in dict(school=school,degree=level,major=major).items()])
  lab.create_version(e['id'],'school',school+'英文名','英文名称')
 server=make_server(lab,0,FixtureMapper());print(server.server_port,flush=True);server.serve_forever()
`;
(async()=>{
 const server=spawn(python,['-u','-c',source],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const port=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(Number(d.toString().trim())));server.once('exit',()=>reject(Error('server failed')));});
  const base='http://127.0.0.1:'+port;browser=await chromium.launch({...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{}),headless:true});const page=await browser.newPage({viewport:{width:1440,height:1100}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));const read=async()=>await(await fetch(base+'/api/state')).json();const checks=[];
  async function check(name,fn){await fn();checks.push(name);console.log('PASS '+name);}
  await page.goto(base+'/#profile/education');
  await check('profile shows two complete sets before any website scan',async()=>{
   await page.locator('[data-profile-set="college"]').waitFor();
   const before=await read();
   assert.equal(await page.locator('[data-profile-set]').count(),2);
   assert.equal(await page.locator('[data-profile-set="college"] [data-set-member]').count(),2);
   assert.equal(await page.locator('[data-profile-set="high-school"] [data-set-member]').count(),2);
   assert.equal(await page.locator('[data-profile-set="college"] .set-composition').textContent(),'本科＋硕士');
   assert((await page.locator('[data-profile-set="high-school"] [data-set-gap]').textContent()).includes('缺少高中'));
   assert.equal(await page.locator('[data-profile-set="high-school"] .set-composition').textContent(),'高中（待补）＋本科＋硕士');
   assert.equal(await page.locator('[data-profile-group] input[type=checkbox]').count(),0);
   assert.equal(await page.locator('[data-profile-entry][open]').count(),0);
   await page.locator('[data-profile-set="college"] [data-edit-group-entry]').first().click();
   assert.equal(await page.locator('[data-profile-entry][open]').count(),1);
   assert(await page.locator('#profile-view').isVisible());
   await page.locator('[data-profile-entry][open] [data-add-version]').first().click();
   await page.locator('#new-version-dialog').getByRole('button',{name:'取消',exact:true}).click();
   assert.deepEqual(await read(),before);
   await page.reload();await page.locator('[data-profile-set="college"]').waitFor();
   assert(await page.locator('[data-profile-set="college"]').isVisible());
   await page.screenshot({path:'/tmp/profile-visible-groups-ui.png',fullPage:true});
  });
  await page.goto(base+'/?lab=1#practice/'+(await read()).sessions[0].id);await page.locator('#demo-kind').selectOption('education-college');
  await check('college set is automatic despite multiple records and versions',async()=>{
   await page.locator('#scan-demo').click();await page.locator('[data-auto-group="education"]').waitFor();
   assert.equal(await page.locator('[data-choice-entry]').count(),0);assert.equal(await page.locator('[data-auto-entry]').count(),2);assert.equal(await page.locator('[data-missing]').count(),0);
   await page.locator('#fill-start').click();await page.locator('[data-filled-entry]').first().waitFor();
   assert.deepEqual(await page.locator('[data-site="w_education"] [data-filled-field="school"]').evaluateAll(es=>es.map(e=>e.value)),['乙大学','丙大学']);
   assert.equal(await page.locator('[data-site="w_highest_school"]').inputValue(),'丙大学');assert.equal(await page.locator('[data-site="w_bachelor_school"]').inputValue(),'乙大学');
  });
  await check('high-school requirement identifies missing coverage and blocks filling',async()=>{
   await page.locator('#demo-kind').selectOption('education-high-school');await page.locator('#scan-demo').click();await page.locator('[data-missing]').first().waitFor();
   assert((await page.locator('#missing-fields').textContent()).includes('高中'));assert(await page.locator('#fill-start').isDisabled());assert.equal(await page.locator('[data-choice-entry]').count(),0);
  });
  await check('missing record completed in application without switching tabs',async()=>{
   await page.locator('#missing-fields [data-add-material]').first().click();await page.waitForFunction(()=>document.querySelectorAll('[data-auto-entry]').length===3);
   const before=await read(),entry=before.entries.find(e=>e.category==='education'&&Object.keys(e.values).length===0);
   const details=page.locator('[data-auto-entry="'+entry.id+'"]');await details.locator('summary').click();
   const degree=details.locator('[data-answer-key="'+entry.id+'/degree"]');await degree.locator('[data-version-content]').fill('高中');await degree.locator('[data-version-mode="update"]').click();
   await page.waitForFunction(()=>document.querySelector('#toast').textContent==='更新当前版本已完成');
   const school=details.locator('[data-answer-key="'+entry.id+'/school"]');await school.locator('[data-version-content]').fill('甲高中');await school.locator('[data-version-mode="update"]').click();
   await page.waitForFunction(()=>!document.querySelector('#fill-start').disabled);
   assert(await page.locator('#practice-view').isVisible());assert.equal(await page.locator('[data-auto-entry]').count(),3);
   await page.locator('#fill-start').click();await page.waitForFunction(()=>document.querySelectorAll('[data-filled-entry]').length===3);
   assert.deepEqual(await page.locator('[data-filled-field="school"]').evaluateAll(es=>es.map(e=>e.value)),['甲高中','乙大学','丙大学']);
  });
  await check('education added during application appears in its profile set only',async()=>{
   await page.locator('#view-profile').click();await page.locator('#category-nav [data-category="education"]').click();await page.locator('[data-profile-set="college"]').waitFor();
   assert.equal(await page.locator('[data-profile-set="college"] [data-set-member]').count(),2);
   assert.equal(await page.locator('[data-profile-set="high-school"] [data-set-member]').count(),3);
   assert.equal(await page.locator('[data-profile-set="high-school"] [data-set-gap]').count(),0);
   assert.equal(await page.locator('[data-profile-set="high-school"] .set-composition').textContent(),'高中＋本科＋硕士');
   await page.goto(base+'/?lab=1#practice/'+(await read()).sessions[0].id);
  });
  await check('switching website scope excludes high school without user selection',async()=>{
   await page.locator('#demo-kind').selectOption('education-college');await page.locator('#scan-demo').click();await page.waitForFunction(()=>document.querySelectorAll('[data-auto-entry]').length===2);
   assert.equal(await page.locator('[data-choice-entry]').count(),0);await page.locator('#fill-start').click();await page.waitForFunction(()=>document.querySelectorAll('[data-filled-entry]').length===2);assert.equal(await page.locator('[data-filled-entry]').count(),2);
  });
  await check('new mentor field is saved on master record in context',async()=>{
   await page.evaluate(async()=>{const label=document.createElement('label');label.textContent='研究生导师';const input=document.createElement('input');input.dataset.site='w_mentor';input.required=true;label.append(input);document.querySelector('#mock-form').append(label);await scan(readLocalManifest());});
   const missing=page.locator('[data-missing="w_mentor"]');await missing.locator('[data-missing-value]').fill('虚构导师');await missing.locator('[data-missing-mode="update"]').click();await missing.waitFor({state:'hidden'});
   const state=await read(),field=state.fields.find(f=>f.label==='导师');assert.equal(field.category,'education');
   const owners=state.entries.filter(e=>e.values[field.id]);assert.equal(owners.length,1);assert.equal(owners[0].values.degree,'硕士');
   await page.locator('#fill-start').click();await page.waitForFunction(()=>document.querySelector('[data-site="w_mentor"]').value==='虚构导师');assert.equal(await page.locator('[data-site="w_mentor"]').inputValue(),'虚构导师');
  });
  await check('editing one canonical record updates both profile sets and application',async()=>{
   const before=await read(),entry=before.entries.find(e=>e.values.degree==='本科');
   await page.locator('#view-profile').click();await page.locator('#category-nav [data-category="education"]').click();await page.locator('[data-profile-set="college"]').waitFor();
   await page.locator('[data-profile-set="college"] [data-edit-group-entry="'+entry.id+'"]').click();
   await page.locator('[data-profile-answer-key="'+entry.id+'/school"] input').fill('乙大学（更新）');
   await page.locator('#save-profile').click();await page.waitForFunction(()=>document.querySelector('#toast').textContent==='已保存到底稿');
   for(const set of ['college','high-school'])assert((await page.locator('[data-profile-set="'+set+'"] [data-set-member="'+entry.id+'"] strong').textContent()).includes('乙大学（更新）'));
   assert.equal((await read()).entries.length,before.entries.length);
   await page.goto(base+'/?lab=1#practice/'+(await read()).sessions[0].id);await page.locator('#fill-start').click();
   await page.waitForFunction(()=>document.querySelector('[data-site="w_bachelor_school"]').value==='乙大学（更新）');
  });
  await check('reloading restores the scoped plan and local multi-row form',async()=>{
   await page.reload();await page.goto(base+'/?lab=1#practice/'+(await read()).sessions[0].id);await page.locator('[data-auto-group="education"]').waitFor();
   assert.equal(await page.locator('[data-choice-entry]').count(),0);assert.equal(await page.locator('[data-auto-entry]').count(),2);assert.equal(await page.locator('#demo-kind').inputValue(),'education-college');
   await page.locator('#fill-start').click();await page.waitForFunction(()=>document.querySelector('[data-site="w_mentor"]').value==='虚构导师');
   assert.equal(await page.locator('[data-filled-entry]').count(),2);
   await page.screenshot({path:'/tmp/profile-requirement-set-ui.png',fullPage:true});
  });
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:checks.length,pageErrors:errors.length}));
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
