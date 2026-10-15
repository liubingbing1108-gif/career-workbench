const {test}=require('node:test'),assert=require('node:assert/strict');
const {AnswerDrafts}=require('./web/answer-drafts.js');
const tick=()=>new Promise(setImmediate);
const storage=()=>({value:null,getItem(){return this.value;},setItem(k,v){this.value=v;}});
test('unacknowledged newest keystrokes survive a browser reload and retry',async()=>{
 const disk=storage();let resolve;const pending=new Promise(r=>resolve=r);
 const drafts=new AnswerDrafts(disk,()=>pending);drafts.set('s/group/e/f','first');drafts.set('s/group/e/f','latest');
 const restored=new AnswerDrafts(disk,async(p,b)=>({value:b.value,revision:b.revision+1}));
 assert.equal(restored.get('s/group/e/f'),'latest');await restored.flush();assert.equal(restored.status('s').pending,false);
 resolve({value:'first',revision:1});await tick();assert.equal(drafts.get('s/group/e/f'),'latest');
});
test('server conflict retains local edits and failed deletion survives reload',async()=>{
 const disk=storage(),drafts=new AnswerDrafts(disk,async()=>{throw Error('另一页面已修改');});
 drafts.hydrate('s',{'s/g/e/f':{value:'old',revision:4}});drafts.set('s/g/e/f','local');await tick();
 assert.equal(drafts.get('s/g/e/f'),'local');assert(drafts.status('s').error);await assert.rejects(drafts.settled());
 drafts.delete('s/g/e/f');await tick();const restored=new AnswerDrafts(disk,async(p,b)=>({value:null,revision:5}));
 restored.hydrate('s',{'s/g/e/f':{value:'old',revision:4}});assert(!restored.has('s/g/e/f'));await restored.settled();
});
test('confirmed deletion and different sessions remain independent',async()=>{
 const drafts=new AnswerDrafts(storage(),async(p,b)=>({value:b.value,revision:b.revision+1}));
 drafts.set('a/g/e/f','A');drafts.set('b/g/e/f','B');await drafts.settled();drafts.delete('a/g/e/f');await drafts.settled();
 assert(!drafts.has('a/g/e/f'));assert.equal(drafts.get('b/g/e/f'),'B');assert.equal(drafts.status('a').pending,false);
});
