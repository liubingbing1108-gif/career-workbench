"""Decision-first preparation using the existing scoped material/versions engine."""
import copy
import hashlib
import json
from urllib.parse import urlsplit, urlunsplit
from lab import LabError, find, uid


class Preparation:
    def __init__(self, lab, application):
        self.lab, self.application = lab, application

    def open_target(self, url, title="", job_id=None, requires_preference=False, source_id=None):
        try:
            parsed = urlsplit(url.strip())
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError()
            url = urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, parsed.fragment))
        except (AttributeError, ValueError):
            raise LabError("请粘贴有效的 HTTPS 招聘申请链接")
        if len(url) > 3000 or not isinstance(title, str) or len(title) > 300:
            raise LabError("链接或岗位名称过长")
        if job_id and source_id:
            raise LabError("岗位与只读来源不能共用准备记录")
        if any(value is not None and (not isinstance(value, str) or not value or len(value) > 200) for value in (job_id, source_id)):
            raise LabError("岗位或来源标识无效")
        def save(state):
            # A URL is a destination, not the identity of an independent job.
            existing = next((s for s in state["sessions"]
                if (s.get("website") or s.get("target") or s.get("form_analysis") or {}).get("url") == url
                and s.get("management_job_id") == job_id and s.get("source_candidate_id") == source_id), None)
            if existing:
                if requires_preference:
                    existing['manual_reason'] = '该岗位需要选择志愿，请到官网人工申请。'
                return existing
            session = dict(id=uid("session"), name=title or parsed.hostname, overrides={}, selected_versions={}, target={"url": url, "title": title or parsed.hostname}, preparation={"scan_status":"waiting_browser"})
            if job_id:
                session["management_job_id"] = job_id
            if source_id:
                session["source_candidate_id"] = source_id
            if requires_preference:
                session["manual_reason"] = "该岗位需要选择志愿，请到官网人工申请。"
            state["sessions"].append(session)
            return session
        return self.lab.mutate(save)

    def match(self, session_id):
        session = find(self.lab.state()['sessions'], session_id)
        analysis = session.get('form_analysis')
        if not analysis:
            raise LabError('请先读取真实网站表单')
        fields, facts = [], []
        for section in analysis['sections']:
            members = []
            for field in section['fields']:
                if field['type'] in {'display', 'file', 'consent'}:
                    facts.append(field['label'] + '：' + field.get('note', ''))
                    continue
                item = {'id': field['id'], 'label': field['label'], 'type': field['type'],
                        'required': bool(field.get('required')), 'options': field.get('options', []),
                        'instructions': field.get('note', ''), 'section': section['label']}
                if field.get('max_length'):
                    item['maxLength'] = field['max_length']
                if section['repeatable'] and field['type'] != 'checkbox':
                    members.append(item)
                else:
                    fields.append(item)
            if members:
                fields.append({'id': section['id'], 'label': section['label'], 'collection': True,
                               'required': False, 'children': members, 'instructions': section.get('note', '')})
        return self.application.scan(session_id, {'url': analysis['url'], 'title': analysis['title'],
            'execution': 'external', 'fields': fields, 'page_facts': facts,
            'source': '已读取官网字段，由现有 Codex 理解并匹配资料'})

    def settings(self, session_id, file_id):
        def save(state):
            session = find(state['sessions'], session_id)
            if file_id not in (None, ''):
                find(state['files'], file_id)
            session.setdefault('preparation', {})['attachment_id'] = file_id
            session['preparation'].pop('preview', None)
            return session['preparation']
        return self.lab.mutate(save)

    def view(self, session_id):
        session = find(self.lab.state()['sessions'], session_id)
        prep = session.get('preparation', {})
        return {'attachment_id': prep.get('attachment_id'), 'attachment_decided': 'attachment_id' in prep,
                'preview': prep.get('preview'), 'execution': prep.get('execution'),
                'notes': (session.get('website') or {}).get('preparation_notes', []),
                'scan_status': prep.get('scan_status'), 'scan_error': prep.get('scan_error'), 'browser':prep.get('browser')}

    @staticmethod
    def missing_key(item):
        return '/'.join(str(v or '') for v in (item['website_field']['id'], item.get('entry_id'), item.get('child_id'), item.get('field_id'), item.get('kind')))

    def defer(self, session_id, key, deferred):
        plan = self.application.plan(session_id)
        item = next((i for i in plan['missing'] if self.missing_key(i) == key), None)
        if not item or item['kind'] != 'value' or not item['editable']:
            raise LabError('经历范围或问题含义尚未确定，不能跳过后填写')
        def save(state):
            prep = find(state['sessions'], session_id).setdefault('preparation', {})
            keys = set(prep.get('deferred', []))
            keys.add(key) if deferred else keys.discard(key)
            prep['deferred'] = sorted(keys)
        self.lab.mutate(save)

    def bundle(self, session_id):
        with self.lab.lock:
            plan = self.application.plan(session_id)
            return {'application': plan, 'preparation': {**self.view(session_id), 'current': self.current(session_id, plan)}}

    def current(self, session_id, plan=None):
        plan = plan or self.application.plan(session_id)
        session = plan['session']
        if not session.get('form_analysis') or not plan.get('website'):
            raise LabError('尚未完成资料匹配')
        prep = session.get('preparation', {})
        deferred = set(prep.get('deferred', []))
        entries = {e['id']: e for e in self.lab.state()['entries']}
        tasks, manual = [], []
        if prep.get('scan_status') in ('matching','failed'):
            tasks.append({'key':'schema','label':'官网表单匹配','message':'完成重新匹配后才能核对完整预览并填写'})
        for item in plan['missing']:
            child = next((c for c in item['website_field'].get('children', []) if c['id'] == item.get('child_id')), item['website_field'])
            entry = entries.get(item.get('entry_id'))
            title = ' · '.join(str(v) for v in [entry and (entry['values'].get('school') or entry['values'].get('company')), entry and (entry['values'].get('degree') or entry['values'].get('role')), child['label']] if v)
            task = {'key': self.missing_key(item), 'label': title, 'message': item['message'], 'entry_id': item.get('entry_id'), 'website_id': item['website_field']['id']}
            if task['key'] in deferred and item['kind'] == 'value' and item['editable']:
                manual.append(task)
            elif item['blocking']:
                tasks.append(task)
        if 'attachment_id' not in prep:
            tasks.append({'key': 'attachment', 'label': '简历附件', 'message': '选择附件或明确本次不上传'})
        pending = [i['label'] + '：' + i['message'] for i in tasks]
        rows = []
        for item in plan['automatic'] + plan['decisions']:
            w = item['website_field']
            if w.get('collection'):
                members = item['mapping'].get('members', [])
                records = []
                for entry in item['selected']:
                    values = []
                    for member in members:
                        child = find(w['children'], member['website_id'])
                        key = member.get('field_id') or child['id']
                        unresolved = next((i for i in plan['missing'] if i['website_field']['id'] == w['id'] and i.get('entry_id') == entry['id'] and i.get('child_id') == child['id']), None)
                        values.append({'website_id': child['id'], 'label': child['label'],
                                       'value': '' if unresolved else entry.get('answer_values', {}).get(key, ''),
                                       'pending': bool(unresolved), 'manual': bool(unresolved and self.missing_key(unresolved) in deferred),
                                       'source_ref': {'entry_id': entry['id'], 'field_id': member.get('field_id'),
                                                      'version_id': next((c['selected']['id'] for c in entry.get('answer_choices', []) if c['field']['id'] == member.get('field_id') and c.get('selected')), None)}})
                    records.append({'entry_id': entry['id'], 'values': values})
                rows.append({'website_id': w['id'], 'label': w['label'], 'records': records})
            else:
                rows.append({'website_id': w['id'], 'label': w['label'], 'value': item['value'],
                             'source_ref': {'entry_id': item.get('entry_id'), 'field_id': item['mapping'].get('field_id')}})
                follow_up = w.get('follow_up_when')
                if follow_up and item['value'] == follow_up['value']:
                    rows[-1]['follow_up'] = follow_up['message']
        # Unresolved/optional answers must also be visible; preview never fabricates them.
        for missing in plan['missing']:
            if missing['website_field'].get('collection'):
                continue
            rows.append({'website_id': missing['website_field']['id'], 'label': missing['website_field']['label'],
                         'value': '', 'pending': missing['blocking'], 'manual': self.missing_key(missing) in deferred})
        file_id = prep.get('attachment_id')
        file_meta = find(self.lab.state()['files'], file_id) if file_id else None
        content = {'url': plan['website']['url'], 'title': plan['website']['title'], 'rows': rows,
                   'attachment': {'id': file_meta['id'], 'name': file_meta['name']} if file_meta else None,
                   'pending': pending, 'tasks': tasks, 'manual': manual, 'notes': plan['website'].get('preparation_notes', []),
                   'page_facts': plan['website'].get('page_facts', [])}
        content['digest'] = hashlib.sha256(json.dumps(content, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        return content

    def preview(self, session_id):
        content = self.current(session_id)
        def save(state):
            find(state['sessions'], session_id).setdefault('preparation', {})['preview'] = copy.deepcopy(content)
            return content
        return self.lab.mutate(save)

    def start(self, session_id, digest):
        if find(self.lab.state()['sessions'], session_id).get('manual_reason'):
            raise LabError('该岗位需要选择志愿，请到官网人工申请。')
        content = self.current(session_id)
        prep = find(self.lab.state()['sessions'], session_id).get('preparation', {})
        if not prep.get('preview') or prep['preview']['digest'] != digest or digest != content['digest']:
            raise LabError('材料已变化，请重新查看预览再确认', 409)
        if content['pending']:
            raise LabError('请先处理：' + '；'.join(content['pending']))
        def queue(state):
            if self.current(session_id)['digest'] != digest:
                raise LabError('材料已变化，请重新查看预览再确认', 409)
            session = find(state['sessions'], session_id)
            if any(s['id'] != session_id and
                   (s.get('website') or s.get('target') or {}).get('url') == content['url'] and
                   s.get('preparation', {}).get('execution', {}).get('status') in {'awaiting_executor', 'running'}
                   for s in state['sessions']):
                raise LabError('同一官网有另一个岗位正在填写，请先暂停，再连接本次岗位', 409)
            previous = session['preparation'].get('execution')
            if previous and previous.get('digest') == digest and previous['status'] in {'awaiting_executor', 'running'}:
                return previous
            if previous:
                session['preparation'].setdefault('execution_history',[]).append({k:copy.deepcopy(v) for k,v in previous.items() if k not in {'confirmed_materials','connection'}})
            queued_content={**content,'preserve_unsaved_page':True} if session['preparation'].get('preserve_unsaved_page') else content
            execution = {'id': uid('fill'), 'digest': digest, 'status': 'awaiting_executor',
                         'message': '材料已确认，等待连接官网填写程序；尚未向官网输入。',
                         'confirmed_materials': queued_content, 'filled': 0, 'verified': 0,'saved':False,'attachment_verified':False}
            session['preparation']['execution'] = execution
            return execution
        return self.lab.mutate(queue)

    def verify(self,session_id,after_reopen=False):
        def queue(state):
            session=find(state['sessions'],session_id);prep=session.get('preparation',{});previous=prep.get('execution')
            if not previous or previous.get('status') in ('running','awaiting_executor'):raise LabError('请先完成或暂停本次填写后核对',409)
            content=copy.deepcopy(previous['confirmed_materials'])
            content.update(verification_only=True,after_reopen=after_reopen)
            prep.setdefault('execution_history',[]).append({k:copy.deepcopy(v) for k,v in previous.items() if k not in {'confirmed_materials','connection'}})
            prep['execution']={'id':uid('verify'),'digest':previous['digest'],'status':'awaiting_executor','confirmed_materials':content,'filled':0,'verified':0,'saved':False,'attachment_verified':False,'verification_only':True,'after_reopen':after_reopen,'message':'正在核对当前官网；不填写或重新上传。'}
            return prep['execution']
        return self.lab.mutate(queue)

    def pause(self, session_id):
        def stop(state):
            job = find(state['sessions'], session_id).get('preparation', {}).get('execution')
            if not job or job['status'] not in {'awaiting_executor', 'running'}:
                raise LabError('当前没有正在执行的填写')
            job['stop_requested'] = True
            job['message'] = '正在停止后续动作，官网已填内容保留。'
            if job['status'] == 'awaiting_executor':
                job['status'] = 'paused'
            return job
        return self.lab.mutate(stop)
