let tabId=Number.parseInt(new URL(location.href).searchParams.get('tabId'),10);
let client=Number.isInteger(tabId)?new JobFillClient(tabId):null;
let launchTicket=new URLSearchParams(location.hash.slice(1)).get('launch');
const statusBox=document.querySelector('#status');
let launchDetails,retryTimer;
let connection,connectedUrl,url,stopped=false,running=false,polling=false,counts={filled:0,verified:0};
const display=text=>statusBox.textContent=text;
async function request(action,data={}){
 const response=await fetch('http://127.0.0.1:8768/api/executor/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({connection,url,...data})});
 const result=await response.json();if(!response.ok)throw Error(result.error||'连接失败');return result;
}
async function target(){const tab=await chrome.tabs.get(tabId);if(!tab.url?.startsWith('https:'))throw Error('请先打开招聘官网，再从该页开启扩展');url=tab.url;document.querySelector('#target').textContent='目标官网：'+url;}
if(!launchTicket)target().catch(e=>display(e.message));
async function connect(){
 try{
  await target();let scan;
  for(let attempt=0;attempt<30;attempt++){
   scan=await client.call('scan',{});if(!scan.ok)throw Error(scan.error.message);
   if(scan.result.fields?.some(field=>!field.disabled))break;
   if(attempt<29)await new Promise(resolve=>setTimeout(resolve,1000));
  }
  if(!scan.result.fields?.some(field=>!field.disabled))throw Error('请在官网完成登录或打开申请表，系统会自动继续读取');
  const choices=new Map();let readFormat=false;
  for(const field of scan.result.fields){
   if(field.disabled)continue;
   if(field.context?.driver==='phoenix-calendar'&&field.kind==='unsupported'){
    const format=await client.call('readDateFormat',{snapshotId:scan.result.snapshotId,fieldId:field.fieldId});
    if(!format.ok)throw Error(field.label+'：'+format.error.message);
    readFormat=true;
   }else if(field.kind==='select'&&field.options?.state==='requires-opening'){
    const options=await client.call('readOptions',{snapshotId:scan.result.snapshotId,fieldId:field.fieldId});
    if(options.ok)choices.set(field.fieldId,options.result);
   }
  }
  if(readFormat){scan=await client.call('scan',{});if(!scan.ok)throw Error(scan.error.message);}
  for(const field of scan.result.fields)if(choices.has(field.fieldId))field.options=choices.get(field.fieldId);
  const result=connection&&connectedUrl===url?{connection,message:'继续读取当前官网'}:await request('connect',{code:launchDetails?.code||document.querySelector('#code').value.trim()});connection=result.connection;connectedUrl=url;
  document.querySelector('#code').value='';document.querySelector('#connect').disabled=true;stopped=false;display(result.message);
  // Send only field metadata; existing website answers are never imported as profile facts.
  const snapshot={...scan.result,fields:scan.result.fields.map(({currentValue,...field})=>field)};
  const prepared=await request('scan',{snapshot});display(prepared.message||result.message);document.querySelector('#retry-scan').hidden=true;if(!polling){polling=true;poll();}
  if(launchTicket)await request('launch-report',{ticket:launchTicket,status:'ready'}).catch(()=>{});
  return true;
 }catch(e){display(e.message);if(launchTicket){document.querySelector('#retry-scan').hidden=false;await request('launch-report',{ticket:launchTicket,status:'needs_user'}).catch(()=>{});scheduleRetry();}return false;}
}
document.querySelector('#connect').onclick=connect;
document.querySelector('#retry-scan').onclick=connect;
function scheduleRetry(){
 clearTimeout(retryTimer);
 retryTimer=setTimeout(async()=>{if(!running&&!stopped)await connect();},4000);
}
async function findTarget(details){
 const all=await chrome.tabs.query({url:details.url});
 let tab=all.find(t=>t.id===tabId)||all.find(t=>t.url===details.url);
 if(!tab){
  const role=new URL(details.url),job=role.searchParams.get('jobAdId');
  if(job){const forms=await chrome.tabs.query({url:role.origin+'/form*'});tab=forms.find(t=>{const u=new URL(t.url);return u.searchParams.get('jobAdId')===job;});}
 }
 return tab||await chrome.tabs.create({url:details.url,active:false});
}
async function openTarget(){
 document.querySelector('#permission').hidden=true;
 await request('launch-report',{ticket:launchTicket,status:'connecting'});
 const tab=await findTarget(launchDetails);tabId=tab.id;client=new JobFillClient(tabId);
 if(launchDetails.mode==='focus'){
  await chrome.tabs.update(tabId,{active:true});if(chrome.windows)await chrome.windows.update(tab.windowId,{focused:true});
 }
 await new Promise((resolve,reject)=>{
  const timeout=setTimeout(()=>{chrome.tabs.onUpdated.removeListener(update);reject(Error('官网加载超时，请检查页面后继续'));},45000);
  function update(id,change){if(id===tabId&&change.status==='complete'){clearTimeout(timeout);chrome.tabs.onUpdated.removeListener(update);resolve();}}
  chrome.tabs.onUpdated.addListener(update);
  chrome.tabs.get(tabId).then(t=>{if(t.status==='complete')update(tabId,{status:'complete'});});
 });
 await connect();
}
async function cleanupTransport(ticket){
 // Only short-lived launch pages generated by this application are removed.
 const tabs=await chrome.tabs.query({url:['http://127.0.0.1:8768/*','http://localhost:8768/*']});
 for(const tab of tabs){if(!tab.url)continue;const u=new URL(tab.url);if(u.searchParams.get('launch')===ticket)await chrome.tabs.remove(tab.id);}
}
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
 if(message?.type!=='jobfill:transport'||message.ticket!==launchTicket||!launchDetails||sender.id!==chrome.runtime.id||sender.frameId!==0||!sender.tab?.id)return;
 let source;try{source=new URL(sender.url);}catch{return;}
 if(!['http://127.0.0.1:8768','http://localhost:8768'].includes(source.origin)||source.searchParams.get('launch')!==launchTicket)return;
 chrome.tabs.remove(sender.tab.id).then(()=>respond({ok:true})).catch(()=>respond({ok:false}));return true;
});
async function acceptLaunch(ticket){
 const details=await request('launch-claim',{ticket});
 await cleanupTransport(ticket);
 if(details.mode==='focus'&&connection){
  const tab=await findTarget(details);await chrome.tabs.update(tab.id,{active:true});if(chrome.windows)await chrome.windows.update(tab.windowId,{focused:true});await request('launch-report',{ticket,status:'ready'}).catch(()=>{});return;
 }
 if(running)throw Error('已有填写正在进行，请先暂停');
 clearTimeout(retryTimer);launchTicket=ticket;launchDetails=details;connection=null;connectedUrl=null;stopped=false;
 document.querySelector('#target').textContent='目标官网：'+details.url;
 if(await chrome.permissions.contains({origins:['https://*/*']}))return openTarget();
 document.querySelector('#permission').hidden=false;display('完成一次授权后，以后由工作台自动启动。');
 const controller=await chrome.tabs.getCurrent();if(controller)await chrome.tabs.update(controller.id,{active:true});
 await request('launch-report',{ticket:launchTicket,status:'permission'});
}
if(launchTicket){
 document.querySelector('#legacy-connect').hidden=true;
 acceptLaunch(launchTicket).catch(e=>{display(e.message);if(launchDetails)scheduleRetry();});
 document.querySelector('#enable-auto').onclick=async()=>{
  const allowed=await chrome.permissions.request({origins:['https://*/*']});
  if(!allowed){display('未授权，自动填写尚未启用。');return;}
  try{await openTarget();}catch(e){display(e.message);scheduleRetry();}
 };
}
document.querySelector('#stop').onclick=async()=>{stopped=true;if(client)await client.call('cancel',{});display('已请求停止；已填内容保留在官网。');};
async function poll(){
 if(stopped||running){polling=false;return;}
 try{
  const next=await request('launch-next');
  if(next.ticket){await acceptLaunch(next.ticket);if(!stopped)setTimeout(poll,1000);return;}
  const tab=await chrome.tabs.get(tabId);if(tab.url!==url)throw Error('官网已切换，连接已停止');
  const result=await request('poll');
  if(result.stop){stopped=true;display(result.message);await client.call('cancel',{});}
  if(result.job){
   running=true;counts={filled:0,verified:0};
   const report=async progress=>{counts=progress;display(progress.message);const response=await request('report',{job_id:result.job.id,...progress});if(response.stop)stopped=true;};
   try{await JobFillMaterials.run(client,result.job.materials,report,()=>stopped);}
   catch(e){await report({status:stopped?'paused':'failed',filled:counts.filled,verified:counts.verified,issues:[e.message],message:'填写已停止：'+e.message});}
   finally{running=false;}
  }
  if(!stopped)setTimeout(poll,1000);else{polling=false;document.querySelector('#connect').disabled=false;}
 }catch(e){polling=false;display('连接已停止：'+e.message);document.querySelector('#connect').disabled=false;document.querySelector('#retry-scan').hidden=false;}
}

setInterval(async()=>{
 if(!connection||polling||running)return;
 try{const next=await request('launch-next');if(next.ticket)await acceptLaunch(next.ticket);}catch{}
},2000);
