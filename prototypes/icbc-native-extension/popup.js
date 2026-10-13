const output=document.querySelector('#result'),request=document.querySelector('#request');
let client,snapshot,latestResponse;
async function connected(){if(!client){const [tab]=await chrome.tabs.query({active:true,currentWindow:true});client=new JobFillClient(tab.id);}return client;}
const display=r=>{latestResponse=r;output.textContent=JSON.stringify(r,null,2);};
async function call(method,payload={}){return (await connected()).call(method,payload);}
async function run(fn){try{await fn();}catch(e){display({ok:false,error:e.message});}}
document.querySelector('#scan').onclick=()=>run(async()=>{const r=await call('scan');if(r.ok)snapshot=r.result;display(r);});
document.querySelector('#status').onclick=()=>run(async()=>display(await call('status')));
document.querySelector('#cancel').onclick=()=>run(async()=>display(await call('cancel')));
document.querySelector('#send').onclick=()=>run(async()=>{const parsed=JSON.parse(request.value);display(await call(parsed.method,parsed.payload));});
document.querySelector('#validate').onclick=()=>run(async()=>{const parsed=JSON.parse(request.value);if(parsed.method!=='execute')throw Error('此按钮仅检查 execute 填写计划');display(await call('validate',parsed.payload));});
for(const [id,name] of [['demo','fill'],['records','records']])document.getElementById(id).onclick=()=>run(async()=>{const r=await call('scan');if(!r.ok){display(r);return;}snapshot=r.result;request.value=JSON.stringify(JobFillDemo[name](snapshot),null,2);display({ok:true,note:'仅生成虚构请求，尚未执行。'});});
document.querySelector('#report').onclick=()=>run(async()=>{const r=latestResponse||await call('status');display(r);if(r){await chrome.scripting.executeScript({target:{tabId:client.tabId},func:data=>{let p=document.querySelector('#jobfill-executor-report');if(!p){p=document.createElement('pre');p.id='jobfill-executor-report';p.style.cssText='position:fixed;right:14px;bottom:80px;max-width:400px;max-height:260px;overflow:auto;background:white;border:1px solid #aaa;padding:12px;z-index:2147483646;font:11px monospace;white-space:pre-wrap';document.body.append(p);}p.textContent=JSON.stringify(data,null,2);},args:[r]});}});
