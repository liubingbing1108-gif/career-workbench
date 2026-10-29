/* No browser or network: mocks exercise extension launch and permissions. */
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
const ticket='fictional_ticket_1234567890';
const settle=async()=>{for(let i=0;i<12;i++)await new Promise(setImmediate);};
function controller(permitted,failScan=false,warmup=0,existing=[],recovery=null){
 const elements=new Map(),opened=[],requests=[],calls=[],timers=[],removed=[],activated=[];let transport;let connectCount=0,permissionRequests=0,scanCount=0,clientScans=0;
 const el=id=>{if(!elements.has(id))elements.set(id,{hidden:true,disabled:false,value:'',textContent:''});return elements.get(id);};
 const chrome={runtime:{id:'a'.repeat(32),onMessage:{addListener(fn){transport=fn;}}},tabs:{query:async ({url})=>typeof url==='string'?existing:[],remove:async id=>removed.push(id),getCurrent:async()=>({id:1}),update:async(id,options)=>activated.push({id,...options}),get:async id=>({id,url:'https://example.com/apply',status:'complete'}),create:async options=>{opened.push(options);return {id:42};},onUpdated:{addListener(){},removeListener(){}}},permissions:{contains:async()=>permitted,request:async()=>{permissionRequests++;return true;}}};
 let busy=!!recovery?.busy,cancelled=false,proofAccepted=false;
 class JobFillClient{constructor(id){this.id=id;}async call(action){calls.push(action);
  if(action==='executionState')return {ok:true,result:{sessionId:'original-core',page:{url:'https://example.com/apply'},busy,cancelled}};
  if(action==='cancel'){cancelled=true;if(!recovery?.stuck)busy=false;return {ok:true,result:{stopping:busy}};}
  clientScans++;if(busy)return {ok:false,error:{code:'BUSY',message:'旧任务执行中'}};
  return {ok:true,result:{sessionId:'original-core',capabilities:{stopProof:1},url:'https://example.com/apply',fields:clientScans<=warmup?[]:[{id:'name',label:'姓名',currentValue:'existing private value'}]}};
 }}
 const fetch=async(url,options)=>{const action=url.split('/').at(-1),body=JSON.parse(options.body);requests.push({action,body});let result={ok:true};
 if(action==='launch-claim')result={url:'https://example.com/apply',code:'fixture-code'};
 if(action==='connect'){connectCount++;result={connection:'fixture-connection',message:'connected'};}
 if(action==='stop-check')result={stop_check:recovery&&!proofAccepted?{job_id:'old-attempt',core_session_id:recovery.wrongCore?'different-core':'original-core'}:null};
 if(action==='stop-proof'){proofAccepted=true;result={accepted:true};}
 if(action==='scan'&&failScan&&++scanCount===1)return {ok:false,json:async()=>({error:'not ready'})};
 if(action==='poll')result={job:null};return {ok:true,json:async()=>result};};
 const context=vm.createContext({URL,URLSearchParams,Number,Error,location:{href:'chrome-extension://'+'a'.repeat(32)+'/workbench.html#launch='+ticket,hash:'#launch='+ticket},document:{querySelector:el},chrome,fetch,JobFillClient,JobFillMaterials:{run:async()=>{throw Error('unconfirmed fill');}},setTimeout:(fn,ms)=>{if(ms===100&&recovery||ms===1000&&clientScans<=warmup)setImmediate(fn);else timers.push(fn);return 1;},clearTimeout(){},setInterval(){}});
 vm.runInContext(fs.readFileSync(__dirname+'/workbench.js','utf8'),context);
 return {elements,opened,requests,calls,el,removed,activated,get transport(){return transport;},get connectCount(){return connectCount;},get permissionRequests(){return permissionRequests;}};
}
test('granted permission launches exact official URL and connects without a toolbar click',async()=>{const c=controller(true);await settle();assert.equal(c.opened.length,1);assert.equal(c.opened[0].url,'https://example.com/apply');assert.equal(c.opened[0].active,false);assert.equal(c.activated.length,0);assert.equal(c.connectCount,1);assert.equal(c.permissionRequests,0);assert(c.requests.some(r=>r.action==='launch-report'&&r.body.status==='ready'));assert(!c.calls.includes('fill'));assert(!JSON.stringify(c.requests).includes('existing private value'));});
test('first permission is requested only after explicit enable click',async()=>{const c=controller(false);await settle();assert.equal(c.opened.length,0);assert.equal(c.permissionRequests,0);assert.equal(c.el('#permission').hidden,false);await c.el('#enable-auto').onclick();await settle();assert.equal(c.permissionRequests,1);assert.equal(c.opened.length,1);assert.equal(c.connectCount,1);});
test('retry after scan failure reuses single-use connection',async()=>{const c=controller(true,true);await settle();assert.equal(c.connectCount,1);assert.equal(c.el('#retry-scan').hidden,false);await c.el('#retry-scan').onclick();await settle();assert.equal(c.connectCount,1);assert.equal(c.el('#retry-scan').hidden,true);});
test('SPA warmup automatically waits for visible fields without sending existing answers',async()=>{const c=controller(true,false,2);await settle();assert.equal(c.calls.filter(a=>a==='scan').length,3);assert.equal(c.connectCount,1);assert.equal(c.el('#retry-scan').hidden,true);assert(!JSON.stringify(c.requests).includes('existing private value'));});

