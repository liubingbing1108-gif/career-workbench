"""One resumable public lookup per management revision, independent of UI navigation."""
import threading
import time
from store import Conflict, Missing, Invalid

class ResolutionTasks:
    def __init__(self,store,lookup):
        self.store,self.lookup=store,lookup
        self.lock=threading.RLock();self.tasks={}
        self.slots=threading.BoundedSemaphore(3)

    def status(self,jid,start=False,retry=False):
        job=self.store.get(jid);key=(jid,job['revision'])
        with self.lock:
            task=self.tasks.get(key)
            if start and (not task or retry and task.get('result') is not None):
                task={'started':time.monotonic(),'stage':'正在检查投递链接','message':'先检查已提供页面；资讯和招聘首页再查具体岗位。','result':None}
                # Keep only one current revision per job and bounded completed tasks.
                self.tasks={k:v for k,v in self.tasks.items() if k[0]!=jid and (v['result'] is None or time.monotonic()-v['started']<300)}
                self.tasks[key]=task
                threading.Thread(target=self.run,args=(job,key,task),daemon=True).start()
            if not task:
                if job.get('official_url_status')=='verified':
                    return {'status':'ready','entry':job['official_entry'],'job':job}
                return {'status':'unavailable','message':'查找已结束或岗位已修改，请重新开始。','candidates':[]}
            return task['result'] or {'status':'resolving','stage':task['stage'],'message':task['message'],'elapsed':time.monotonic()-task['started']}

    def choose(self,jid,url,confirm_role=False):
        job=self.store.get(jid)
        with self.lock:
            task=self.tasks.get((jid,job['revision']))
            result=task and task['result']
            entries=result.get('candidates',[]) if result and result.get('status') in ('needs_selection','identity_mismatch') else []
            entry=next((e for e in entries if e['url']==url and e.get('verification')=='public_pages'),None)
            if not entry:raise Invalid('候选已失效或尚未核验，请重新查找。')
            if result['status']=='identity_mismatch':
                if confirm_role is not True:raise Invalid('请明确确认采用该官网岗位名称，不自动替换原岗位。')
                job=self.store.update(jid,job['revision'],{'role':entry['official_role'],'location':entry['location']},None)
                entry={**entry,'role':job['role']}
            saved=self.store.set_official(jid,job['revision'],entry)
            task['result']={'status':'ready','entry':entry,'job':saved}
            self.tasks[(jid,saved['revision'])]=task
            return task['result']

    def inspection_job(self,jid):
        job=self.store.get(jid)
        with self.lock:
            task=self.tasks.get((jid,job['revision']))
            if not task or (task.get('result') or {}).get('status')!='needs_inspection':raise Invalid('页面核对请求已结束，请重新开始')
        return job

    def observe(self,jid,revision,observation):
        job=self.store.get(jid)
        if job['revision']!=revision:raise Conflict('岗位已修改，未采用旧页面核对')
        with self.lock:
            task=self.tasks.get((jid,revision))
            if not task or (task.get('result') or {}).get('status')!='needs_inspection':raise Invalid('页面核对请求已失效')
        result=self.lookup().inspect_browser(job,observation)
        if result['status']=='ready':result['job']=self.store.set_official(jid,revision,result['entry'])
        with self.lock:
            task['result']=result
            if result.get('job'):self.tasks[(jid,result['job']['revision'])]=task
        return result

    def run(self,job,key,task):
        def progress(stage,message):
            with self.lock:task.update(stage=stage,message=message)
        try:
            with self.slots:
                result=self.lookup().lookup(job,progress=progress)
            if result['status']=='ready':
                current=self.store.get(job['id'])
                if current['revision']!=job['revision']:raise Conflict('岗位已修改，请按新信息重新查找。')
                result['job']=current if current.get('official_url_status')=='verified' and current.get('official_url')==result['entry']['url'] else self.store.set_official(job['id'],job['revision'],result['entry'])
                # Saving increments revision. Polls must find the same completed task.
                with self.lock:self.tasks[(job['id'],result['job']['revision'])]=task
        except (Conflict,Missing):result={'status':'unavailable','candidates':[],'message':'岗位已修改或删除，本次查找已停止。请返回管理重新开始。'}
        except Exception:result={'status':'unavailable','candidates':[],'message':'官网查找发生错误，请重试；资料与来源链接已保留。'}
        with self.lock:task['result']=result
