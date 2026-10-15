// Page messages contain only a one-use ticket. The extension verifies the sender
// and the backend binds the ticket to one job and its verified official URL.
(() => {
 const localOrigin=location.origin;
 const send=async message=>{
  // Reloading an extension invalidates content scripts already in open pages.
  // sendMessage can throw synchronously, before it returns a Promise.
  try{return await chrome.runtime.sendMessage(message);}
  catch{return {ok:false,message:'填写插件已更新或连接中断，请刷新工作台后重试；不要刷新招聘官网。'};}
 };
 window.addEventListener('message',async event=>{
  if(event.source!==window||event.origin!==localOrigin||!['career:hello','career:launch'].includes(event.data?.type)||typeof event.data.requestId!=='string')return;
  const requestId=event.data.requestId;
  const result=await send({type:event.data.type==='career:hello'?'jobfill:hello':'jobfill:launch',ticket:event.data.ticket});
  window.postMessage({type:'career:reply',requestId,result},localOrigin);
 });
 const launchTicket=new URL(location.href).searchParams.get('launch');
 if(location.pathname==='/launch-relay'&&launchTicket&&/^[A-Za-z0-9_-]{20,100}$/.test(launchTicket))void send({type:'jobfill:launch',ticket:launchTicket});
})();
