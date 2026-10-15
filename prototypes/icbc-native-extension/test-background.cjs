const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const settle=async()=>{for(let n=0;n<15;n++)await new Promise(setImmediate);};
function setup(permitted=true){let listener;const launches=[],removed=[];const context=vm.createContext({URL,Set,Promise,importScripts(){},JobFillService:class{async launch(ticket){launches.push(ticket);return {ok:true};}},chrome:{runtime:{onMessage:{addListener(fn){listener=fn;}}},permissions:{contains:async()=>permitted},tabs:{remove:async id=>removed.push(id)}}});vm.runInContext(fs.readFileSync(__dirname+'/background.js','utf8'),context);return {launches,removed,send(msg,sender={url:'http://127.0.0.1:8768/',frameId:0,tab:{id:9}}){return new Promise(resolve=>{if(!listener(msg,sender,resolve))resolve(null);});}};}
const ticket='fictional_ticket_123456789';
test('launch happens in background without creating a controller tab; replay is deduplicated',async()=>{const f=setup();await f.send({type:'jobfill:launch',ticket});await f.send({type:'jobfill:launch',ticket});assert.deepEqual(f.launches,[ticket]);assert.equal(f.removed.length,0);});
test('only dedicated relay is removed; normal product page never closes',async()=>{const f=setup();await f.send({type:'jobfill:launch',ticket},{url:'http://127.0.0.1:8768/launch-relay?launch='+ticket,frameId:0,tab:{id:9}});assert.deepEqual(f.removed,[9]);});
test('external origins and subframes cannot launch; permissions remain required',async()=>{for(const sender of [{url:'https://evil.example',frameId:0},{url:'http://127.0.0.1:8768',frameId:1}]){const f=setup();await f.send({type:'jobfill:launch',ticket},sender);assert.equal(f.launches.length,0);}const f=setup(false);assert.equal((await f.send({type:'jobfill:launch',ticket})).ok,false);assert.equal(f.launches.length,0);});
test('concurrent different tickets are serialized and keep distinct targets',async()=>{const f=setup();await Promise.all([f.send({type:'jobfill:launch',ticket}),f.send({type:'jobfill:launch',ticket:ticket+'b'})]);assert.deepEqual(f.launches,[ticket,ticket+'b']);});
function service(){const tabs=[{id:42,url:'https://acme.zhiye.com/form?jobAdId=one&userId=private',windowId:3,status:'complete'}],created=[],activated=[],requests=[];let timer;const ctx=vm.createContext({URL,Map,Error,Promise,setTimeout:fn=>(timer=fn,1),clearTimeout(){},JobFillClient:class{constructor(id){this.id=id;}},chrome:{tabs:{query:async()=>tabs,create:async options=>{created.push(options);return {id:80,...options};},update:async(id,options)=>activated.push([id,options])},windows:{update:async()=>{}}},fetch:async(url,options)=>{const body=JSON.parse(options.body);requests.push(body);return {ok:true,json:async()=>({session_id:'s',url:'https://acme.zhiye.com/campus/detail?jobAdId=one',code:'code',mode:body.ticket==='focus'?'focus':'prepare'})};}});vm.runInContext(fs.readFileSync(__dirname+'/service-controller.js','utf8'),ctx);return {controller:new ctx.JobFillService(),tabs,created,activated};}
test('existing same-job form is reused even if launch target is public detail',async()=>{const f=service();await f.controller.launch(ticket);assert.equal(f.created.length,0);assert.equal(f.controller.tabId,42);assert.equal(f.activated.length,0);});
test('focus reuses the same official page and only explicit focus activates it',async()=>{const f=service();await f.controller.launch('focus');assert.equal(f.created.length,0);assert.equal(f.activated[0][0],42);assert.equal(f.controller.details,undefined,'handoff must not rescan, rematch or poll materials');});
test('a new job gets one background official page and no auxiliary page',async()=>{const f=service();f.tabs.length=0;await f.controller.launch(ticket);assert.equal(f.created.length,1);assert.equal(f.created[0].active,false);});

test('read-only connection waits past search-only shell and never requests matching or writes',async()=>{
 let connects=0,fields=[{label:'搜索职位关键词',disabled:true}];
 const ctx=vm.createContext({URL,chrome:{tabs:{get:async()=>({status:'complete',url:'https://fixture.example/apply'})}},setTimeout(){},clearTimeout(){}});
 vm.runInContext(fs.readFileSync(__dirname+'/service-controller.js','utf8'),ctx);
 const c=new ctx.JobFillService();Object.assign(c,{details:{url:'https://fixture.example/apply',mode:'verify',code:'fictional'},tabId:42,client:{async call(method){assert.equal(method,'scan');return {ok:true,result:{fields}};}},request:async action=>{assert(['connect','launch-report'].includes(action));if(action==='connect')connects++;return {connection:'read-only'};}});
 assert.equal(await c.connect(),false);assert.equal(connects,0);
 fields=[{label:'搜索职位关键词',disabled:false},{label:'验证码',disabled:false}];
 assert.equal(await c.connect(),false);assert.equal(connects,0);
 fields=[{label:'姓名',disabled:true,currentValue:'虚构姓名'}];
 assert.equal(await c.connect(),true);assert.equal(connects,1);assert.equal(c.prepared,true);
});

