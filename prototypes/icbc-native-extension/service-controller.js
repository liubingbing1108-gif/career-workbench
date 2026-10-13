/* One background controller, one selected official tab. No UI or submit action. */
class JobFillService {
 constructor(){this.connection=null;this.url=null;this.running=false;this.launching=false;this.stopped=false;this.timer=null;this.client=null;}
 async request(action,data={}){
  const response=await fetch('http://127.0.0.1:8768/api/executor/'+action,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({connection:this.connection,url:this.url,...data})});
  const result=await response.json();if(!response.ok)throw Error(result.error||'填写连接中断');return result;
 }
 async target(details){
  const role=new URL(details.url),job=role.searchParams.get('jobAdId');
  const candidates=await chrome.tabs.query({url:role.origin+'/*'});
  const matches=candidates.filter(t=>{try{const u=new URL(t.url);return t.url===details.url||job&&u.searchParams.get('jobAdId')===job&&['/form','/campus/detail','/social/detail'].includes(u.pathname);}catch{return false;}});
  return matches.find(t=>t.id===this.tabId)||matches.find(t=>new URL(t.url).pathname==='/form')||matches[0]||await chrome.tabs.create({url:details.url,active:false});
 }
 async launch(ticket){
  if(this.running)throw Error('正在填写，需先暂停');
  if(this.launching)return {ok:false,message:'正在连接，请稍候'};
  this.launching=true;
  try{
   const details=await this.request('launch-claim',{ticket});
   this.ticket=ticket;this.details=details;this.stopped=false;
   const tab=await this.target(details);this.tabId=tab.id;this.client=new JobFillClient(tab.id);
   if(details.mode==='focus'){await chrome.tabs.update(tab.id,{active:true});await chrome.windows.update(tab.windowId,{focused:true});}
   this.connection=null;this.url=null;this.prepared=false;this.schedule(0);return {ok:true};
  }finally{this.launching=false;}
 }
 schedule(ms=1000){clearTimeout(this.timer);this.timer=setTimeout(()=>this.tick(),ms);}
 async connect(){
  const tab=await chrome.tabs.get(this.tabId);if(tab.status!=='complete')return false;
  const target=new URL(this.details.url),actual=new URL(tab.url);
  if(actual.protocol!=='https:'||actual.origin!==target.origin)throw Error('请在对应官网完成登录');
  this.url=tab.url;
  let scan=await this.client.call('scan');if(!scan.ok||!scan.result.fields?.some(f=>!f.disabled))return false;
  if(!this.connection)this.connection=(await this.request('connect',{code:this.details.code})).connection;this.connectedUrl=this.url;
  for(const field of scan.result.fields){
   if(field.disabled)continue;
   if(field.context?.driver==='phoenix-calendar'&&field.kind==='unsupported'){
    await this.client.call('readDateFormat',{snapshotId:scan.result.snapshotId,fieldId:field.fieldId});
   }
  }
  scan=await this.client.call('scan');if(!scan.ok)throw Error(scan.error.message);
  const options=new Map();
  for(const field of scan.result.fields.filter(f=>!f.disabled&&f.kind==='select'&&f.options?.state==='requires-opening')){
   const result=await this.client.call('readOptions',{snapshotId:scan.result.snapshotId,fieldId:field.fieldId});if(result.ok)options.set(field.fieldId,result.result);
  }
  scan=await this.client.call('scan');if(!scan.ok)throw Error(scan.error.message);
  for(const f of scan.result.fields)if(options.has(f.fieldId))f.options=options.get(f.fieldId);
  const snapshot={...scan.result,fields:scan.result.fields.map(({currentValue,...field})=>field)};
  await this.request('scan',{snapshot});await this.request('launch-report',{ticket:this.ticket,status:'ready'}).catch(()=>{});this.connectedUrl=this.url;this.prepared=true;return true;
 }
 async tick(){
  if(this.stopped||this.running)return;
  try{
   if(!this.connection||!this.prepared){if(!await this.connect()){await this.request('launch-report',{ticket:this.ticket,status:'needs_user'}).catch(()=>{});this.schedule(3000);return;}}
   const tab=await chrome.tabs.get(this.tabId);if(tab.url!==this.connectedUrl){this.connection=null;this.schedule();return;}
   const next=await this.request('launch-next');if(next.ticket){await this.launch(next.ticket);return;}
   const result=await this.request('poll');if(result.stop){this.stopped=true;return;}
   if(result.job){
    this.running=true;let counts={filled:0,verified:0};
    const report=async p=>{counts=p;const res=await this.request('report',{job_id:result.job.id,...p});if(res.stop)this.stopped=true;};
    try{await JobFillMaterials.run(this.client,result.job.materials,report,()=>this.stopped);}
    catch(e){await report({...counts,status:this.stopped?'paused':'failed',issues:[...(counts.issues||[]),e.message],message:'填写已停止，请查看未完成事项。'}).catch(()=>{});}
    finally{this.running=false;}
   }
   this.schedule();
  }catch(e){
   await this.request('launch-report',{ticket:this.ticket,status:'needs_user'}).catch(()=>{});
   // A disconnected controller never opens new pages by itself.
   this.schedule(4000);
  }
 }
}
globalThis.JobFillService=JobFillService;
