const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function fixture(readyAt=3){
 const state={ticks:0,ready:false,events:0,time:0};
 const row={get innerHTML(){return state.ready?'completed-card':'pending-card';},querySelectorAll(){return Array(state.ready?3:1).fill({});},querySelector(){return null;}};
 const root={querySelector(){return row;},querySelectorAll(){return [{textContent:'fictional.pdf'}];}};
 const input={closest(){return root;},dispatchEvent(){state.events++;}};
 const D={text:e=>e?.textContent?.trim()||'',visible:()=>true,one:es=>es[0],click(){},setTextCommitted(){},show(){},async wait(fn,ctx){
  for(let n=0;n<25;n++){ctx.check();state.ticks++;state.time+=100;state.ready=state.ticks>=readyAt;const value=fn();if(value)return value;}
  throw Error('waiting timed out');
 }};
 const context=vm.createContext({window:{JobFillDOM:D},location:{href:'https://fixture.example/form'},document:{querySelectorAll(){return [];}},performance:{now:()=>state.time}});
 vm.runInContext(fs.readFileSync(__dirname+'/generic-adapter.js','utf8'),context);
 return {state,adapter:context.window.JobFillAdapters.generic,attachment:{fileNames:['fictional.pdf'],input},ctx:{check(){}}};
}
test('matching filename on retry waits for upload completion and stable controls',async()=>{
 const f=fixture(),r=await f.adapter.uploadAttachment(f.attachment,{fileName:'fictional.pdf'},f.ctx);
 assert.equal(r.status,'attachment-present');assert(f.state.ticks>=10);assert.equal(f.state.events,0,'must not duplicate an in-flight upload');
});
test('pending filename alone never confirms a completed upload',async()=>{
 const f=fixture(Infinity);await assert.rejects(f.adapter.uploadAttachment(f.attachment,{fileName:'fictional.pdf'},f.ctx),/尚未完成上传/);assert.equal(f.state.events,0);
});
test('cancellation is preserved while waiting for the existing upload',async()=>{
 const f=fixture(Infinity);f.ctx.check=()=>{throw Error('已停止');};await assert.rejects(f.adapter.uploadAttachment(f.attachment,{fileName:'fictional.pdf'},f.ctx),/已停止/);
});
