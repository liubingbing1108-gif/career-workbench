(() => {
 'use strict';
 const q=(s,r=document)=>[...r.querySelectorAll(s)], text=e=>e?.textContent?.trim()||'';
 const visible=e=>!!e?.isConnected&&!!e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden';
 const one=(items,name)=>{if(items.length!==1)throw Error(name+'匹配数量 '+items.length);return items[0];};
 const click=e=>{if(!visible(e)||e.disabled)throw Error('控件不可操作');e.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,button:0}));e.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,button:0}));e.click();};
 function setText(e,value,blur=true){if(e.disabled||e.readOnly)throw Error('文本不可写');e.focus();Object.getOwnPropertyDescriptor(e.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,'value').set.call(e,value);e.dispatchEvent(new InputEvent('input',{bubbles:true,composed:true,inputType:'insertText',data:value}));e.dispatchEvent(new Event('change',{bubbles:true,composed:true}));e.dispatchEvent(new KeyboardEvent('keyup',{key:'Unidentified',bubbles:true}));if(blur)e.blur();}
 const nativeChannel=()=>window.JobFillNativeChannel;
 async function setTextCommitted(e,value,blur=true){
  if(e.disabled||e.readOnly||!nativeChannel())throw Error('文本输入未接通');
  if(e.hasAttribute('data-jobfill-native-field'))throw Error('该输入框已有填写请求');
  const marker=crypto.randomUUID();e.setAttribute('data-jobfill-native-field',marker);
  try{const r=await chrome.runtime.sendMessage({type:'jobfill:native-text',channel:nativeChannel(),marker,value,blur,url:location.href});if(!r?.ok)throw Error(r?.error||'文本输入连接中断');if(r.result.value!==value)throw Error('文本输入实际值不一致');}
  finally{if(e.getAttribute('data-jobfill-native-field')===marker)e.removeAttribute('data-jobfill-native-field');}
 }
 const wait=(fn,ctx,ms=5000)=>new Promise((resolve,reject)=>{const start=performance.now();const tick=()=>{try{ctx.check();const r=fn();if(r)return resolve(r);if(performance.now()-start>=ms)throw Error('等待官网控件超时');setTimeout(tick,25);}catch(e){reject(e);}};tick();});
 const show=message=>{let p=document.querySelector('#jobfill-executor-progress');if(!p){p=document.createElement('aside');p.id='jobfill-executor-progress';p.style.cssText='position:fixed;right:14px;bottom:14px;max-width:400px;padding:14px;background:#17243a;color:white;z-index:2147483647;font:14px/1.6 system-ui;pointer-events:none';document.body.append(p);}p.textContent=message;};
 async function settle(errors,ctx){let stable=0;await wait(()=>{if(errors().length){stable=0;return false;}if(!stable)stable=performance.now();return performance.now()-stable>=350;},ctx,5000);}
 window.JobFillDOM={q,text,visible,one,click,setText,setTextCommitted,nativeTextBridgeReady:!!nativeChannel(),wait,show,settle};
})();