test('existing exact official page is reused without foreground activation or duplicate tabs',async()=>{const c=controller(true,false,0,[{id:87,url:'https://example.com/apply'}]);await settle();assert.equal(c.opened.length,0);assert.equal(c.activated.length,0);assert.equal(c.connectCount,1);});
test('transport cleanup only closes own current-ticket top-level local relay',async()=>{const c=controller(true);await settle();const message={type:'jobfill:transport',ticket};const valid={id:'a'.repeat(32),frameId:0,tab:{id:9},url:'http://127.0.0.1:8768/?launch='+ticket};for(const sender of [{...valid,url:'https://evil.example/?launch='+ticket},{...valid,frameId:1},{...valid,id:'b'.repeat(32)},{...valid,url:'http://127.0.0.1:8768/?launch=another'}])c.transport(message,sender,()=>{});assert.equal(c.removed.length,0);let response;c.transport(message,valid,r=>response=r);await settle();assert.deepEqual(c.removed,[9]);assert.equal(response.ok,true);});

test('reconnect cancels only the paired original core and proves stop before rescanning',async()=>{
 for(const busy of [false,true]){
  const c=controller(true,false,0,[],{busy});await settle();
  assert.equal(c.connectCount,1);assert.equal(c.calls.filter(a=>a==='cancel').length,1);
  const proof=c.requests.find(r=>r.action==='stop-proof');assert.equal(proof.body.job_id,'old-attempt');
  assert.equal(proof.body.proof.busy,false);assert.equal(proof.body.proof.cancelled,true);
  assert(c.requests.findIndex(r=>r.action==='stop-proof')<c.requests.findIndex(r=>r.action==='scan'));
  assert(c.requests.some(r=>r.action==='launch-report'&&r.body.status==='ready'));
  assert.equal(c.requests.find(r=>r.action==='connect').body.core_session_id,'original-core');
 }
});
test('a different original core does not get cancelled or claim recovery',async()=>{
 const c=controller(true,false,0,[],{busy:true,wrongCore:true});await settle();
 assert(!c.calls.includes('cancel'));assert(!c.requests.some(r=>r.action==='stop-proof'||r.action==='scan'));
 assert(c.el('#status').textContent.includes('原执行页面'));
});
test('a cancellation request without settlement remains blocked',async()=>{
 const c=controller(true,false,0,[],{busy:true,stuck:true});for(let i=0;i<4;i++)await settle();
 assert(c.calls.includes('cancel'));assert(!c.requests.some(r=>r.action==='stop-proof'||r.action==='scan'));
 assert(c.el('#status').textContent.includes('仍在停止中'));
});
