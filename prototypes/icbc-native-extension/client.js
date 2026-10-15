/* Extension-side entry point: a future trusted controller can reuse this class. */
function jobFillNativeSetter(marker,value,blur,url){
 if(location.href!==url)throw Error('网页已切换');
 const roots=[document];for(let i=0;i<roots.length;i++)for(const e of roots[i].querySelectorAll('*'))if(e.shadowRoot)roots.push(e.shadowRoot);
 const matches=roots.flatMap(r=>[...r.querySelectorAll('[data-jobfill-native-field]')]).filter(e=>e.getAttribute('data-jobfill-native-field')===marker);
 if(matches.length!==1)throw Error('文本输入目标不唯一');const e=matches[0];
 if(e.disabled||e.readOnly||!(e instanceof HTMLTextAreaElement||e instanceof HTMLInputElement&&['text','email','tel','number','search'].includes(e.type)))throw Error('该控件不允许文本输入');
 e.focus();let nativeEdit=false;
 const setter=Object.getOwnPropertyDescriptor(e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set;
 // Force one actual editing transition when replaying an uncommitted equal value.
 if(e.value===value)setter.call(e,'');
 if(typeof document.execCommand==='function'&&typeof e.select==='function'&&(e instanceof HTMLTextAreaElement||['text','search','tel'].includes(e.type))){e.select();nativeEdit=document.execCommand('insertText',false,value)&&e.value===value;}
 if(!nativeEdit){Object.getOwnPropertyDescriptor(e instanceof HTMLTextAreaElement?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,value);e.dispatchEvent(new InputEvent('input',{bubbles:true,composed:true,inputType:'insertText',data:value}));}
 e.dispatchEvent(new Event('change',{bubbles:true,composed:true}));e.dispatchEvent(new KeyboardEvent('keyup',{key:'Unidentified',bubbles:true}));if(blur)e.blur();
 return {value:e.value,method:nativeEdit?'native-edit':'native-setter'};
}
globalThis.JobFillClient=class {
 async documentKey(){
  const result=await chrome.scripting.executeScript({target:{tabId:this.tabId},func:()=>({url:location.href,key:String(performance.timeOrigin)})});
  return result[0]?.result;
 }
 async inspectEntry(){
  const tab=await chrome.tabs.get(this.tabId);if(!tab.url?.startsWith('https:'))throw Error('请在对应HTTPS官网核对');
  const result=await chrome.scripting.executeScript({target:{tabId:this.tabId},func:()=>({
   url:location.href,title:document.title,
   headings:[...document.querySelectorAll('h1,h2,h3,[class*="job-title"],[class*="position-title"]')].filter(e=>e.getClientRects().length).map(e=>e.textContent.trim().slice(0,300)).filter(Boolean).slice(0,30),
   employer_links:[...document.querySelectorAll('a[href]')].filter(a=>/官网|官方网站|Official Website/i.test(a.textContent)).map(a=>a.href).filter(u=>u.startsWith('https:')).slice(0,10),
   state:document.querySelector('input[type=password]')?'login':document.querySelector('input:not([type=hidden]),textarea')?'form':'detail'
  })});
  if(result.length!==1)throw Error('页面核对目标不唯一');return result[0].result;
 }
 async queryProgress(job){
  const visited=new Set();
  for(let step=0;step<4;step++){
   let observation;
   for(let n=0;n<16;n++){
    const tab=await chrome.tabs.get(this.tabId);
    if(tab.status==='complete'){
     await chrome.scripting.executeScript({target:{tabId:this.tabId},files:['progress-reader.js']});
     const result=await chrome.scripting.executeScript({target:{tabId:this.tabId},func:job=>JobProgressReader.read(job),args:[job]});
     observation=result[0]?.result;
     if(observation?.status==='needs_user'||observation?.status==='records'||observation?.records?.length)return observation;
     if(observation?.nav?.some(n=>!visited.has(n.label)))break;
    }
    await new Promise(resolve=>setTimeout(resolve,400));
   }
   const next=observation?.nav?.find(n=>!visited.has(n.label));
   if(!next)return observation||{status:'unavailable'};
   visited.add(next.label);
   await chrome.scripting.executeScript({target:{tabId:this.tabId},func:(job,label,url)=>JobProgressReader.navigate(job,label,url),args:[job,next.label,observation.url]});
   await new Promise(resolve=>setTimeout(resolve,800));
  }
  return {status:'unavailable'};
 }
 async reloadAndScan(expectedUrl){
  const tab=await chrome.tabs.get(this.tabId);if(tab.url!==expectedUrl)throw Error('官网已切换，未刷新');
  const before=await this.call('scan'),document=await this.documentKey();
  const count=before.ok?before.result.fields.length:0;let last,signature='',stable=0,error='';
  await chrome.tabs.reload(this.tabId,{bypassCache:true});
  for(let n=0;n<60;n++){
   await new Promise(r=>setTimeout(r,500));const current=await chrome.tabs.get(this.tabId);
   if(current.url!==expectedUrl)throw Error('官网刷新后需要重新登录或检查页面');
   try{
    const nextDocument=await this.documentKey();if(nextDocument?.key===document?.key)continue;
    const scan=await this.call('scan');
    if(!scan.ok){error=scan.error?.message||'';continue;}
    if(!scan.result.fields?.some(f=>!f.disabled))continue;
    last=scan.result;
    const next=JSON.stringify(last.fields.map(f=>[f.label,f.currentValue]));stable=next===signature?stable+1:0;signature=next;
    // The form can already be usable while a third-party resource keeps the
    // browser's tab.status at loading. Check the new document and stable form.
    if(last.fields.length>=count&&stable>=1)return last;
   }catch(e){error=e.message;}
  }
  if(last)return last;
  throw Error('官网重新打开后未能读取表单'+(error?'：'+error:'，尚未确认内容已保存'));
 }

 constructor(tabId){
  if(!Number.isInteger(tabId))throw Error('需要明确的 tabId');this.tabId=tabId;this.channel=crypto.randomUUID();
  chrome.runtime.onMessage.addListener((message,sender,respond)=>{
   if(message?.type!=='jobfill:native-text'||message.channel!==this.channel)return;
   if(sender.id!==chrome.runtime.id||sender.tab?.id!==this.tabId||sender.frameId!==0||message.url!==this.activeUrl||!/^https:/.test(message.url)||!/^[0-9a-f-]{36}$/i.test(message.marker)||typeof message.value!=='string'||message.value.length>200000||typeof message.blur!=='boolean'){respond({ok:false,error:'文本输入请求未通过目标校验'});return;}
   chrome.tabs.get(this.tabId).then(tab=>{if(tab.url!==message.url)throw Error('网页已切换');return chrome.scripting.executeScript({target:{tabId:this.tabId},world:'MAIN',func:jobFillNativeSetter,args:[message.marker,message.value,message.blur,message.url]});}).then(results=>{if(results.length!==1)throw Error('执行目标不唯一');respond({ok:true,result:results[0].result});}).catch(e=>respond({ok:false,error:e.message}));
   return true;
  });
 }
 async call(method,payload={}){
  const tab=await chrome.tabs.get(this.tabId),u=new URL(tab.url||'');
  if(u.protocol!=='https:')throw Error('执行器仅在用户主动调用的 HTTPS 页面运行');
  this.activeUrl=tab.url;
  await chrome.scripting.executeScript({target:{tabId:this.tabId},func:channel=>{window.JobFillNativeChannel=channel;window.JobFillClientRevision='1.2.13';},args:[this.channel]});
  await chrome.scripting.executeScript({target:{tabId:this.tabId},files:['executor-core.js','dom-utils.js','generic-adapter.js','feishu-adapter.js','icbc-adapter.js','bootstrap.js']});
  const results=await chrome.scripting.executeScript({target:{tabId:this.tabId},func:(m,p)=>window.JobFillExecutor.dispatch(m,p),args:[method,payload]});
  if(results.length!==1)throw Error('执行目标不唯一');return results[0].result;
 }
};

if(typeof window!=='undefined')window.JobFillClient=globalThis.JobFillClient;