test('official autosave sends only changed supported values and marks new documents without losing prior backup',async()=>{
 const c=service().controller,requests=[];let documentKey='first';
 Object.assign(c,{details:{mode:'prepare'},url:'https://example.com/apply',client:{documentKey:async()=>({url:c.url,key:documentKey})},request:async(action,data)=>{requests.push({action,data});return {};}});
 const snapshot={page:{url:c.url},sections:[{sectionId:'basic',label:'个人信息'}],fields:[
  {fieldId:'name',label:'姓名',kind:'text',currentValue:'虚构姓名',sectionId:'basic'},
  {fieldId:'school',label:'学校',kind:'autocomplete',currentValue:'虚构大学',sectionId:'basic'},
  {fieldId:'secret',label:'密码',kind:'text',currentValue:'never-store',sectionId:'basic'},
  {fieldId:'consent',label:'同意协议',kind:'checkbox',currentValue:true,sectionId:'basic'}]};
 await c.captureDraft(snapshot);assert.equal(requests.length,1);assert.equal(requests[0].data.initial,true);assert.equal(requests[0].data.fields.length,2);
 await c.captureDraft(snapshot);assert.equal(requests.length,1);
 snapshot.fields[0].currentValue='改过的虚构姓名';await c.captureDraft(snapshot);assert.equal(requests[1].data.initial,false);
 documentKey='second';snapshot.fields[0].currentValue='';await c.captureDraft(snapshot);assert.equal(requests[2].data.initial,true);
 c.details.mode='verify';await c.captureDraft(snapshot);assert.equal(requests.length,3);
});

test('prepare exposes every empty optional section and sends their schema without altering answers',async()=>{
 const methods=[],sections=[{sectionId:'education',label:'教育经历',count:2,canAdd:true},{sectionId:'awards',label:'获奖',count:0,canAdd:true},{sectionId:'language',label:'语言能力',count:0,canAdd:true}];
 const fields=[{fieldId:'name',label:'姓名',kind:'text',currentValue:'保留的姓名',sectionId:'basic'}];
 const ctx=vm.createContext({URL,crypto:require('node:crypto').webcrypto,chrome:{tabs:{get:async()=>({status:'complete',url:'https://fixture.example/apply'})}}});
 vm.runInContext(fs.readFileSync(__dirname+'/service-controller.js','utf8'),ctx);
 const c=new ctx.JobFillService();let sent;
 Object.assign(c,{details:{url:'https://fixture.example/apply',mode:'prepare',code:'fixture'},captureDraft:async snapshot=>assert.equal(snapshot.fields[0].currentValue,'保留的姓名'),client:{async call(method,params){
  methods.push(method);
  if(method==='scan')return {ok:true,result:{snapshotId:'current',fields:structuredClone(fields),sections:structuredClone(sections)}};
  if(method==='ensureRecords'){const s=sections.find(s=>s.sectionId===params.sections[0].sectionId);assert.equal(s.count,0);s.count=1;fields.push({fieldId:s.sectionId+'-name',label:s.label+'名称',kind:'text',currentValue:'',sectionId:s.sectionId});return {ok:true};}
  assert.equal(method,'status');return {ok:true,result:{status:'complete'}};
 }},request:async(action,data)=>{if(action==='scan')sent=data.snapshot;else assert(['connect','launch-report'].includes(action));return {connection:'fixture'};}});
 await c.connect();assert.equal(methods.filter(m=>m==='ensureRecords').length,2);
 assert.deepEqual(sent.fields.map(f=>f.label),['姓名','获奖名称','语言能力名称']);assert(sent.fields.every(f=>!('currentValue' in f)));assert.equal(fields[0].currentValue,'保留的姓名');
});

test('progress query uses separate background tab, reports only observations, preserves fill connection',async()=>{
 const created=[],removed=[],requests=[];
 const ctx=vm.createContext({URL,Promise,chrome:{tabs:{create:async x=>(created.push(x),{id:99,windowId:1}),remove:async id=>removed.push(id)},windows:{}},JobFillClient:class{constructor(id){assert.equal(id,99);}async queryProgress(details){assert.equal(details.mode,'progress');return {status:'records',url:details.url,records:[{role:'产品经理',stage:'面试中'}]};}}});
 vm.runInContext(fs.readFileSync(__dirname+'/service-controller.js','utf8'),ctx);const c=new ctx.JobFillService();
 c.connection='existing';c.tabId=42;c.client={untouched:true};
 c.request=async(action,data)=>{requests.push(action);if(action==='launch-claim')return {mode:'progress',url:'https://example.com/apply',role:'产品经理'};assert.equal(action,'progress-report');assert.equal(data.observation.records[0].stage,'面试中');return {status:'complete'};};
 assert.equal((await c.launch(ticket)).ok,true);assert.equal(c.connection,'existing');assert.equal(c.tabId,42);assert(c.client.untouched);assert.equal(created[0].active,false);assert.deepEqual(removed,[99]);assert.deepEqual(requests,['launch-claim','progress-report']);
});
