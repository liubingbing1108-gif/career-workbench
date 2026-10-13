/* Progress-state contract without a browser, network, or candidate data. */
const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function render(execution,confirming=false){
 const nodes=new Map();const node=id=>{if(!nodes.has(id))nodes.set(id,{hidden:false,textContent:'',innerHTML:'',classes:new Set(),classList:{toggle(name,on){const n=nodes.get(id);on?n.classes.add(name):n.classes.delete(name);}},setAttribute(){},removeAttribute(){}});return nodes.get(id);};
 const steps=Array.from({length:5},(_,i)=>node('step'+i));
 const context=vm.createContext({preparationState:{execution,current:{rows:[],pending:[]},browser:{message:'连接官网'}},sessionId:'fixture',answerDrafts:new Map(),$:(s)=>node(s),$$:(s)=>s==='#execution-steps li'?steps:[],escapeHtml:s=>s,setInterval(){}});
 vm.runInContext(fs.readFileSync(__dirname+'/web/preparation.js','utf8'),context);
 vm.runInContext('confirmingPreparation='+confirming+';updatePreparationProgress()',context);return {node,steps};
}
test('queued job has only the connection node active and no finished actions',()=>{const c=render({status:'awaiting_executor',filled:0,verified:0,message:'等待连接'});assert(c.steps[0].classes.has('active'));assert(c.steps.every(n=>!n.classes.has('done')));assert.equal(c.node('#execution-return').hidden,true);assert.equal(c.node('#execution-pause').hidden,false);});
test('pausing before connection does not claim completed stages',()=>{const c=render({status:'paused',filled:0,verified:0,message:'已暂停'});assert(c.steps[0].classes.has('active'));assert(c.steps.every(n=>!n.classes.has('done')));assert.equal(c.node('#execution-return').hidden,false);});
test('live field message and actual phase drive the monitor',()=>{const c=render({status:'running',phase:'filling',filled:2,verified:1,message:'正在填写：实习描述（3/8）'});assert(c.steps[1].classes.has('active'));assert.equal(c.node('#execution-current').textContent,'正在填写：实习描述（3/8）');assert(c.node('#execution-counts').textContent.includes('页面已核对 1'));});
test('finished review exposes exactly the two completion actions',()=>{const c=render({status:'needs_attention',phase:'review',filled:8,verified:8,saved:true});assert(c.steps[4].classes.has('active'));assert.equal(c.node('#execution-return').hidden,false);assert.equal(c.node('#execution-official').hidden,false);assert.equal(c.node('#execution-pause').hidden,true);});
test('a new confirmation never shows the previous run as current progress',()=>{const c=render({status:'needs_attention',phase:'review',filled:37,verified:37},true);assert(c.steps[0].classes.has('active'));assert.equal(c.node('#execution-counts').textContent,'');assert.equal(c.node('#execution-current').textContent,'正在自动连接本次官网');});

test('old save receipt with zero verified fields cannot display completed save/check steps',()=>{const c=render({status:'needs_attention',phase:'review',filled:29,verified:0,saved:true});assert(!c.steps[2].classes.has('done'));assert(!c.steps[3].classes.has('done'));assert(c.node('#execution-current').textContent.includes('尚未确认'));assert(!c.node('#execution-counts').textContent.includes('草稿已保存'));});

test('saved attachment names its official destination and the confirmation button names the company',()=>{
 const c=render({status:'needs_attention',phase:'review',filled:1,verified:1,saved:true,persistence_verified:true,attachment_verified:true,confirmed_materials:{title:'示例公司招聘门户',attachment:{name:'fictional.pdf'},rows:[]}});
 assert.equal(c.node('#execution-official').textContent,'去示例公司官网确认');
 assert.equal(c.node('#execution-attachment').textContent,'已保存到官网「简历附件」：fictional.pdf');
 assert.equal(c.node('#execution-attachment').hidden,false);
 const modern=render({status:'needs_attention',confirmed_materials:{title:'投递简历 - 示例公司校招官网',rows:[]}});assert.equal(modern.node('#execution-official').textContent,'去示例公司官网确认');
});
test('an in-page attachment without persistence evidence is not labelled saved',()=>{
 const c=render({status:'running',phase:'saving',attachment_verified:true,confirmed_materials:{attachment:{name:'fictional.pdf'},rows:[]}});
 assert(c.node('#execution-attachment').textContent.includes('正在检查'));assert(!c.node('#execution-attachment').textContent.includes('已保存'));
});

test('restored unsaved form reports current page readiness without claiming saved draft',()=>{
 const c=render({status:'needs_attention',phase:'review',verified:1,attachment_verified:true,saved:false,confirmed_materials:{preserve_unsaved_page:true,attachment:{name:'fictional.pdf'},rows:[{value:'虚构姓名'}]}});
 assert.equal(c.node('#execution-title').textContent,'资料已填好，请在当前官网提交');
 assert(c.node('#execution-counts').textContent.includes('请勿刷新'));
 assert(c.node('#execution-attachment').textContent.includes('所选原件已上传至当前官网'));
 assert(!c.steps[2].classes.has('done'));
});
