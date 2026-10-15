"""Loopback handoff to a user-opened extension page; never executes browser code here."""
import copy
import base64
import mimetypes
import re
import secrets
import time
from urllib.parse import urlsplit,parse_qs
from lab import LabError


class ExecutorBridge:
    def __init__(self, lab, scan_receiver=None):
        self.lab = lab
        self.scan_receiver = scan_receiver
        self.code = secrets.token_urlsafe(18)
        self.code_session_id = None
        self.codes = {}
        self.connections = {}
        # A restarted process cannot prove which browser still owns an old active task.
        if any(s.get('preparation', {}).get('execution', {}).get('status') in {'running', 'awaiting_executor'} for s in lab.state()['sessions']):
            def recover(state):
                for session in state['sessions']:
                    job = session.get('preparation', {}).get('execution')
                    if job and job['status'] in {'running', 'awaiting_executor'}:
                        job.update(status='paused', stop_requested=True, message='本机服务已重启，旧任务已暂停；请重新连接并核对预览后继续，官网已填内容保留。')
            lab.mutate(recover)

    @staticmethod
    def allowed_origin(origin):
        return bool(re.fullmatch(r'chrome-extension://[a-p]{32}', origin or ''))

    def setup(self, session_id=None):
        with self.lab.lock:
            if session_id is not None and not any(s['id'] == session_id for s in self.lab.state()['sessions']):
                raise LabError('该准备记录已删除或不存在', 404)
            self.code = secrets.token_urlsafe(18)
            self.code_session_id = session_id
            self.codes = {k:v for k,v in self.codes.items() if time.time()-v[1]<300}
            self.codes[self.code] = (session_id,time.time())
            return {'code': self.code}

    def status(self, url, session_id=None):
        stale = {token for token, c in self.connections.items() if time.time()-c['seen'] >= 30}
        if stale:
            def expire(state):
                for session in state['sessions']:
                    job = session.get('preparation', {}).get('execution')
                    if job and job['status'] == 'running' and job.get('connection') in stale:
                        job.update(status='failed', message='填写连接已中断；官网可能保留部分输入，请重新连接、预览并检查实际现场。')
            self.lab.mutate(expire)
        active = any(c['url'] == url and (session_id is None or c['session_id'] == session_id)
                     and time.time()-c['seen'] < 20 for c in self.connections.values())
        return {'connected': active}

    def call(self, action, origin, data):
        if not self.allowed_origin(origin):
            raise LabError('仅接受本人打开的已配对浏览器扩展', 403)
        with self.lab.lock:
            if action == 'connect':
                code = data.get('code')
                scoped = self.codes.get(code) if isinstance(code,str) else None
                if not isinstance(code, str) or not (secrets.compare_digest(code, self.code) or scoped and time.time()-scoped[1]<300):
                    raise LabError('连接码已失效，请从工作台重新复制', 403)
                code_session_id = scoped[0] if scoped else self.code_session_id
                url = data.get('url', '')
                self.status(url)
                # A verified public Phoenix role may lead to its own form after
                # login. Bind it to this job only; never adopt another jobAdId.
                if code_session_id:
                    owner=next((s for s in self.lab.state()['sessions'] if s['id']==code_session_id),None)
                    old=(owner.get('website') or owner.get('target') or {}).get('url','') if owner else ''
                    a,b=urlsplit(url),urlsplit(old);identity=parse_qs(b.query).get('jobAdId')
                    if owner and owner.get('management_job_id') and not owner.get('website') and url!=old and identity and a.scheme==b.scheme=='https' and a.netloc==b.netloc and a.path=='/form' and parse_qs(a.query).get('jobAdId')==identity and not a.username and not a.password:
                        def adopt(state):
                            session=next(s for s in state['sessions'] if s['id']==code_session_id)
                            session['target'].setdefault('public_url',old);session['target']['url']=url
                        self.lab.mutate(adopt)
                candidates = [s for s in self.lab.state()['sessions'] if
                    (s.get('website') or s.get('target') or {}).get('url') == url and
                    (code_session_id is None or s['id'] == code_session_id)]
                if not candidates:
                    raise LabError('当前官网与待投递链接不一致')
                if len(candidates) != 1:
                    raise LabError('同一链接有多个岗位，请从本次岗位重新复制连接码', 409)
                session_id = candidates[0]['id']
                if any(s.get('preparation', {}).get('execution', {}).get('status') == 'running' and (s.get('website') or s.get('target') or {}).get('url') == url for s in self.lab.state()['sessions']):
                    raise LabError('当前官网正在填写，请先暂停再更换连接', 409)
                self.connections = {k: c for k, c in self.connections.items() if c['url'] != url}
                token = secrets.token_urlsafe(24)
                self.connections[token] = dict(origin=origin, url=url, session_id=session_id, seen=time.time())
                self.code = secrets.token_urlsafe(18)
                self.code_session_id = None
                self.codes.pop(code,None)
                return {'connection': token, 'message': '已连接；只有材料预览确认后才会填写。'}
            connection = self.connections.get(data.get('connection', ''))
            if not connection or connection['origin'] != origin:
                raise LabError('填写连接无效，请重新连接', 403)
            if data.get('url') != connection['url']:
                raise LabError('官网已切换，停止接收材料', 409)
            connection['seen'] = time.time()
            if not any(s['id'] == connection['session_id'] for s in self.lab.state()['sessions']):
                if action in {'poll', 'report'}:
                    return {'job': None, 'accepted': False, 'stop': True, 'message': '该岗位已删除，后续填写已停止；官网已填内容保留。'}
                raise LabError('该准备记录已删除，连接已停止', 409)
            if action == 'scan':
                if not self.scan_receiver:
                    raise LabError('扫描接收未启用', 503)
                return self.scan_receiver(connection['url'], data.get('snapshot'), connection['session_id'])
            if action == 'draft':
                from official_draft import save_official_draft
                return save_official_draft(self.lab, connection['session_id'], connection['url'], data)
            if action == 'poll':
                def take(state):
                    for session in state['sessions']:
                        if session['id'] != connection['session_id']:
                            continue
                        job = session.get('preparation', {}).get('execution')
                        if not job or job['status'] != 'awaiting_executor' or job['confirmed_materials']['url'] != connection['url']:
                            continue
                        job.update(status='running', connection=data['connection'], message='已连接，正在重新读取官网并准备填写。')
                        materials=copy.deepcopy(job['confirmed_materials'])
                        attachment=materials.get('attachment')
                        if attachment and not materials.get('verification_only'):
                            meta,raw=self.lab.file_bytes(attachment['id'])
                            if meta['name']!=attachment['name']:
                                raise LabError('所选附件已变化，请重新检查预览',409)
                            attachment.update(base64=base64.b64encode(raw).decode(),mime_type=mimetypes.guess_type(meta['name'])[0] or 'application/octet-stream')
                        return {'id': job['id'], 'materials': materials}
                    return None
                return {'job': self.lab.mutate(take)}
            if action == 'report':
                def report(state):
                    job = next((s.get('preparation', {}).get('execution') for s in state['sessions']
                                if s['id'] == connection['session_id'] and s.get('preparation', {}).get('execution', {}).get('id') == data.get('job_id')), None)
                    if not job or job.get('connection') != data['connection'] or job['status'] not in {'running'}:
                        raise LabError('执行任务不匹配或已结束', 409)
                    status = data.get('status')
                    if status not in {'running', 'needs_attention', 'complete', 'failed', 'paused'}:
                        raise LabError('执行状态无效')
                    for key in ('filled', 'verified'):
                        if type(data.get(key)) is not int or not 0 <= data[key] <= 500:
                            raise LabError('回读数量无效')
                    if not isinstance(data.get('message'), str) or len(data['message']) > 2000:
                        raise LabError('执行说明无效')
                    issues = data.get('issues', [])
                    if not isinstance(issues, list) or any(not isinstance(i, str) or len(i) > 1000 for i in issues) or len(issues) > 500:
                        raise LabError('执行问题格式无效')
                    manual = [i['label'] + '：已选择由本人在官网填写' for i in job['confirmed_materials'].get('manual', [])]
                    skipped = [i['label'] + '：本次留空或跳过，可在官网补充' for i in job['confirmed_materials'].get('skipped', [])]
                    issues = list(dict.fromkeys(issues + manual + skipped))
                    if (manual or skipped) and status == 'complete':
                        status = 'needs_attention'
                    flags={key:data.get(key,False) for key in ('saved','attachment_verified','save_acknowledged','persistence_verified','draft_supported')}
                    if any(type(value) is not bool for value in flags.values()):raise LabError('保存或附件回读标记无效')
                    counts={key:data.get(key,0) for key in ('persisted','expected_count')}
                    if any(type(v) is not int or not 0<=v<=500 for v in counts.values()):raise LabError('保存检查数量无效')
                    if flags['saved'] and flags['persistence_verified'] and counts['persisted']!=counts['expected_count']:raise LabError('保存核对数量不一致')
                    phase=data.get('phase','review' if status in {'needs_attention','complete'} else 'filling')
                    if phase not in {'connecting','filling','saving','verifying','review'}:raise LabError('填写步骤无效')
                    job.update(status=status, phase=phase, filled=data['filled'], verified=data['verified'], message=data['message'], issues=issues,**flags,**counts)
                    if job.get('verification_only') and job.get('after_reopen') and flags['persistence_verified'] and not flags['draft_supported'] and counts['persisted']<counts['expected_count']:
                        next(s for s in state['sessions'] if s['id']==connection['session_id'])['preparation']['preserve_unsaved_page']=True
                    return {'accepted': True, 'stop': bool(job.get('stop_requested'))}
                return self.lab.mutate(report)
            raise LabError('未知填写连接动作', 404)
