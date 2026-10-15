"""User-triggered, browser-observed application progress; no scheduled remote reads."""
import re
import time
import threading
from urllib.parse import urlsplit
from store import Invalid, Conflict, Missing
from official import public_https
from public_jobs import role_key


def scope(url):
    p=urlsplit(public_https(url))
    parts=p.path.strip('/').split('/')
    tenant='/'+'/'.join(parts[:3]) if (p.hostname or '').endswith('mokahr.com') and len(parts)>=3 else '/'+parts[0] if (p.hostname or '').endswith('.jobs.feishu.cn') else ''
    return p.netloc,tenant


class ProgressQueries:
    def __init__(self,store):
        self.store=store;self.tasks={};self.lock=threading.RLock()

    def start(self,jid):
        job=self.store.get(jid)
        if job.get('needs_review') or not job.get('company') or not job.get('role'):
            raise Invalid('请先核对公司和具体岗位，再查询对应投递记录')
        url=job.get('official_url') or job.get('source_url') or job.get('url','')
        public_https(url)
        with self.lock:
            old=self.tasks.get(jid)
            if old and old['revision']==job['revision'] and time.time()-old['started']<100 and old['result']['status']=='running':
                return old
            task={'job_id':jid,'revision':job['revision'],'url':url,'company':job['company'],'role':job['role'],
                  'started':time.time(),'result':{'status':'running','changed':False,'message':'正在连接Chrome，读取官网投递记录…'}}
            self.tasks[jid]=task
            return task

    def status(self,jid):
        self.store.get(jid)
        with self.lock:
            task=self.tasks.get(jid)
            if not task:return {'status':'unavailable','changed':False,'message':'请点击查询，读取官网当前进度。'}
            if task['result']['status']=='running' and time.time()-task['started']>=100:
                task['result']={'status':'unavailable','changed':False,'message':'官网查询未完成，请检查Chrome插件或登录状态后重试；原进度保留。'}
            return task['result']

    def accept(self,task,observation):
        with self.lock:
            if self.tasks.get(task['job_id']) is not task or time.time()-task['started']>=100:
                raise Conflict('本次查询已过期，请重新查询')
            if task['result']['status']!='running':return task['result']
            if not isinstance(observation,dict):raise Invalid('官网进度回报格式无效')
            result={'status':'unavailable','changed':False,'message':'没有找到唯一对应的投递记录，原招聘进度保留。'}
            status=observation.get('status')
            if status=='needs_user':
                result={'status':'needs_user','changed':False,'message':'请在Chrome完成该官网登录或验证码，然后重新点击查询。'}
            elif status=='unavailable':
                result['message']='未能读取官网投递记录，请确认已登录且网站显示本岗位的申请记录；原进度保留。'
            else:
                url=observation.get('url','')
                if scope(url)!=scope(task['url']):raise Invalid('查询页面不属于当前公司的招聘网站')
                rows=observation.get('records',[])
                if not isinstance(rows,list) or len(rows)>50:raise Invalid('官网投递记录格式无效')
                matches=[r for r in rows if isinstance(r,dict) and role_key(re.sub(r'^第\s*\d+\s*志愿\s*','',r.get('role','')))==role_key(task['role'])]
                if len(matches)==1:
                    stage=matches[0].get('stage','')
                    # These are actual short website labels; do not invent interview rounds.
                    if not isinstance(stage,str) or not 1<=len(stage)<=60 or not re.fullmatch(r'[\w\s（）()：:、/·—-]+',stage):raise Invalid('官网招聘进度文本无效')
                    if not re.search(r'筛选|评估|评审|审核|笔试|测评|面试|一面|二面|三面|终面|offer|录用|未通过|不合适|淘汰|结束|终止|撤回|放弃|处理中|待处理|待安排|已投递|已申请|已提交',stage,re.I):raise Invalid('页面未显示可确认的招聘进度')
                    try:result=self.store.apply_progress(task['job_id'],task['revision'],stage,url)
                    except (Conflict,Missing):result={'status':'unavailable','changed':False,'message':'查询期间岗位已修改或删除，未写入过期结果。'}
                elif len(matches)>1:
                    result['message']='官网有多条同名申请，无法确定对应记录，已保留原进度。'
            task['result']=result
            return result
