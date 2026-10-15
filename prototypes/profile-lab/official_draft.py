"""Local recovery copy of supported applicant inputs, never a website save receipt."""
import copy
import hashlib
import json
import re
import time
from lab import LabError, find

SAFE_KINDS = {'text', 'email', 'tel', 'textarea', 'select', 'autocomplete', 'radio', 'multiselect', 'date', 'month', 'year', 'number'}

def save_official_draft(lab, sid, url, data):
    fields = data.get('fields')
    if not isinstance(fields, list) or len(fields) > 500:
        raise LabError('官网草稿字段无效')
    cleaned = []
    for f in fields:
        if not isinstance(f, dict) or f.get('kind') not in SAFE_KINDS or f.get('disabled') or re.search(r'密码|验证码|协议|声明|登录|密钥|令牌|password|captcha|consent|login|secret|token|otp', str(f.get('label', '')), re.I):
            continue
        value=f.get('currentValue')
        valid_value=isinstance(value,str) and len(value)<=40000 or f['kind']=='multiselect' and isinstance(value,list) and len(value)<=100 and all(isinstance(v,str) and len(v)<=500 for v in value)
        if not valid_value or not all(isinstance(f.get(k), str) and len(f[k]) <= limit for k,limit in [('fieldId',500),('label',300),('section',300),('sectionId',500)]):
            raise LabError('官网草稿内容无效')
        if not isinstance(f.get('record', -1), int) or not -1 <= f.get('record', -1) < 100:
            raise LabError('官网草稿条目无效')
        cleaned.append({k: f.get(k) for k in ('fieldId','label','section','sectionId','record','kind','currentValue')})
    if sum(len(json.dumps(f['currentValue'],ensure_ascii=False)) for f in cleaned) > 200000:
        raise LabError('官网草稿过大')
    def save(state):
        prep = find(state['sessions'], sid).setdefault('preparation', {})
        draft = prep.setdefault('official_draft', {'url':url, 'fields':[]})
        if draft['url'] != url:
            raise LabError('草稿与官网不一致',409)
        def identity(f):return (f['section'],f['record'],f['label'])
        # Duplicate labels cannot be replayed reliably; retain no ambiguous values.
        counts = {identity(f):sum(identity(g)==identity(f) for g in cleaned) for f in cleaned}
        rows = {identity(f):f for f in draft['fields']}
        changed = False
        for f in cleaned:
            key = identity(f)
            if counts[key] != 1:continue
            if data.get('initial') and key in rows:continue
            if key not in rows and not f['currentValue']:continue
            if rows.get(key) != f:rows[key]=f;changed=True
        if changed:
            draft.update(fields=list(rows.values()), saved_at=time.time())
        return {'saved_at':draft.get('saved_at'), 'count':len(draft['fields']), 'local_only':True}
    return lab.mutate(save)

def restore_content(lab, sid):
    session=find(lab.state()['sessions'],sid);prep=session.get('preparation',{});draft=prep.get('official_draft')
    url=(session.get('website') or session.get('target') or {}).get('url')
    if not draft or not draft['fields'] or draft['url']!=url:
        raise LabError('没有可恢复的本岗位官网草稿')
    rows=[];groups={}
    for f in draft['fields']:
        if f['record'] < 0:
            rows.append({'website_id':f['fieldId'],'label':f['label'],'value':f['currentValue']})
        else:
            key=(f['sectionId'],f['section'])
            groups.setdefault(key,{}).setdefault(f['record'],[]).append({'website_id':re.sub(r'\[\d+\]','[]',f['fieldId']),'label':f['label'],'value':f['currentValue']})
    for (sid_,label),records in groups.items():
        if sorted(records)!=list(range(max(records)+1)):
            raise LabError('草稿经历条目不完整，请核对官网后再恢复')
        rows.append({'website_id':sid_,'label':label,'records':[{'values':records[i]} for i in sorted(records)]})
    file_id=prep.get('attachment_id');meta=find(lab.state()['files'],file_id) if file_id else None
    content={'url':url,'title':session.get('name','本次申请'),'rows':rows,'attachment':{'id':meta['id'],'name':meta['name']} if meta else None,
             'pending':[],'tasks':[],'manual':[],'notes':['本机恢复副本；最终提交由本人完成。只恢复已预览的字段，附件使用本岗位所选原件。'], 'preserve_unsaved_page':True, 'source':'official_draft'}
    content['digest']=hashlib.sha256(json.dumps(content,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    return copy.deepcopy(content)
