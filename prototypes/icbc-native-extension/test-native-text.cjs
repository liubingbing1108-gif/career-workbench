const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
function fixture(){
 const url='https://example.com/apply',marker='00000000-0000-4000-8000-000000000001',state={url,committed:'',injections:[]};let listener;
 class Input {constructor(){this._value='';this.type='text';this.disabled=false;this.readOnly=false;}get value(){return this._value;}set value(v){this._value=v;}getAttribute(){return marker;}focus(){}select(){state.selected=true;}blur(){}dispatchEvent(e){if(e.type==='input')state.committed=this.value;}}
 const input=new Input(),nodes=[input];
 const chrome={runtime:{id:'fixture-extension',onMessage:{addListener(fn){listener=fn;}}},tabs:{get:async()=>({url:state.url})},scripting:{executeScript:async args=>{state.injections.push(args);return [{result:args.func(...args.args)}];}}};
 class E {constructor(type,properties){this.type=type;Object.assign(this,properties);}}
 const context=vm.createContext({window:{},chrome,crypto:{randomUUID:()=>marker},URL,Error,location:{href:url},document:{querySelectorAll:s=>s==='*'?[]:nodes},HTMLInputElement:Input,HTMLTextAreaElement:class{},InputEvent:E,Event:E,KeyboardEvent:E});
 vm.runInContext(fs.readFileSync(__dirname+'/client.js','utf8'),context);const client=new context.window.JobFillClient(42);client.activeUrl=url;
 const message={type:'jobfill:native-text',channel:marker,marker,value:'fictional major',blur:true,url};
 const sender={id:'fixture-extension',tab:{id:42},frameId:0};
 const send=(m=message,s=sender)=>new Promise(resolve=>listener(m,s,resolve));
 return {state,input,nodes,send,message,sender,document:context.document};
}
test('native input events commit the confirmed text through a fixed MAIN-world helper',async()=>{const f=fixture(),r=await f.send();assert.equal(r.ok,true);assert.equal(f.state.committed,'fictional major');assert.equal(f.state.injections[0].world,'MAIN');assert.equal(f.state.injections[0].target.tabId,42);});
test('browser editing inserts only the confirmed text with a fixed editing command',async()=>{const f=fixture();f.document.execCommand=(command,ui,value)=>{assert.equal(command,'insertText');assert.equal(ui,false);f.input._value=value;f.input.dispatchEvent({type:'input'});return true;};const r=await f.send();assert.equal(r.result.method,'native-edit');assert.equal(f.state.selected,true);assert.equal(f.state.committed,'fictional major');});
test('another extension, frame, tab or raw selector cannot request native input',async()=>{for(const sender of [{id:'wrong',tab:{id:42},frameId:0},{id:'fixture-extension',tab:{id:43},frameId:0},{id:'fixture-extension',tab:{id:42},frameId:1}]){const f=fixture();assert.equal((await f.send(f.message,sender)).ok,false);assert.equal(f.state.injections.length,0);}const f=fixture();assert.equal((await f.send({...f.message,marker:'[name=password]'})).ok,false);assert.equal(f.state.injections.length,0);});
test('navigation and sensitive or ambiguous controls stop native input',async()=>{const f=fixture();f.state.url='https://example.com/other';assert.equal((await f.send()).ok,false);assert.equal(f.state.injections.length,0);const g=fixture();g.input.type='password';assert.equal((await g.send()).ok,false);assert.equal(g.state.committed,'');const h=fixture();h.nodes.push(h.input);assert.equal((await h.send()).ok,false);assert.equal(h.state.committed,'');});
