const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
function fixture(){
 let observer,disconnected=0,now=0;const timers=new Map(),listeners=new Map();let serial=0;
 const document={documentElement:{},addEventListener:(n,f)=>listeners.set(n,f),removeEventListener:(n,f)=>{if(listeners.get(n)===f)listeners.delete(n);}};
 const sandbox={window:{},document,performance:{now:()=>now},setTimeout:f=>{timers.set(++serial,f);return serial;},clearTimeout:id=>timers.delete(id),MutationObserver:class{constructor(f){observer=f;}observe(){}disconnect(){disconnected++;}}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'dom-utils.js'),'utf8'),sandbox);
 return {wait:sandbox.window.JobFillDOM.wait,timers,listeners,mutate:()=>observer(),event:n=>listeners.get(n)?.(),advance:n=>now+=n,disconnected:()=>disconnected};
}
test('DOM changes resolve waits even when background timers never run',async()=>{
 const f=fixture();let ready=false;const result=f.wait(()=>ready&&'selected',{check(){}});assert.equal(f.timers.size,1);
 ready=true;f.mutate();assert.equal(await result,'selected');assert.equal(f.timers.size,0);assert.equal(f.listeners.size,0);assert.equal(f.disconnected(),1);
});
test('input events wake property-only updates and cancellation cleans up',async()=>{
 const f=fixture();let value='';const result=f.wait(()=>value,{check(){}});value='committed';f.event('input');assert.equal(await result,'committed');
 const g=fixture();let cancelled=false;const failed=g.wait(()=>false,{check(){if(cancelled)throw Error('cancelled');}});cancelled=true;g.mutate();await assert.rejects(failed,/cancelled/);assert.equal(g.listeners.size,0);assert.equal(g.timers.size,0);
});
test('mutation wakeups retain timeout boundary without leaking observers',async()=>{
 const f=fixture();const failed=f.wait(()=>false,{check(){}},100);f.advance(101);f.mutate();await assert.rejects(failed,/超时/);assert.equal(f.disconnected(),1);assert.equal(f.timers.size,0);
});
