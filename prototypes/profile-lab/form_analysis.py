"""Store a read-only website analysis separately from answers and fill plans."""
import copy
from urllib.parse import urlsplit
from lab import LabError, find, uid


def validate_analysis(raw):
    if not isinstance(raw, dict) or raw.get('schema_version') != 1:
        raise LabError('表单解析格式无效')
    allowed = {'schema_version','url','title','scanned_at','source','sections','attention','limits'}
    if set(raw) - allowed:
        raise LabError('字段解析不能包含答案、执行计划或额外数据')
    url = urlsplit(raw.get('url',''))
    if url.scheme != 'https' or not url.hostname or url.username or url.password:
        raise LabError('需要有效的 HTTPS 招聘链接')
    for key in ('url','title','scanned_at','source'):
        if not isinstance(raw.get(key),str) or not raw[key] or len(raw[key])>3000:
            raise LabError('解析说明不完整')
    sections=raw.get('sections')
    if not isinstance(sections,list) or not 1<=len(sections)<=50:
        raise LabError('表单区块数量无效')
    ids=set()
    for s in sections:
        if set(s)-{'id','label','repeatable','record_count','can_add','fields','note'}:
            raise LabError('区块包含未支持的数据')
        if not all(isinstance(s.get(k),str) and s[k] for k in ('id','label')):
            raise LabError('区块缺少标识或名称')
        if type(s.get('repeatable')) is not bool or type(s.get('can_add')) is not bool or type(s.get('record_count')) is not int or not 0<=s['record_count']<=200:
            raise LabError('区块条数或新增能力无效')
        if not isinstance(s.get('fields'),list) or len(s['fields'])>100:
            raise LabError('字段清单无效')
        for f in s['fields']:
            if set(f)-{'id','label','type','required','note','max_length','options','executor_field_ids'}:
                raise LabError('字段清单不能保存网页已有答案')
            if not all(isinstance(f.get(k),str) and f[k] for k in ('id','label','type')) or f['id'] in ids:
                raise LabError('字段标识无效或重复')
            ids.add(f['id'])
            if f.get('required') is not None and type(f['required']) is not bool:
                raise LabError('必填标记无效')
            for key in ('options','executor_field_ids'):
                if not isinstance(f.get(key,[]),list) or any(not isinstance(v,str) for v in f.get(key,[])):
                    raise LabError('字段选项或执行器标识无效')
    if not isinstance(raw.get('limits',[]),list) or any(not isinstance(v,str) for v in raw.get('limits',[])):
        raise LabError('扫描范围说明无效')
    for item in raw.get('attention',[]):
        if set(item)!={'title','detail','kind'} or not all(isinstance(v,str) for v in item.values()):
            raise LabError('待处理说明无效')
    return copy.deepcopy(raw)


def save_analysis(lab, raw, session_id=None):
    analysis=validate_analysis(raw)
    def save(state):
        if session_id:
            session=find(state['sessions'],session_id)
            if session.get('website'):
                raise LabError('已有材料方案的投递不能被字段解析覆盖，请新建投递',409)
        else:
            session=dict(id=uid('session'),name=analysis['title'][:80],overrides={},selected_versions={})
            state['sessions'].append(session)
        session['form_analysis']=analysis
        return session
    return lab.mutate(save)
