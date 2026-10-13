const test=require('node:test'),assert=require('node:assert/strict');
const {PreparationSaveQueue}=require('./web/preparation-store.js');
const tick=()=>new Promise(r=>setImmediate(r));
const deferred=()=>{let resolve;const promise=new Promise(a=>{resolve=a;});return {promise,resolve};};
test('rapid checks serialize and coalesce latest intent',async()=>{
 const gate=deferred(),sent=[],paints=[];let calls=0;
 const q=new PreparationSaveQueue(async(p,b)=>{sent.push(b.ids);if(++calls===1)await gate.promise;},async()=>({ids:sent.at(-1)}),()=>{},(id,b)=>paints.push(b.ids));
 q.enqueue('a','g','choices',{ids:['one']});q.enqueue('a','g','choices',{ids:['one','two']});q.enqueue('a','g','choices',{ids:['two']});
 assert.equal(sent.length,1);gate.resolve();await tick();assert.deepEqual(sent,[['one'],['two']]);assert.deepEqual(paints,[['two']]);assert(!q.busy('a'));
});
test('late preview cannot repaint a newer click',async()=>{
 const gate=deferred();let reads=0;const paints=[];
 const q=new PreparationSaveQueue(async()=>{},async()=>++reads===1?gate.promise:{fresh:true},()=>{},(id,b)=>paints.push(b));
 q.enqueue('a','g','choices',{});await tick();q.enqueue('a','g','choices',{});gate.resolve({stale:true});await tick();assert.deepEqual(paints,[{fresh:true}]);
});
test('failed save keeps intent and blocks confirmation until retry',async()=>{
 let fail=true,saved;const q=new PreparationSaveQueue(async(p,b)=>{if(fail)throw Error('offline');saved=b;},async()=>({}),()=>{},()=>{});
 q.enqueue('a','g','choices',{ids:['two']});await tick();assert(q.busy('a'));assert.equal(q.state('a').error,'offline');fail=false;q.retry('a');await tick();assert(!q.busy('a'));assert.deepEqual(saved.ids,['two']);
});
test('independent jobs and failed-read retry never duplicate a mutation',async()=>{
 let writes=0,fail=true;const q=new PreparationSaveQueue(async()=>{writes++;},async()=>{if(fail)throw Error('read');return {};},()=>{},()=>{});
 q.enqueue('a','g','choices',{});await tick();assert.equal(writes,1);fail=false;q.retry('a');q.enqueue('b','g','choices',{});await tick();assert.equal(writes,2);assert(!q.busy('a'));assert(!q.busy('b'));
});
