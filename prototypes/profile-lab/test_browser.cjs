/* Offline browser integration: fictional data, independent Chrome test profile. */
const {chromium}=require('playwright');
const {spawn}=require('child_process');const assert=require('node:assert/strict');const path=require('node:path');
const python=process.env.PYTHON || 'python3';
const source=`from lab import Lab
from server import make_server
from requirements import requirement
import tempfile
class FixtureMapper:
 def map(self,fields,profile):
  known={'w_name':('name','basic'),'w_email':('email','contact'),'w_employment':(None,'employment')}
  existing=next((f for f in profile if f['label']=='最早可以入职的日期'),None)
  if existing:known['w_available']=(existing['id'],existing['category'])
  result={'engine':'离线虚构夹具映射','mappings':[{'website_id':f['id'],'field_id':known.get(f['id'],(None,None))[0],'category':known.get(f['id'],(None,None))[1],'status':'mapped' if f['id'] in known else 'new','reason':'离线测试契约'} for f in fields]}
  for m in result['mappings']:
   if m['category']=='employment':
    m['requirement']=requirement(m['website_id'],'choose')
    m['members']=[{'website_id':c['id'],'field_id':c['id']} for c in next(f for f in fields if f['id']==m['website_id']).get('children',[])]
  return result
with tempfile.TemporaryDirectory(prefix='profile-browser-test-') as directory:
 lab=Lab(directory);lab.new_session("虚构界面演练");server=make_server(lab,0,FixtureMapper());print(server.server_port,flush=True);server.serve_forever()
`;
(async()=>{
 const server=spawn(python,['-u','-c',source],{cwd:__dirname,stdio:['ignore','pipe','pipe']});let browser;
 try{
  const port=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(Number(d.toString().trim())));server.once('exit',()=>reject(Error('test server failed')));});
  const base='http://127.0.0.1:'+port;browser=await chromium.launch({...(process.env.PLAYWRIGHT_CHANNEL?{channel:process.env.PLAYWRIGHT_CHANNEL}:{}),headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const read=async()=>await(await fetch(base+'/api/state')).json();const post=async(url,data)=>{const r=await fetch(base+url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});if(!r.ok)throw Error(await r.text());return r.json();};
  const checks=[];async function check(name,fn){await fn();checks.push(name);console.log('PASS '+name);}
  const upload=async(name,content)=>{await page.locator('#resume-file').setInputFiles(content?{name,mimeType:'text/plain',buffer:Buffer.from(content)}:path.join(__dirname,'web/samples/sample.txt'));await page.locator('#import-dialog').waitFor({state:'visible'});await page.waitForFunction(()=>document.querySelector('#import-task-preview')?.textContent.includes('完成'));};
  const close=async()=>{if(await page.locator('#import-dialog').isVisible())await page.getByRole('button',{name:'关闭导入预览',exact:true}).click();};
  await page.goto(base+'/?lab=1');await page.waitForSelector('#category-nav button');
  await check('blank full form editable without upload',async()=>{assert.equal((await read()).files.length,0);await page.locator('[data-library-record]>summary').first().click();await page.getByLabel('中文姓名',{exact:true}).fill('手填虚构');await page.locator('[data-save-record="update"]').first().click();await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('已保存'));assert.equal((await read()).entries[0].values.name,'手填虚构');});
  await check('initial import select all and explicit replace',async()=>{await upload();await page.locator('#select-all-import').click();await page.locator('.dialog-footer [data-import-mode="replace"]').click();await page.locator('#import-dialog').waitFor({state:'hidden'});assert.equal((await read()).entries[0].values.name,'Alex Example');});
  await check('same uploaded facts omitted from decisions',async()=>{await upload();assert.equal(await page.locator('[data-candidate]').count(),0);await close();});
  const change=(description)=>`Company: Example Labs\nRole: Research Intern\nEmployment type: Internship\nStart date: 2023-07-01\nEnd date: 2023-09-30\nDescription: ${description}`;
  // Derive exact fictional anchors from the installed sample, no real resume values.
  let initial=await read();let entry=initial.entries.find(e=>e.category==='employment');
  const changed=(d)=>`Company: ${entry.values.company}\nRole: ${entry.values.role}\nEmployment type: ${entry.values.employment_type}\nStart date: ${entry.values.started}\nEnd date: ${entry.values.ended}\nDescription: ${d}`;
  await check('one changed description save new preserves default',async()=>{await upload('new.txt',changed('新增描述版本'));assert.equal(await page.locator('[data-candidate]').count(),1);await page.locator('#select-all-import').click();await page.locator('.dialog-footer [data-import-mode="new"]').click();await page.locator('#import-dialog').waitFor({state:'hidden'});const s=await read();assert.equal(s.versions.length,2);assert.equal(s.entries.find(e=>e.id===entry.id).default_versions.description,s.versions[0].id);});
  await check('replace chosen version and ignore changed import',async()=>{await upload('replace.txt',changed('替换描述版本'));await page.locator('#select-all-import').click();await page.locator('.dialog-footer [data-import-mode="replace"]').click();await page.locator('#import-dialog').waitFor({state:'hidden'});assert.equal((await read()).versions.length,2);await upload('ignore.txt',changed('忽略的描述'));await page.locator('#select-all-import').click();await page.locator('.dialog-footer [data-import-mode="ignore"]').click();await page.locator('#import-dialog').waitFor({state:'hidden'});await upload('ignore-again.txt',changed('忽略的描述'));assert.equal(await page.locator('[data-candidate]').count(),0);await close();});
  await check('profile save ignores version buttons and retains field values',async()=>{await page.locator('#category-nav [data-category="employment"]').click();await page.locator('[data-library-record]').first().evaluate(e=>e.open=true);await page.locator('[data-save-record="update"]').first().click();await page.waitForFunction(()=>document.querySelector('#toast').textContent==='已保存这条资料');assert.equal((await read()).entries.find(e=>e.id===entry.id).values.company,entry.values.company);});
  const extra=[];
  for(const company of ['虚构公司乙','虚构公司丙']){const e=await post('/api/entries',{category:'employment'});await post('/api/profile',{values:[{entry_id:e.id,field_id:'company',value:company},{entry_id:e.id,field_id:'role',value:'虚构实习'}]});const v=await post('/api/versions/create',{entry_id:e.id,field_id:'description',content:company+'默认版'});extra.push({e,v});}
  await page.reload();await page.goto(base+'/?lab=1#practice/'+(await read()).sessions[0].id);
  await check('website scan precedes choices basic info reused',async()=>{assert.equal(await page.locator('[data-choice-entry]').count(),0);await page.locator('#scan-demo').click();await page.waitForSelector('[data-choice-entry]');assert.equal(await page.locator('[data-choice-entry]').count(),3);assert.equal(await page.locator('[data-missing="w_available"]').count(),1);assert.equal(await page.locator('[data-decision]').count(),1);assert(await page.locator('#fill-start').isDisabled());});
  await check('new website question saves only in this application',async()=>{await page.locator('[data-missing="w_available"] [data-missing-value]').fill('2027-07-01');await page.locator('[data-missing="w_available"] [data-missing-mode="update"]').click();await page.locator('[data-missing="w_available"]').waitFor({state:'hidden'});const s=await read(),f=s.fields.find(f=>f.label==='最早可以入职的日期');assert(f);assert.equal(s.answer_versions.filter(v=>v.field_id===f.id).length,0);});
  await check('choose two entries and independent description version',async()=>{await page.locator('[data-experience-none]').click();await page.waitForFunction(()=>application.decisions.find(x=>x.category==='employment').selected.length===0);await page.locator('[data-choice-entry="'+entry.id+'"] [data-experience]').check();await page.waitForFunction(id=>application.decisions.find(x=>x.category==='employment').selected.map(e=>e.id).join()===id,entry.id);await page.locator('[data-choice-entry="'+extra[1].e.id+'"] [data-experience]').check();await page.waitForFunction(ids=>JSON.stringify(application.decisions.find(x=>x.category==='employment').selected.map(e=>e.id))===JSON.stringify(ids),[entry.id,extra[1].e.id]);await page.locator('[data-choice-entry="'+entry.id+'"] > details').evaluate(e=>e.open=true);const block=page.locator('[data-answer-key="'+entry.id+'/description"]');await block.locator('[data-version-content]').fill('新增描述版本');await block.locator('[data-version-mode="session"]').click();await page.waitForFunction(()=>document.querySelector('#toast').textContent==='仅供本次使用已完成');await page.locator('#fill-start').click();await page.waitForFunction(()=>document.querySelectorAll('[data-filled-experience]').length===2);assert.equal(await page.locator('[data-filled-experience]').count(),2);assert.equal(await page.locator('[data-filled-experience="0"] [data-filled-field="description"]').inputValue(),'新增描述版本');assert.equal(await page.locator('[data-filled-experience="1"] [data-filled-field="company"]').inputValue(),'虚构公司丙');assert.equal(await page.locator('[data-site="w_name"]').inputValue(),'Alex Example');});
  await check('unsaved edits block execution and individual edits stay session-only',async()=>{await page.locator('[data-choice-entry="'+entry.id+'"] > details').evaluate(e=>e.open=true);let block=page.locator('[data-answer-key="'+entry.id+'/description"]');await block.locator('[data-version-content]').fill('临时修改');await page.locator('#fill-start').click();assert((await page.locator('#toast').textContent()).includes('还未选择保存方式'));const before=(await read()).versions.length;await block.locator('[data-version-mode="session"]').click();await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('仅供本次使用已完成'));assert.equal((await read()).versions.length,before);await page.locator('#fill-start').click();await page.waitForFunction(()=>document.querySelector('[data-filled-experience="0"] [data-filled-field="description"]').value==='临时修改');assert.equal(await page.locator('[data-filled-experience="0"] [data-filled-field="description"]').inputValue(),'临时修改');assert.equal(await block.locator('[data-version-mode="new"],[data-version-mode="update"]').count(),0);});
  await check('reorder selected entries changes actual fill order',async()=>{await page.locator('[data-choice-entry="'+extra[1].e.id+'"] [data-move-entry="up"]').click();await page.waitForFunction(id=>document.querySelector('[data-choice-entry]').dataset.choiceEntry===id,extra[1].e.id);await page.locator('#fill-start').click();await page.waitForFunction(()=>document.querySelector('[data-filled-experience="0"] [data-filled-field="company"]').value==='虚构公司丙');assert.equal(await page.locator('[data-filled-experience="1"] [data-filled-field="company"]').inputValue(),entry.values.company);});
  await check('fresh application isolates new answers and temporary text',async()=>{await page.locator('#new-session').click();await page.waitForFunction(()=>document.querySelector('#session-select').selectedOptions[0]?.textContent==='新的虚构演练'&&!document.querySelector('[data-choice-entry]'));await page.locator('#scan-demo').click();await page.waitForSelector('[data-choice-entry]');assert.equal(await page.locator('[data-missing="w_available"]').count(),1);assert.equal(await page.locator('[data-choice-entry="'+entry.id+'"] [data-answer-key="'+entry.id+'/description"] [data-version-content]').inputValue(),'替换描述版本');});
  await check('version choices hide imported filenames and revisions',async()=>{
    const labels=await page.locator('[data-version-select] option').allTextContents();
    assert.equal(labels.length,0);assert(labels.every(label=>!/\.(txt|pdf|docx)\b|修订/.test(label)));
    await page.locator('#view-profile').click();await page.locator('#category-nav [data-category="employment"]').click();
    await page.locator('[data-library-record="'+entry.id+'"] > summary').evaluate(e=>e.parentElement.open=true);
    assert.equal(await page.locator('[data-open-practice],.source,.version-list').count(),0);
    assert((await page.locator('[data-library-field-version] option').allTextContents()).every(label=>!/\.(txt|pdf|docx)\b|修订/.test(label)));
    const block=page.locator('[data-library-record="'+entry.id+'"] [data-library-field-wrap="description"]');
    assert.equal(await block.locator('[data-library-field]').count(),1);assert.equal(await block.locator('[data-new-field-version]').count(),0);
  });
  await check('stable profile modules have no version controls and save as a record',async()=>{
    await page.locator('#category-nav [data-category="basic"]').click();const card=page.locator('[data-library-record]').first();await card.evaluate(e=>e.open=true);assert.equal(await card.locator('[data-record-version],[data-new-field-version],[data-save-field]').count(),0);
    await card.locator('[data-library-field="name"]').fill('显式保存的虚构资料');await card.locator('[data-save-record="update"]').click();await page.waitForFunction(()=>document.querySelector('#toast').textContent==='已保存这条资料');assert.equal((await read()).entries.find(e=>e.category==='basic').values.name,'显式保存的虚构资料');
  });
  await check('unmatched website shows pending material state without executing',async()=>{
    const before=await read();
    const analysis={schema_version:1,url:'https://example.com/apply',title:'虚构待投递岗位',scanned_at:'2026-10-10T00:00:00Z',source:'虚构测试',sections:[{id:'education',label:'教育经历',repeatable:true,record_count:2,can_add:true,fields:[{id:'education[].school',label:'学校',type:'text',required:true,executor_field_ids:['education[0].school','education[1].school']}]}],attention:[{title:'资料待匹配',detail:'尚未匹配',kind:'choice'}],limits:['仅解析当前表单']};
    const session=await post('/api/form-analysis',{analysis});
    await page.goto(base+'/?analysis-test=1#practice/'+session.id);await page.locator('#prep-match').waitFor();await page.locator('.prep-unmatched').waitFor();
    assert(await page.locator('#practice-view').isVisible());assert((await page.locator('.prep-heading').textContent()).includes(analysis.title));
    assert.equal(await page.locator('[data-analysis-field]').count(),0);assert(await page.locator('#fill-start').isHidden());assert(await page.locator('#scan-demo').isHidden());
    assert(await page.locator('.prep-unmatched').isVisible());assert(await page.locator('#prep-match').isEnabled());
    const after=await read();for(const key of ['entries','fields','versions','answer_versions','files'])assert.deepEqual(after[key],before[key]);assert(!after.sessions.find(s=>s.id===session.id).website);
    await page.reload();await page.locator('#prep-match').waitFor();assert((await page.locator('.prep-heading').textContent()).includes(analysis.title));
    await page.locator('#view-profile').click();assert(await page.locator('#profile-view').isVisible());
  });
  await check('decision-first page supports versions new fields and complete preview',async()=>{
    const s=await read(),session=s.sessions.find(x=>x.form_analysis),employees=s.entries.filter(e=>e.category==='employment');
    const rule={group:'internship',selection:'choose',summary:'选择要填写的实习，默认使用已有版本',filters:[],rank:null,required_values:[],min_items:null,max_items:null};
    const manifest={url:session.form_analysis.url,title:'虚构岗位',execution:'external',fields:[{id:'name',label:'名字',required:true},{id:'internship',label:'实习经历',collection:true,required:false,children:[{id:'company',label:'公司',required:true},{id:'description',label:'实习描述',type:'textarea'}]},{id:'proficiency',label:'精通程度',required:true,type:'select',options:['入门','商务会话'],decision_required:true}]};
    await post('/api/preparation/mapping',{session_id:session.id,manifest,interpretation:{mappings:[{website_id:'name',status:'mapped',category:'basic',field_id:'name',members:[]},{website_id:'internship',status:'mapped',category:'employment',field_id:null,entry_ids:employees.map(e=>e.id),recommended_ids:[employees[0].id],requirement:rule,members:[{website_id:'company',field_id:'company'},{website_id:'description',field_id:'description'}]},{website_id:'proficiency',status:'new',category:'additional',field_id:null,members:[],new_field:{label:'精通程度',category:'additional',type:'select'}}]}});
    await page.goto(base+'/?prep-test=1#practice/'+session.id);await page.locator('#prep-preview').waitFor();
    assert(await page.locator('#prep-live-preview').isVisible());assert.equal(await page.locator('#execution-dialog').count(),1);assert((await page.locator('#prep-live-preview').textContent()).includes(employees[0].values.company));assert.equal(await page.locator('[data-choice-entry]').count(),employees.length);assert.equal(await page.locator('[data-experience]:checked').count(),1);
    assert.equal(await page.locator('[data-set-version]').count(),employees.length);assert(await page.locator('[data-expansion-key="automatic"]').evaluate(e=>!e.open));
    assert.equal(await page.locator('#prep-needed [data-missing-key]').count(),1);
    let releaseSettings;const settingsGate=new Promise(resolve=>releaseSettings=resolve);
    await page.route('**/api/preparation/settings',async route=>{await settingsGate;await route.continue();});
    await page.locator('#prep-attachment').selectOption('');
    try{assert(await page.locator('#prep-needed [data-group-mode="session"]').isDisabled());}finally{releaseSettings();}
    await page.waitForFunction(()=>document.querySelector('#preview-save-state').textContent==='选择已保存 · 预览已更新');
    await page.unroute('**/api/preparation/settings');
    await page.locator('#prep-needed [data-missing-value]').selectOption('商务会话');await page.locator('#prep-needed [data-group-mode="session"]').click();
    await page.waitForFunction(()=>!document.querySelector('#prep-needed [data-missing-key]'));
    const after=await read();assert(after.fields.some(f=>f.label==='精通程度'));
    await page.locator('#prep-preview').click();await page.locator('#prep-preview-dialog').waitFor({state:'visible'});
    const text=await page.locator('#prep-preview-content').textContent();assert(text.includes('名字'));assert(text.includes('商务会话'));assert(text.includes(employees[0].values.company));
    assert(await page.locator('#prep-confirm').isEnabled());const setup=await(await fetch(base+'/api/executor-setup')).json();const connected=await fetch(base+'/api/executor/connect',{method:'POST',headers:{'Content-Type':'application/json',Origin:'chrome-extension://'+'a'.repeat(32)},body:JSON.stringify({code:setup.code,url:manifest.url})});assert(connected.ok);await page.waitForFunction(()=>!document.querySelector('#prep-confirm').disabled);await page.locator('#prep-confirm').click();
    await page.waitForFunction(()=>document.querySelector('#execution-current').textContent.includes('等待连接'));
    assert.equal((await read()).sessions.find(x=>x.id===session.id).preparation.execution.filled,0);
  });
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:checks.length,pageErrors:errors.length}));
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
