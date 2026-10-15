/* Fictional local UI only: no recruiting site, model service, or real resume. */
const {chromium}=require('playwright'),{spawn}=require('node:child_process'),assert=require('node:assert/strict'),path=require('node:path');
const source=`from server import make_server
from test_product_fixture import make_fixture
from test_recognizer import sample
import threading,sys
release=threading.Event()
threading.Thread(target=lambda:(sys.stdin.readline(),release.set()),daemon=True).start()
f,app,m=make_fixture()
class SlowRecognizer:
 name='离线解析测试'
 def status(self):return {'engine':self.name,'available':True}
 def extract(self,fields,blocks):
  release.wait(30)
  return sample()[1],{}
f.lab.recognizer=SlowRecognizer()
def optional(state):
 for s in state['sessions']:
  s['website']['fields'].append(dict(id='portfolio',label='作品说明',type='textarea',required=False))
  s['website']['mappings'].append(dict(website_id='portfolio',category='additional',status='new',field_id=None,members=[],new_field=dict(label='作品说明',category='additional',type='multiline')))
f.lab.mutate(optional)
server=make_server(f.lab,management_app=app,management_handler=m.handler(app),browser_opener=lambda url:None)
print(server.server_port,flush=True)
server.serve_forever()
`;
(async()=>{
 const server=spawn(process.env.PYTHON||'python3',['-u','-c',source],{cwd:__dirname,stdio:['pipe','pipe','pipe']});let browser;
 try{
  const port=await new Promise((resolve,reject)=>{server.stdout.once('data',d=>resolve(Number(d.toString().trim())));server.once('exit',()=>reject(Error('fixture stopped')));});
  const base='http://127.0.0.1:'+port;browser=await chromium.launch({headless:true});const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const read=async()=>await(await fetch(base+'/api/state')).json();
  const post=async(url,data,origin)=>{const r=await fetch(base+url,{method:'POST',headers:{'Content-Type':'application/json',...(origin?{Origin:origin}:{})},body:JSON.stringify(data)});assert(r.ok,await r.clone().text());return r.json();};
  await page.goto(base+'/#profile/basic');await page.locator('#resume-file').setInputFiles({name:'fiction.txt',mimeType:'text/plain',buffer:Buffer.from('陈示例 example@example.invalid\n样例大学 数学 本科 2020/09-2024/06\n样例公司 研究部门 分析实习 2023/07-至今\n参与整理样例项目资料。')});
  await page.locator('#import-dialog').waitFor();await page.locator('#import-task-preview progress').waitFor({state:'visible',timeout:10000}).catch(async e=>{console.log('Import diagnostic',await page.locator('#import-task-preview').textContent());throw e;});await page.locator('#import-task-preview summary').click();await page.waitForFunction(()=>document.querySelector('.resume-text-preview').textContent.includes('陈示例'));assert((await page.locator('.resume-text-preview').textContent()).includes('陈示例'));if(process.env.UI_EVIDENCE){require('node:fs').mkdirSync(process.env.UI_EVIDENCE,{recursive:true});await page.screenshot({path:path.join(process.env.UI_EVIDENCE,'resume-parsing.png')});}
  server.stdin.write('release\n');await page.reload();await page.locator('.library-import-info>summary').click();await page.locator('#import-tasks').waitFor();await page.waitForFunction(()=>document.querySelector('#import-tasks').textContent.includes('完成'));
  assert(!(await page.locator('#completed-imports').evaluate(e=>e.open)));await page.locator('#completed-imports summary').click();await page.locator('[data-import-preview]').first().click();await page.locator('[data-candidate]').first().waitFor();assert((await read()).entries.every(e=>e.values.name!=='陈示例'));assert.equal(await page.locator('[data-import-set]').count(),2);assert.equal(await page.locator('.set-field input[type=checkbox]').count(),0);await page.locator('#import-category').selectOption('employment');assert.equal(await page.locator('[data-import-unit]:visible').count(),1);await page.locator('#import-category').selectOption('');if(process.env.UI_EVIDENCE){await page.screenshot({path:path.join(process.env.UI_EVIDENCE,'resume-sets.png')});}
  console.log('PASS parsing progress, extracted-text preview, background completion across reload and explicit import');
  await page.getByRole('button',{name:'关闭导入预览',exact:true}).click();
  const before=await read(),sid=before.sessions[0].id;
  await page.goto(base+'/#practice/'+sid);await page.locator('#prep-live-preview').waitFor();assert(await page.locator('#prep-optional').isVisible());assert((await page.locator('#prep-optional').textContent()).includes('作品说明'));
  await page.locator('#prep-optional textarea').fill('虚构作品草稿，尚未确认');await page.waitForFunction(()=>document.querySelector('#preview-save-state').textContent.includes('草稿已自动保存'),null,{timeout:5000}).catch(async error=>{console.log(JSON.stringify({label:await page.locator('#preview-save-state').textContent(),errors,local:await page.evaluate(()=>localStorage.getItem('career-answer-drafts-v1')),drafts:(await read()).sessions.map(s=>s.preparation?.drafts)}));throw error;});
  if(process.env.UI_EVIDENCE){await page.locator('#prep-optional').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(process.env.UI_EVIDENCE,'saved-draft.png')});}await page.reload();await page.locator('#prep-optional textarea').waitFor();assert.equal(await page.locator('#prep-optional textarea').inputValue(),'虚构作品草稿，尚未确认');assert.deepEqual((await read()).entries,before.entries);
  await page.goto(base+'/#practice/'+before.sessions[1].id);await page.waitForFunction(id=>document.querySelector('#form-analysis').dataset.session===id,before.sessions[1].id);await page.locator('#prep-optional textarea').waitFor();assert.equal(await page.locator('#prep-optional textarea').inputValue(),'');
  await page.goto(base+'/#practice/'+sid);await page.waitForFunction(id=>document.querySelector('#form-analysis').dataset.session===id,sid);await page.locator('#prep-optional textarea').waitFor();await page.locator('#prep-optional [data-group-mode="session"]').click();await page.waitForFunction(()=>!document.querySelector('#prep-optional textarea'));
  assert((await page.locator('#prep-live-preview').textContent()).includes('虚构作品草稿，尚未确认'));assert.deepEqual((await read()).entries,before.entries);
  await page.getByRole('button',{name:'投递管理',exact:true}).click();const frame=page.frameLocator('#management-frame');await frame.getByRole('button',{name:'继续投递',exact:true}).first().waitFor();assert((await frame.locator('#table-area').textContent()).includes('草稿待继续'));
  await frame.getByRole('button',{name:'继续投递',exact:true}).first().click();await page.locator('#prep-live-preview').waitFor();assert.equal((await read()).sessions.length,before.sessions.length);
  console.log('PASS edit autosave across reload, job isolation, optional material included and continue entry');
  const origin='chrome-extension://'+'a'.repeat(32),setup=await(await fetch(base+'/api/executor-setup?session='+sid)).json();
  const connected=await post('/api/executor/connect',{code:setup.code,url:'https://example.com/apply'},origin);
  await post('/api/executor/draft',{connection:connected.connection,url:'https://example.com/apply',initial:true,fields:[{fieldId:'name',label:'姓名',kind:'text',currentValue:'虚构手填姓名',sectionId:'basic',section:'个人信息',record:-1}]},origin);
  await page.goto(base+'/#practice/'+sid);await page.locator('#restore-official-draft').waitFor();await page.locator('#restore-official-draft').click();await page.locator('#prep-preview-dialog').waitFor({state:'visible'});assert((await page.locator('#prep-preview-content').textContent()).includes('虚构手填姓名'));assert(await page.locator('#prep-confirm').isEnabled());
  await page.locator('#prep-confirm').click();await page.waitForFunction(()=>document.querySelector('#execution-current').textContent.includes('等待连接'));
  const execution=(await read()).sessions.find(s=>s.id===sid).preparation.execution;assert.equal(execution.filled,0);assert.equal(execution.saved,false);assert.equal(execution.confirmed_materials.source,'official_draft');assert.equal(execution.confirmed_materials.rows[0].value,'虚构手填姓名');
  console.log('PASS authenticated official-input backup, explicit restore preview and queued-only recovery');
  assert.deepEqual(errors,[]);console.log('PASS 3 recovery UI checks; 0 page errors');
 }finally{if(browser)await browser.close();server.kill('SIGTERM');}
})().catch(e=>{console.error(e);process.exitCode=1;});
