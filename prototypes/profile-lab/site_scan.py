"""Accept schema-only browser scans, then let the existing model map field meanings."""
from datetime import datetime, timezone
import re
import threading
from lab import LabError, find
from form_analysis import save_analysis


def scan_analysis(snapshot, url):
    if not isinstance(snapshot, dict) or snapshot.get('schemaVersion') != 1 or snapshot.get('page', {}).get('url') != url:
        raise LabError('网页扫描与待投递链接不一致')
    fields, sections = snapshot.get('fields'), snapshot.get('sections')
    if not isinstance(fields, list) or not 1 <= len(fields) <= 500 or not isinstance(sections, list) or len(sections) > 50:
        raise LabError('当前页面未读取到可用表单；请先登录并打开申请表')
    # Generic pages often expose repeated blocks separately, while scalar fields
    # live directly on the page. Keep those fields instead of silently dropping them.
    declared={s.get('sectionId') for s in sections}
    sections=list(sections)+[{'sectionId':sid,'label':'个人信息及其他问题','count':1,'canAdd':False,'non_repeating':True}
                            for sid in dict.fromkeys(f.get('sectionId') for f in fields)
                            if sid not in declared]
    result = []
    seen = set()
    for section in sections:
        sid = section.get('sectionId')
        if not isinstance(sid, str) or not sid or sid in seen:
            raise LabError('网页分区标识无效')
        seen.add(sid)
        members = [f for f in fields if f.get('sectionId') == sid]
        repeated = not section.get('non_repeating') and (bool(section.get('canAdd')) or len({f.get('recordId') for f in members if f.get('recordId')}) > 1)
        flat_keys, counts = {}, {}
        if repeated:
            for f in members:
                key = (f.get('label'), f.get('kind'), f.get('context', {}).get('componentIndex', 0))
                record = f.get('recordId')
                counts[(key, record)] = counts.get((key, record), 0) + 1
                if record:
                    flat_keys.setdefault(key, f.get('fieldId'))
        grouped = {}
        for f in members:
            fid, label = f.get('fieldId'), f.get('label')
            if not isinstance(fid, str) or not fid or not isinstance(label, str) or not label:
                raise LabError('网页字段缺少标识或名称')
            canonical = re.sub(r'\[\d+\]', '[]', fid) if repeated else fid
            if repeated and '[' not in fid and f.get('recordId'):
                key = (label, f.get('kind'), f.get('context', {}).get('componentIndex', 0))
                if all(n == 1 for (k, _), n in counts.items() if k == key):
                    canonical = flat_keys[key]
            if canonical in grouped:
                grouped[canonical]['executor_field_ids'].append(fid)
                continue
            kind = f.get('kind', 'unsupported')
            # Agreement controls always remain a user action, never mapped as profile facts.
            if kind == 'checkbox':
                kind = 'consent'
            if f.get('disabled') or kind == 'unsupported':
                kind = 'display'
            options = f.get('options', {}).get('items', [])
            if not isinstance(options, list) or any(not isinstance(v, str) for v in options):
                raise LabError('网页选项格式无效')
            note = '；'.join(str(v) for v in [f.get('description'), f.get('context', {}).get('placeholder'), f.get('blockedReason')] if v)
            grouped[canonical] = dict(id=canonical, label=label[:300], type=kind, required=bool(f.get('required')),
                                      note=note[:3000], options=options[:500], executor_field_ids=[fid])
            max_length = f.get('constraints', {}).get('maxLength')
            if type(max_length) is int and max_length > 0:
                grouped[canonical]['max_length'] = max_length
        result.append(dict(id=sid,label=str(section.get('label') or sid)[:300], repeatable=repeated,
                           record_count=int(section.get('count') or (1 if members else 0)),can_add=bool(section.get('canAdd')),
                           fields=list(grouped.values()),note=str(section.get('description') or '网站当前可访问的字段；隐藏或后续条件分支需继续读取。')[:3000]))
    return dict(schema_version=1,url=url,title=str(snapshot['page'].get('title') or '本次申请')[:300],
                scanned_at=datetime.now(timezone.utc).isoformat(),source='本人连接的填写扩展只读扫描 '+str(snapshot.get('executorVersion','未知'))[:30],sections=result,attention=[],
                limits=['仅覆盖当前可访问字段；隐藏分支、附件上传及最终提交需按官网实际情况处理。'])


class SiteScan:
    def __init__(self,lab,preparation):
        self.lab,self.preparation=lab,preparation
        self.threads=[]

    def accept(self,url,snapshot,session_id=None):
        analysis=scan_analysis(snapshot,url)
        sessions=[s for s in self.lab.state()['sessions'] if (s.get('target') or s.get('website') or {}).get('url')==url
                  and (session_id is None or s['id']==session_id)]
        if len(sessions)>1:raise LabError('请从本次岗位连接浏览器，不能按链接共用材料',409)
        session=next(iter(sessions),None)
        if not session:raise LabError('未找到对应的待投递链接')
        if session.get('website'):
            # Keep confirmed answers and choices; retain only the fresh schema so
            # newly supported controls can be reconciled through the same mapper.
            info={'executor_version':str(snapshot.get('executorVersion',''))[:30],'client_version':str(snapshot.get('coverageDetails',{}).get('clientRevision',''))[:30],'native_text_ready':snapshot.get('coverageDetails',{}).get('nativeTextBridgeReady') is True}
            self.lab.mutate(lambda state:find(state['sessions'],session['id']).setdefault('preparation',{}).update(latest_analysis=analysis,latest_executor_info=info))
            return {'status':'ready','message':'已有本次材料，保留你的选择；执行前会重新读取官网。'}
        sid=session['id']
        if session.get('preparation',{}).get('scan_status')=='matching':
            return {'status':'matching'}
        save_analysis(self.lab,analysis,sid)
        self.lab.mutate(lambda state:find(state['sessions'],sid).setdefault('preparation',{}).update(scan_status='matching',scan_error=''))
        def match():
            try:
                self.preparation.match(sid)
                self.lab.mutate(lambda state:find(state['sessions'],sid)['preparation'].update(scan_status='ready',scan_error=''))
            except Exception as error:
                def failed(state):
                    remaining=next((s for s in state['sessions'] if s['id']==sid),None)
                    if remaining:remaining['preparation'].update(scan_status='failed',scan_error=str(error)[:500])
                self.lab.mutate(failed)
        thread=threading.Thread(target=match,daemon=True);self.threads.append(thread);thread.start()
        return {'status':'matching','message':'已读取官网，正在匹配资料；完成后工作台自动显示待确认内容。'}
