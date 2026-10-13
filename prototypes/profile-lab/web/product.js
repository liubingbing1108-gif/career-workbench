/* Two primary pages; preparation belongs to one managed job. */
let preparingJob=null;
const browserLaunches=new Map();
function cancelJobPreparation(){
  const old=preparingJob;preparingJob=null;old?.controller.abort();if(old)refreshRevision++;
}
window.addEventListener('workbench:view-change',event=>{if(event.detail!== 'practice')cancelJobPreparation();});
function targetUrl(session){return session?.website?.url||session?.target?.url||session?.form_analysis?.url||'';}
function flowWaiting(title,message,actions=''){
  $('#target-waiting').hidden=false;$('#form-analysis').hidden=true;
  const fingerprint=JSON.stringify([title,message,actions]);const dataset=$('#target-waiting').dataset;if(dataset?.content===fingerprint)return;
  if(dataset)dataset.content=fingerprint;
  $('#target-waiting').innerHTML=`<section class="flow-waiting">${actions?'':'<span class="flow-spinner" aria-hidden="true"></span>'}<h2>${escapeHtml(title)}</h2><p>${escapeHtml(message)}</p><div class="button-row">${actions}</div></section>`;
}
function updateTargetPanel(session){
  if(preparingJob)return;
  $('#reread-form').hidden=!session;
  $('#show-execution').hidden=!session;
  const url=targetUrl(session);$('#application-url').value=url;
  $('#flow-identity').textContent=session?.name||'';
  if(session?.manual_reason){flowWaiting('此岗位需要本人处理',session.manual_reason,'<button id="target-official" class="primary">去官网处理</button>');$('#target-official').onclick=safe(()=>launchBrowser('focus'));return;}
  const ready=!!session?.form_analysis&&!!session?.website&&!['matching','failed'].includes(preparationState.scan_status);
  $('#target-waiting').hidden=ready;
  if(ready)return;
  if(!session){flowWaiting('从投递管理开始','录入岗位后，点击该行“开始投递”。');return;}
  const browser=preparationState.browser,stalled=browser?.status==='opening'&&Date.now()/1000-browser.updated_at>25;
  const needsUser=browser?.status==='needs_user',failed=preparationState.scan_status==='failed'||browser?.status==='failed'||stalled;
  const title=needsUser?'官网需要你继续':failed?'本次准备需要继续':preparationState.scan_status==='matching'?'正在匹配你的资料':'正在读取官网岗位';
  flowWaiting(title,browser?.status==='failed'?browser.message:preparationState.scan_error||browser?.message||'系统正在解析链接、确认岗位并读取申请表，完成后会自动展示可选材料。',needsUser?'<button id="target-official" class="primary">去官网处理</button><button id="target-connect">我已完成，继续</button>':failed?'<button id="target-connect" class="primary">重试本次准备</button>':'');
  if($('#target-connect'))$('#target-connect').onclick=safe(()=>launchBrowser('prepare',true));
  if($('#target-official'))$('#target-official').onclick=safe(()=>launchBrowser('focus'));
}
async function managementApi(path,body,signal){
  const bootstrapResponse=await fetch('/management/api/bootstrap',{signal});
  const bootstrap=await bootstrapResponse.json();
  const res=await fetch('/management/api'+path,{signal,method:body?'POST':'GET',headers:{'Content-Type':'application/json','X-Management-Token':bootstrap.token},body:body?JSON.stringify(body):undefined});
  const result=await res.json();if(!res.ok)throw Error(result.error||'岗位准备失败');return result;
}
async function prepareManagedJob(job,retry=false){
  cancelJobPreparation();
  const run={jobId:job.id,controller:new AbortController()};preparingJob=run;
  const active=()=>preparingJob===run&&currentView==='practice'&&!run.controller.signal.aborted;
  const request=(path,body)=>managementApi('/jobs/'+encodeURIComponent(job.id)+path,body,run.controller.signal);
  sessionId=null;$('#show-execution').hidden=true;
  showView('practice');$('#flow-identity').textContent=[job.company,job.title||job.role].filter(Boolean).join(' · ');
  flowWaiting('正在检查投递链接','先核对已提供页面；资讯或招聘首页再查具体岗位。返回后可随时继续。');
  try{
    let official=await request('/resolution',{retry});
    if(official.status==='needs_inspection'){
      flowWaiting('正在检查已提供的页面','复用Chrome中的页面，核对公司、岗位和登录状态；不会填写或上传材料。');
      const bridge=await extensionMessage('career:hello');
      const inspection=await api('/api/entry-inspection',{job_id:job.id,direct:bridge?.ok===true});
      if(bridge?.ok){const checked=await extensionMessage('career:launch',{ticket:inspection.ticket});if(!checked?.ok)throw Error(checked?.message||'指定页面核对未完成，请重试。');}
      for(let n=0;n<30&&active();n++){
        official=await request('/resolution');if(official.status!=='needs_inspection')break;
        await new Promise(resolve=>setTimeout(resolve,1000));
      }
      if(official.status==='needs_inspection')official={...official,message:'指定页面尚未连接。请检查Chrome中的当前官网后重试；未发送个人材料。'};
    }
    while(active()&&official.status==='resolving'){
      flowWaiting(official.stage||'正在查找官网岗位',(official.message||'正在核对官网与具体岗位。')+' 已用 '+Math.floor(official.elapsed||0)+' 秒；返回管理后仍可继续。');
      await new Promise((resolve,reject)=>{
        const signal=run.controller.signal;
        const onAbort=()=>{clearTimeout(timer);reject(new DOMException('已离开本次准备','AbortError'));};
        const timer=setTimeout(()=>{signal.removeEventListener('abort',onAbort);resolve();},1000);
        signal.addEventListener('abort',onAbort,{once:true});
      });
      if(!active())return;
      official=await request('/resolution');
    }
    if(!active())return;
    if(official.status!=='ready'){
      flowWaiting('官网岗位尚需核对',official.message,'<button id="resolve-retry">重新查找</button><button id="resolve-back">返回管理修改岗位</button>');
      const box=document.createElement('div');box.className='official-candidates';
      box.innerHTML=(official.candidates||[]).map((c,i)=>`<p><strong>${escapeHtml(c.official_role||c.role)}</strong> · ${escapeHtml(c.location)}<br><a href="${escapeHtml(c.url)}" target="_blank" rel="noopener">查看候选官网</a>${c.verification==='public_pages'?` <button data-official-choice="${i}">${official.status==='identity_mismatch'?'采用官网岗位名称并继续':'选择此岗位'}</button>`:''}</p>`).join('');$('#target-waiting').append(box);
      $$('[data-official-choice]',box).forEach(button=>button.onclick=safe(async()=>{
        button.disabled=true;
        try{const selected=await managementApi('/jobs/'+encodeURIComponent(job.id)+'/resolution-choice',{url:official.candidates[Number(button.dataset.officialChoice)].url,confirm_role:official.status==='identity_mismatch'});await prepareManagedJob(selected.job);}
        catch(error){button.disabled=false;toast(error.message);}
      }));
      $('#resolve-retry').onclick=safe(()=>prepareManagedJob(job,true));$('#resolve-back').onclick=()=>showView('management');return;
    }
    $('#management-frame').contentWindow.postMessage({type:'workbench:jobs-changed'},location.origin);
    flowWaiting('官网投递入口已核对','正在连接对应官网，若需要登录，会在这里提示。');
    const result=await api('/api/preparation/open',{job_id:job.id});if(!active())return;sessionId=result.id;
    history.replaceState(null,'','#practice/'+sessionId);
    await refresh();if(!active())return;
    preparingJob=null;updateTargetPanel(state.sessions.find(s=>s.id===sessionId));window.scrollTo({top:0});
    if(!result.manual_reason&&!preparationState.executor?.connected&&!['running','awaiting_executor'].includes(result.preparation?.execution?.status))await launchBrowser();
  }catch(error){
    if(!active()||error.name==='AbortError')return;
    flowWaiting('本次准备未完成',error.message,'<button id="resolve-retry">重试</button>');$('#resolve-retry').onclick=safe(()=>prepareManagedJob(job,true));
  }finally{if(preparingJob===run)preparingJob=null;}
}
function extensionMessage(type,extra={}){
 return new Promise(resolve=>{const requestId=crypto.randomUUID();let timer;const receive=event=>{if(event.source===window&&event.origin===location.origin&&event.data?.type==='career:reply'&&event.data.requestId===requestId){clearTimeout(timer);window.removeEventListener('message',receive);resolve(event.data.result);}};window.addEventListener('message',receive);timer=setTimeout(()=>{window.removeEventListener('message',receive);resolve(null);},type==='career:hello'?300:12000);window.postMessage({type,requestId,...extra},location.origin);});
}
async function launchBrowser(mode='prepare',rescan=false){
  const selected=sessionId,key=selected+'/'+mode;
  if(browserLaunches.has(key))return browserLaunches.get(key);
  const pending=(async()=>{const bridge=await extensionMessage('career:hello');const result=await api('/api/browser-launch',{session_id:selected,mode,rescan,direct:bridge?.ok===true});if(bridge?.ok&&result.ticket){const connected=await extensionMessage('career:launch',{ticket:result.ticket});if(!connected?.ok)throw Error(connected?.message||'插件连接未完成，请重试。');}if(mode==='prepare'&&selected===sessionId&&currentView==='practice'){const next=await api('/api/preparation?session='+encodeURIComponent(selected));if(selected===sessionId&&currentView==='practice'){preparationState={...next,current:preparationState.current};updateTargetPanel(state.sessions.find(s=>s.id===selected));updatePreparationProgress();}}return result;})();
  browserLaunches.set(key,pending);
  try{return await pending;}finally{if(browserLaunches.get(key)===pending)browserLaunches.delete(key);}
}
window.addEventListener('message',safe(async event=>{
  if(event.origin!==location.origin||event.source!==$('#management-frame').contentWindow)return;
  if(event.data?.type==='workbench:deleted'){
    const removed=state.sessions.filter(s=>s.management_job_id===event.data.job_id).map(s=>s.id);
    for(const key of answerDrafts.keys())if(removed.some(id=>key.startsWith(id+'/')))answerDrafts.delete(key);
    const activeRemoved=removed.includes(sessionId);await refresh();if(activeRemoved)showView('management');return;
  }
  if(event.data?.type==='workbench:prepare')await prepareManagedJob(event.data.job);
}));
$('#back-management').onclick=()=>showView('management');
$('#show-execution').onclick=()=>showExecutionDialog();
$('#reread-form').onclick=safe(()=>launchBrowser('prepare',true));
$('#execution-minimize').onclick=()=>$('#execution-dialog').close();
$('#execution-return').onclick=()=>{$('#execution-dialog').close();showView('management');};
$('#execution-official').onclick=safe(()=>launchBrowser('focus'));
$('#execution-pause').onclick=safe(async()=>{await api('/api/preparation/pause',{session_id:sessionId});preparationState={...await api('/api/preparation?session='+encodeURIComponent(sessionId)),current:preparationState.current};updatePreparationProgress();});
window.addEventListener('hashchange',safe(async()=>{
  if(location.hash==='#management'){showView('management');return;}
  if(location.hash==='#practice'){showView('management');return;}
  const requested=location.hash.match(/^#practice\/([\w-]+)$/)?.[1];
  if(requested&&state?.sessions.some(s=>s.id===requested)){sessionId=requested;await refresh();showView('practice');}
  else if(location.hash.startsWith('#profile/'))showView('profile');
}));
if(new URLSearchParams(location.search).has('lab')){document.body.classList.add('lab-mode');$('#session-select').parentElement.hidden=false;$('#application-link-form').hidden=true;$('#new-session').onclick=safe(async()=>{sessionId=(await api('/api/sessions',{name:'新的虚构演练'})).id;history.replaceState(null,'','#practice/'+sessionId);await refresh();showView('practice');});}
setInterval(async()=>{
  if(preparingJob||currentView!=='practice')return;
  const current=state?.sessions.find(s=>s.id===sessionId);if(!current?.target||current.website&&!['matching','failed'].includes(preparationState.scan_status))return;
  try{const selected=sessionId,newest=await api('/api/state');if(selected!==sessionId||currentView!=='practice')return;const session=newest.sessions.find(s=>s.id===selected);if(session?.website&&!current.website||session?.preparation?.scan_status!==preparationState.scan_status)await refresh();else if(session){preparationState={...preparationState,...session.preparation};updateTargetPanel(session);}}catch{}
},1800);
