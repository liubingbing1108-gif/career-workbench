// Page messages contain only a one-use ticket. The extension verifies the sender
// and the backend binds the ticket to one job and its verified official URL.
const localOrigin=location.origin;
window.addEventListener('message',event=>{
 if(event.source!==window||event.origin!==localOrigin||!['career:hello','career:launch'].includes(event.data?.type)||typeof event.data.requestId!=='string')return;
 const requestId=event.data.requestId;
 chrome.runtime.sendMessage({type:event.data.type==='career:hello'?'jobfill:hello':'jobfill:launch',ticket:event.data.ticket}).then(result=>window.postMessage({type:'career:reply',requestId,result},localOrigin)).catch(()=>window.postMessage({type:'career:reply',requestId,result:{ok:false}},localOrigin));
});
const launchTicket=new URL(location.href).searchParams.get('launch');
if(location.pathname==='/launch-relay'&&launchTicket&&/^[A-Za-z0-9_-]{20,100}$/.test(launchTicket))chrome.runtime.sendMessage({type:'jobfill:launch',ticket:launchTicket}).catch(()=>{});
