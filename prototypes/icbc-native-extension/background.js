importScripts('client.js','material-runner.js','service-controller.js');
const controller=new JobFillService(),launched=new Set();let serial=Promise.resolve();
chrome.runtime.onMessage.addListener((message,sender,respond)=>{
 if(!['jobfill:hello','jobfill:launch'].includes(message?.type))return;
 let u;try{u=new URL(sender.url);}catch{return;}
 if(!['http://127.0.0.1:8768','http://localhost:8768'].includes(u.origin)||sender.frameId!==0)return;
 if(message.type==='jobfill:hello'){respond({ok:true,version:'1.2.9'});return;}
 if(!/^[A-Za-z0-9_-]{20,100}$/.test(message.ticket))return;
 serial=serial.catch(()=>{}).then(async()=>{
  if(!await chrome.permissions.contains({origins:['https://*/*']}))throw Error('尚未启用自动填写权限');
  if(!launched.has(message.ticket)){const result=await controller.launch(message.ticket);if(!result.ok)return result;launched.add(message.ticket);}
  // Only the dedicated relay may close itself. Never close the user's workbench.
  if(u.pathname==='/launch-relay'&&u.searchParams.get('launch')===message.ticket&&sender.tab?.id)await chrome.tabs.remove(sender.tab.id);
  return {ok:true};
 });
 serial.then(respond).catch(e=>respond({ok:false,message:e.message}));return true;
});
