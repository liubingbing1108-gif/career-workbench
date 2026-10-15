"""Inspect supplied destinations before discovery; public job data only."""
import json
import re
from urllib.parse import urlsplit, urlunsplit, parse_qs
from urllib.request import Request, build_opener
from intake import public_url, Redirect
from public_jobs import role_key, location_key
from store import Invalid


def classify(url):
    p = urlsplit(url); path = (p.path+'/'+p.fragment.split('?')[0].lstrip('/')).lower()
    if any(p.hostname==h or (p.hostname or '').endswith('.'+h) for h in ('mp.weixin.qq.com','nowcoder.com','niuqizp.com')):
        return 'recruitment_info'
    if re.search(r'/(?:candidatehome/resume|resume/(?:edit|fill)|application/(?:edit|fill))(?:/|$)',path):
        return 'application_form'
    if re.search(r'/(?:resume/[^/]+/apply|form|apply|application)(?:/|$)',path):
        return 'application_form'
    if re.search(r'/(?:position|job|campus|social)/(?:detail|[0-9a-f-]{8,})(?:/|$)',path) or any(k.lower() in {'jobadid','jobid','positionid'} for k in parse_qs(p.query)):
        return 'job_detail'
    return None


def feishu_identity(url):
    p = urlsplit(url)
    if p.scheme != 'https' or not re.fullmatch(r'[a-z0-9-]+\.jobs\.feishu\.cn',p.hostname or '') or p.username or p.password or p.port not in (None,443): return None
    match = re.fullmatch(r'/([^/]+)/(?:resume/(\d{10,25})/apply|position/detail/(\d{10,25}))/?',p.path)
    if not match: return None
    return p, match[1], match[2] or match[3]


def job_json(url):
    if not re.fullmatch(r'/api/v1/job/posts/\d{10,25}',urlsplit(url).path): raise Invalid('仅允许读取公开岗位详情')
    req = Request(public_url(url),headers={'Accept':'application/json','User-Agent':'CareerSpace/1.0 (public job preview)'})
    with build_opener(Redirect()).open(req,timeout=8) as response:
        raw = response.read(1_000_001)
        if len(raw)>1_000_000: raise Invalid('公开岗位数据过大')
        return json.loads(raw)


def company_key(value):
    # Ignore a legal-name suffix only. Never accept arbitrary substring matches.
    return re.sub(r'(?:有限责任公司|股份有限公司|有限公司|公司)$','',re.sub(r'\s+','',value or ''))


class DirectEntry:
    def __init__(self,reader,request=job_json): self.reader,self.request=reader,request

    def inspect(self,job):
        source = job.get('source_url') or job.get('url','')
        identity = feishu_identity(source)
        if not identity: return None
        p,site,jid = identity
        origin = urlunsplit((p.scheme,p.netloc,'','',''))
        public = origin+'/'+site+'/position/detail/'+jid
        try:
            page = self.reader(public)
            meta = page.get('metadata',{})
            tenant = meta.get('tenant_name','')
            if company_key(tenant)!=company_key(job['company']) or meta.get('website_path')!=site:
                return {'status':'needs_review','candidates':[],'reason':'company_mismatch','message':'该链接的招聘主体与管理中的公司不一致，尚未读取或发送个人材料。请核对来源链接和公司。'}
            detail = self.request(origin+'/api/v1/job/posts/'+jid)
            data = detail.get('data',{}).get('job_post_detail',{})
            if detail.get('code')!=0 or str(data.get('id'))!=jid or not data.get('title'):
                raise Invalid('官网未返回该链接对应的岗位，可能已下线或暂时不可读取')
            if data.get('channel_online_status')!=1: raise Invalid('该链接对应的岗位已停止招聘')
            title = data['title']; locations = [x.get('name','') for x in data.get('city_list',[])]
            company_url = next((u for u in page.get('links',[]) if urlsplit(u).scheme=='https' and urlsplit(u).hostname and not urlsplit(u).hostname.endswith('feishu.cn')),origin+'/'+site+'/')
            entry = {'company':job['company'],'role':job['role'],'official_role':title,'location':'、'.join(locations),
                     'url':public,'application_url':origin+'/'+site+'/resume/'+jid+'/apply',
                     'company_url':company_url,'recruitment_url':origin+'/'+site+'/',
                     'verification':'public_pages','verification_method':'ats_tenant_and_public_job','job_id':jid,
                     'evidence':[{'url':origin+'/'+site+'/','quote':tenant},{'url':public,'quote':title}]}
            if role_key(title)!=role_key(job['role']) or job.get('location') and location_key(job['location']) not in [location_key(x) for x in locations]:
                return {'status':'identity_mismatch','candidates':[entry],'reason':'role_mismatch','message':'此申请链接对应“'+title+'”（'+entry['location']+'），与你录入的“'+job['role']+'”不同。请确认是采用此官网岗位，还是保留原岗位另查入口。'}
            return {'status':'ready','entry':entry}
        except Exception as error:
            return {'status':'needs_review','candidates':[],'reason':'direct_unreadable','message':('已识别具体申请链接，直接核对未完成：'+str(error)) if isinstance(error,Invalid) else '已识别具体申请链接，但官网岗位信息暂未读取到。原链接和登录现场已保留；请重试直接核对。'}
