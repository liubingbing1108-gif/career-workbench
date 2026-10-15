const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function fixture(sendMessage,path='/'){
 const replies=[],sent=[];let listener;
 const window={addEventListener:(_,fn)=>listener=fn,postMessage:(data,origin)=>replies.push({data,origin})};
 const context=vm.createContext({URL,window,location:{origin:'http://127.0.0.1:8768',pathname:path.split('?')[0],href:'http://127.0.0.1:8768'+path},chrome:{runtime:{sendMessage:m=>{sent.push(m);return sendMessage(m);}}}});
 vm.runInContext(fs.readFileSync(__dirname+'/local-launch.js','utf8'),context);
 return {replies,sent,message:extra=>listener({source:window,origin:'http://127.0.0.1:8768',data:{type:'career:hello',requestId:'fixture'},...extra})};
}
test('synchronous invalidated context replies recoverably instead of throwing',async()=>{const f=fixture(()=>{throw Error('Extension context invalidated.');});await f.message();assert.equal(f.replies[0].data.result.ok,false);assert.match(f.replies[0].data.result.message,/刷新工作台.*不要刷新招聘官网/);});
test('asynchronous disconnection is handled and successful handshake preserved',async()=>{const bad=fixture(()=>Promise.reject(Error('Disconnected')));await bad.message();assert.equal(bad.replies[0].data.result.ok,false);const good=fixture(async()=>({ok:true,version:'fixture'}));await good.message();assert.equal(good.replies[0].data.result.ok,true);assert.equal(good.sent[0].type,'jobfill:hello');});
test('foreign messages remain ignored',async()=>{const f=fixture(async()=>({ok:true}));await f.message({origin:'https://foreign.example'});assert.equal(f.sent.length,0);assert.equal(f.replies.length,0);});
test('relay also handles synchronous invalidation without an uncaught exception',async()=>{const f=fixture(()=>{throw Error('Extension context invalidated.');},'/launch-relay?launch=abcdefghijklmnopqrstuvwx');await Promise.resolve();assert.equal(f.sent.length,1);assert.equal(f.sent[0].type,'jobfill:launch');});
