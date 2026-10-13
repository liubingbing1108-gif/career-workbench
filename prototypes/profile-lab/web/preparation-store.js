/* Serialize per-application edits. Keep the latest intent for each control;
   a slow response may acknowledge storage but never repaint a newer choice. */
class PreparationSaveQueue {
  constructor(send, read, changed, applied) {
    Object.assign(this,{send,read,changed,applied});this.sessions=new Map();
  }
  state(id){if(!this.sessions.has(id))this.sessions.set(id,{pending:new Map(),running:false,error:'',revision:0});return this.sessions.get(id);}
  enqueue(id,key,path,body){const s=this.state(id);s.pending.set(key,{path,body});s.revision++;s.error='';this.changed(id);void this.drain(id);}
  async drain(id){
    const s=this.state(id);if(s.running||s.error||!s.pending.size)return;s.running=true;
    try{
      while(s.pending.size){
        const [key,edit]=s.pending.entries().next().value;s.pending.delete(key);
        try{if(edit.path)await this.send(edit.path,{...edit.body,session_id:id});}
        catch(error){if(!s.pending.has(key))s.pending.set(key,edit);throw error;}
      }
      const revision=s.revision,bundle=await this.read(id);
      if(revision===s.revision)this.applied(id,bundle);
    }catch(error){s.error=error.message||'保存失败';}
    finally{s.running=false;this.changed(id);if(!s.error&&s.pending.size)void this.drain(id);}
  }
  busy(id){const s=this.state(id);return s.running||s.pending.size>0||!!s.error;}
  retry(id){const s=this.state(id);s.error='';if(!s.pending.size)s.pending.set('retry-read',{path:null,body:{}});this.changed(id);void this.drain(id);}
}
if(typeof module!=='undefined')module.exports={PreparationSaveQueue};
