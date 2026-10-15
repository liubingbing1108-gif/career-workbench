/* Durable local outbox first, then revision-checked per-job storage. Drafts do
   not change shared facts or authorize website filling. */
class AnswerDrafts extends Map {
  constructor(storage, send, changed=()=>{}) {
    super();Object.assign(this,{storage,send,changed,records:new Map(),pending:new Set(),errors:new Map(),running:false,error:''});
    try {for(const [key,row] of JSON.parse(storage.getItem('career-answer-drafts-v1')||'[]')){this.records.set(key,row);this.pending.add(key);if(row.value!==null)super.set(key,row.value);}}
    catch {this.error='浏览器草稿读取失败，请检查本机已保存的草稿';}
  }
  persist(){try{this.storage.setItem('career-answer-drafts-v1',JSON.stringify([...this.pending].map(k=>[k,this.records.get(k)])));}catch{this.error='浏览器暂存失败，请等待本机服务保存后再离开';}}
  hydrate(session, rows={}) {
    for(const [key,row] of Object.entries(rows)){if(this.pending.has(key))continue;this.records.set(key,row);if(row.value===null)super.delete(key);else super.set(key,row.value);}
    for(const key of this.keys())if(key.startsWith(session+'/')&&!rows[key]&&!this.pending.has(key))super.delete(key);
    if(this.pending.size)void this.flush();
  }
  set(key,value){this.records.set(key,{value,revision:this.records.get(key)?.revision||0});super.set(key,value);this.pending.add(key);this.persist();this.changed();void this.flush();return this;}
  delete(key){if(!this.has(key)&&!this.records.has(key))return false;this.records.set(key,{value:null,revision:this.records.get(key)?.revision||0});const result=super.delete(key);this.pending.add(key);this.persist();this.changed();void this.flush();return result;}
  async flush(){
    if(this.running)return;this.running=true;this.error='';this.changed();
    const failed=new Set();
    try{while([...this.pending].some(k=>!failed.has(k))){const key=[...this.pending].find(k=>!failed.has(k)),row={...this.records.get(key)};
      try{
        const saved=await this.send('/api/preparation/draft',{session_id:key.split('/')[0],key,...row});
        const current=this.records.get(key);if(!current)continue;current.revision=saved.revision;this.errors.delete(key);
        if(current.value===row.value)this.pending.delete(key);
      }catch(error){if(this.records.has(key)){this.errors.set(key,error.message||'草稿保存失败');failed.add(key);}}
      this.persist();
    }}catch(error){this.error=error.message||'草稿保存失败';}
    finally{this.running=false;this.changed();}
  }
  status(session){return {pending:[...this.pending].some(k=>k.startsWith(session+'/')),error:this.error||[...this.errors].filter(([k])=>k.startsWith(session+'/')).map(([,e])=>e).join('；')};}
  async retry(session){
    if(this.running)return;
    const latest=await this.send('/api/preparation?session='+encodeURIComponent(session));
    for(const key of this.pending)if(key.startsWith(session+'/'))this.records.get(key).revision=latest.drafts?.[key]?.revision||0;
    this.persist();await this.flush();
  }
  async settled(session){while(this.running)await new Promise(resolve=>setTimeout(resolve,10));const status=session?this.status(session):{pending:this.pending.size,error:this.error||[...this.errors.values()].join('；')};if(status.pending||status.error)throw Error(status.error||'草稿尚未保存，请重试');}
  forgetSessions(ids){for(const key of this.records.keys())if(ids.includes(key.split('/')[0])){this.records.delete(key);this.pending.delete(key);this.errors.delete(key);super.delete(key);}this.persist();this.error='';}
}
if(typeof module!=='undefined')module.exports={AnswerDrafts};
