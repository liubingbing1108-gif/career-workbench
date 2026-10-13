"""Read-only adapter for the public Zhiye 2022 portal API (no cookies/login/forms)."""
import json
import re
from urllib.request import Request, build_opener
from urllib.parse import urlsplit, urlunsplit, urlencode, parse_qs
from intake import public_url, Redirect
from store import Invalid


def request_json(url,body=None):
    # This adapter calls only the two public job-read operations used by the site.
    if urlsplit(url).path not in ('/api/JobAd/GetJobAdInfo','/api/Jobad/GetJobAdPageList'):
        raise Invalid('只允许公开职位查询接口')
    req=Request(public_url(url),data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'CareerSpace/1.0 (public job preview)'})
    with build_opener(Redirect()).open(req,timeout=12) as res:
        raw=res.read(1_000_001)
        if len(raw)>1_000_000:raise Invalid('公开岗位数据过大')
        data=json.loads(raw)
    if data.get('Code')!=200:raise Invalid('官网职位接口暂时不可用')
    return data


def role_key(value):
    value=re.sub(r'\s+','',value or '')
    value=re.sub(r'[（(]J\d+[）)]$','',value,flags=re.I)
    value=re.sub(r'^[【\[]?(?:(?:20)?\d{2}届?)?(?:校园招聘|校招)[】\]]?[-—·:：]*','',value)
    return value


def location_key(value):return (value or '').strip().removesuffix('市')


def job_id(url):
    return next(iter(parse_qs(urlsplit(url).query).get('jobAdId',[])),'')


class ZhiyeJobs:
    def __init__(self,request=request_json):self.request=request
    def supports(self,url):return bool(re.fullmatch(r'[a-z0-9-]+\.zhiye\.com',urlsplit(url).hostname or ''))
    def detail(self,base,jid):
        if not re.fullmatch(r'[a-f0-9-]{36}',jid,re.I):raise Invalid('官网岗位编号无效')
        url=base+'/api/JobAd/GetJobAdInfo?'+urlencode({'jobAdId':jid,'displayFields':json.dumps(['JobAdName','Duty','Require','LocId','Category','Degree'])})
        data=self.request(url)['Data']
        if not isinstance(data,dict) or data.get('Id','').lower()!=jid.lower():raise Invalid('官网返回的岗位编号不一致')
        if data.get('Status')!=1:raise Invalid('该官网岗位已停止招聘')
        return data
    def candidates(self,job,recruitment_url,company_url):
        p=urlsplit(recruitment_url);base=urlunsplit((p.scheme,p.netloc,'','',''))
        if p.scheme!='https' or not self.supports(base):return []
        sources=[job.get('source_url',''),job.get('official_url','')]
        ids=[job_id(u) for u in sources if urlsplit(u).hostname==p.hostname and job_id(u)]
        if ids:
            details=[self.detail(base,ids[0])]
        else:
            data=self.request(base+'/api/Jobad/GetJobAdPageList',{'PageIndex':0,'PageSize':100,'KeyWords':role_key(job['role']),'SpecialType':0,'PortalId':'','DisplayFields':['JobAdName','LocId','Category']})
            rows=data.get('Data') or []
            if not isinstance(rows,list):raise Invalid('官网职位列表格式已变化')
            # Read every exact match; never choose the first match from a list.
            rows=[r for r in rows if role_key(r.get('JobAdName'))==role_key(job['role'])]
            if data.get('Count',0)>100:raise Invalid('匹配岗位过多，请补充具体岗位或地点')
            if len(rows)>20:raise Invalid('同名岗位超过20个，请补充地点或具体岗位名称')
            details=[self.detail(base,r['Id']) for r in rows]
        result=[]
        for data in details:
            if role_key(data.get('JobAdName'))!=role_key(job['role']):continue
            loc='、'.join(data.get('LocNames') or [])
            if job.get('location') and location_key(job['location']) not in [location_key(x) for x in data.get('LocNames',[])]:continue
            year=re.search(r'20(\d{2})',job.get('campaign',''));title_year=re.search(r'^(?:20)?(\d{2})届?',data['JobAdName'])
            if year and title_year and year[1]!=title_year[1]:continue
            category=str(data.get('CategoryId'))
            path={'2':'/campus/detail','1':'/social/detail','3':'/intern/detail'}.get(category)
            if not path:continue
            url=base+path+'?'+urlencode({'jobAdId':data['Id']})
            result.append({'company':job['company'],'role':job['role'],'official_role':data['JobAdName'],'location':loc,
                'company_url':company_url,'recruitment_url':recruitment_url,'url':url,
                'evidence':[{'url':url,'quote':data['JobAdName']}],
                'api_verified':True,'job_id':data['Id']})
        return result
