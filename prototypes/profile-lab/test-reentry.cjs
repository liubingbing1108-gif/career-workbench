const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const source=fs.readFileSync(__dirname+'/web/product.js','utf8');
const defer=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return {promise,resolve,reject};};
const tick=()=>new Promise(r=>setImmediate(r));
function harness(){
 const nodes=new Map(),listeners={},requests=[],opened=[],launches=[];
 const node=s=>{if(!nodes.has(s))nodes.set(s,{hidden:false,innerHTML:'',textContent:'',value:'',append(){},contentWindow:{postMessage(){}},close(){},parentElement:{}});return nodes.get(s);};
 const c={console,Map,URLSearchParams,AbortController,DOMException,setTimeout,clearTimeout,setInterval(){},location:{origin:'http://test',hash:'',search:''},history:{replaceState(){}},document:{createElement:()=>({}),body:{classList:{add(){}}}},state:{sessions:[]},currentView:'management',refreshRevision:0,sessionId:null,preparationState:{},answerDrafts:new Map(),$:node,$$:()=>[],escapeHtml:String,safe:f=>f,showExecutionDialog(){},updatePreparationProgress(){},refresh:async()=>{},
 window:{addEventListener:(n,f)=>{(listeners[n]??=[]).push(f);},scrollTo(){}},
 showView(view){c.currentView=view;(listeners['workbench:view-change']||[]).forEach(f=>f({detail:view}));},
 fetch:async(url,options)=>{if(url.endsWith('/bootstrap'))return {ok:true,json:async()=>({token:'test'})};const d=defer();requests.push({url,options,...d});return d.promise;},
 api:async(url,body)=>{if(url==='/api/preparation/open'){opened.push(body.job_id);const id=body.job_id;c.state.sessions=[{id,name:id,form_analysis:{}}];return {id,manual_reason:'fixture: do not open browser'};}if(url==='/api/browser-launch'){launches.push(body);return {};}return {};}};
 vm.createContext(c);vm.runInContext(source,c);
 return {c,node,requests,opened,launches,respond:(i,x)=>requests[i].resolve({ok:true,json:async()=>x})};
}
test('return and restart while old lookup pending opens immediately; old finally cannot unlock newer run',async()=>{
 const h=harness();const first=h.c.prepareManagedJob({id:'a',company:'公司甲',role:'产品经理'});await tick();
 h.c.showView('management');assert(h.requests[0].options.signal.aborted);
 const second=h.c.prepareManagedJob({id:'a',company:'公司甲',role:'产品经理'});await tick();
 assert.equal(h.c.currentView,'practice');assert.equal(h.requests.length,2);
 h.respond(0,{status:'ready'});await first;assert.equal(h.opened.length,0);
 assert.equal(vm.runInContext('preparingJob.jobId',h.c),'a');
 h.respond(1,{status:'ready'});await second;assert.deepEqual(h.opened,['a']);
});
test('late error from previous job neither overwrites the current screen nor opens its website',async()=>{
 const h=harness();const a=h.c.prepareManagedJob({id:'a',company:'甲',role:'岗位A'});await tick();h.c.showView('profile');
 const b=h.c.prepareManagedJob({id:'b',company:'乙',role:'岗位B'});await tick();h.requests[0].reject(Error('old failure'));await a;
 assert.equal(h.node('#flow-identity').textContent,'乙 · 岗位B');assert(!h.node('#target-waiting').innerHTML.includes('old failure'));
 h.respond(1,{status:'ready'});await b;assert.deepEqual(h.opened,['b']);
});
test('return while open request pending never navigates back or launches',async()=>{
 const h=harness(),pending=defer();h.c.api=async()=>pending.promise;
 const a=h.c.prepareManagedJob({id:'a',company:'甲',role:'A'});await tick();h.respond(0,{status:'ready'});await tick();h.c.showView('management');pending.resolve({id:'a'});await a;
 assert.equal(h.c.currentView,'management');assert.equal(h.c.sessionId,null);
});
test('a normal unavailable result stays retryable without a global lock',async()=>{
 const h=harness();const a=h.c.prepareManagedJob({id:'a',company:'甲',role:'A'});await tick();h.respond(0,{status:'unavailable',message:'搜索暂时繁忙'});await a;
 assert(h.node('#target-waiting').innerHTML.includes('搜索暂时繁忙'));assert(!h.node('#target-waiting').innerHTML.includes('flow-spinner'));assert.equal(vm.runInContext('preparingJob',h.c),null);
 const b=h.node('#resolve-retry').onclick();await tick();assert.equal(h.requests.length,2);h.respond(1,{status:'ready'});await b;
});

test('a scanned form that is still matching shows progress, never an empty page',()=>{
 const h=harness();h.c.preparationState={scan_status:'matching'};
 h.c.updateTargetPanel({id:'b',target:{url:'https://example.com/role'},form_analysis:{sections:[]}});
 assert.equal(h.node('#target-waiting').hidden,false);assert(h.node('#target-waiting').innerHTML.includes('正在匹配你的资料'));
});
