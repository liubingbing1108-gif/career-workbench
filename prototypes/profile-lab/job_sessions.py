"""Coordinate independent management jobs with their preparation records."""
import json
from urllib.parse import urlsplit, parse_qs
from lab import LabError

def same_role_form(url,target):
    a,b=urlsplit(url),urlsplit(target)
    if a.scheme!='https' or b.scheme!='https' or a.netloc!=b.netloc or a.username or a.password or a.port not in (None,443):return False
    if url==target:return True
    identity=parse_qs(b.query).get('jobAdId')
    if identity and a.scheme==b.scheme=='https' and a.netloc==b.netloc and a.path=='/form' and parse_qs(a.query).get('jobAdId')==identity:return True
    from direct_entry import feishu_identity
    form,role=feishu_identity(url),feishu_identity(target)
    return bool(form and role and form[0].netloc==role[0].netloc and form[1:]==role[1:])


class JobSessions:
    def __init__(self, lab, store, preparation):
        self.lab, self.store, self.preparation = lab, store, preparation
        preparation.confirmation_view = self.confirmation_view

    def confirmation_view(self, session):
        from store import Missing
        jid = session.get('management_job_id')
        if not jid:
            return None
        try:
            job = self.store.get(jid)
        except Missing:
            return None
        return {'session_id': session['id'], **{key: job.get(key) for key in ('id', 'revision', 'application_status', 'application_confirmed_at', 'timeline')}}

    def confirm_application(self, sid, revision, confirmed):
        from lab import find
        from store import Missing, Conflict
        if confirmed is not True:
            raise LabError('请本人确认已在官网完成投递')
        with self.lab.lock:
            session = find(self.lab.state()['sessions'], sid)
            if not session.get('management_job_id'):
                raise LabError('本次准备未关联投递管理岗位')
            if session.get('preparation', {}).get('execution', {}).get('status') in {'running', 'awaiting_executor'}:
                raise LabError('填写仍在进行，请先暂停并到官网确认', 409)
            try:
                self.validate_destination(sid)
                return self.store.confirm_application(session['management_job_id'], revision)
            except Missing as error:
                raise LabError(str(error), 404)
            except Conflict as error:
                raise LabError(str(error), 409)

    def open(self, data):
        with self.lab.lock:
            job_id = data.get('job_id')
            if job_id:
                if not isinstance(job_id, str) or len(job_id) > 200:
                    raise LabError('岗位标识无效')
                from store import Missing
                # A stale iframe cannot recreate a deleted job's preparation.
                try:
                    job = self.store.get(job_id)
                except Missing as error:
                    raise LabError(str(error), 404)
                if data.get('source_id'):
                    raise LabError('岗位与只读来源不能共用准备记录')
                if job.get('needs_review') or not job.get('company') or not job.get('role'):
                    raise LabError('请先在投递管理核对公司和具体岗位')
                if job.get('official_url_status')!='verified':
                    raise LabError('请先从管理表查找并核验官网入口；招聘信息链接不能直接用于填写')
                target=job.get('official_url','')
                if not target:raise LabError('官网投递链接尚未核验，不能使用来源链接填写')
                # Resume the same job's reviewed form, rather than creating an
                # empty session whenever its public detail link is reopened.
                if not data.get('application_url'):
                    def belongs(session):
                        url=(session.get('website') or session.get('target') or {}).get('url','')
                        if url==target:return True
                        binding=session.get('preparation_destination',{})
                        return same_role_form(url,target) or binding.get('official_url')==target and binding.get('application_url')==url
                    existing=[s for s in self.lab.state()['sessions'] if s.get('management_job_id')==job_id and belongs(s)]
                    if existing:
                        return max(existing,key=lambda s:(bool(s.get('preparation',{}).get('execution')),bool(s.get('website')),bool(s.get('form_analysis'))))
                supplied=data.get('application_url') or job.get('official_entry',{}).get('application_url')
                notice=''
                official_target=target
                if supplied:
                    # Preparing a user-selected form is allowed even when the
                    # public job URL uses another identity or platform route.
                    from official import public_https
                    from store import Invalid
                    try:public_https(supplied)
                    except (Invalid,ValueError) as error:raise LabError(str(error))
                    if not same_role_form(supplied,target):
                        notice='申请表与岗位入口不同，已按指定申请表继续准备。'
                    target=supplied
                session=self.preparation.open_target(target, job['role'], job_id,
                    job.get('requires_preference', False))
                def bind(state):
                    from lab import find
                    current=find(state['sessions'],session['id'])
                    current['preparation_destination']={'official_url':official_target,'application_url':target}
                    current['destination_notice']=notice
                    return current
                return self.lab.mutate(bind)
            url=data.get('url')
            try:
                parsed=urlsplit(url.strip())
                if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or len(url)>3000:
                    raise ValueError()
            except (ValueError,AttributeError):
                raise LabError('请粘贴有效的 HTTPS 招聘申请链接')
            job = self.store.create_link(url,data.get('request_id'))
            # Legacy intake creates only a pending record; launch/start still require a verified destination.
            return self.preparation.open_target(job['source_url'],job['role'],job['id'],job.get('requires_preference',False))

    def validate_destination(self,sid):
        from lab import find
        session=find(self.lab.state()['sessions'],sid)
        if not session.get('management_job_id'):return
        job=self.store.get(session['management_job_id'])
        target=job.get('official_url','')
        if job.get('official_url_status')!='verified' or not target:
            raise LabError('官网投递链接尚未核验，请从管理记录重新开始投递')
        actual=(session.get('website') or session.get('target') or {}).get('url','')
        binding=session.get('preparation_destination',{})
        selected=binding.get('official_url')==target and binding.get('application_url')==actual
        if actual!=target and not selected and not same_role_form(actual,target):
            raise LabError('当前申请表不属于这条官网投递链接，请重新开始投递')

    def counts(self):
        result = {}
        for session in self.lab.state()['sessions']:
            job_id = session.get('management_job_id')
            if job_id:
                summary = result.setdefault(job_id, {'preparation_count': 0, 'execution_count': 0})
                summary['preparation_count'] += 1
                summary['execution_count'] += bool(session.get('preparation', {}).get('execution'))
                prep = session.get('preparation', {})
                status = prep.get('execution', {}).get('status')
                summary['continuation'] = {'session_id': session['id'], 'label':
                    '填写进行中' if status in ('running', 'awaiting_executor') else
                    '已暂停，可继续' if status == 'paused' else
                    '中断待继续' if status == 'failed' else
                    '待官网确认' if status in ('complete', 'needs_attention') else '草稿待继续'}
        return result

    def delete(self, job_id, revision, confirmed):
        # The profile lock serializes scans, reports and opening with this delete.
        # SQLite ATTACH commits both local databases in one rollback transaction.
        with self.lab.lock:
            def related(db):
                profile_path = self.lab.directory / 'lab.sqlite'
                if not profile_path.is_file():
                    raise LabError('资料库不可用，未删除岗位', 503)
                db.execute('ATTACH DATABASE ? AS profile', (str(profile_path),))
                # WAL cannot guarantee one atomic commit across attached databases.
                modes = [db.execute(f'PRAGMA {name}.journal_mode').fetchone()[0]
                         for name in ('main', 'profile')]
                if any(mode not in ('delete', 'truncate', 'persist') for mode in modes):
                    raise LabError('数据库事务模式不支持联动删除，未删除岗位；请检查运行配置', 503)
                state = json.loads(db.execute('SELECT body FROM profile.state WHERE id=1').fetchone()[0])
                removed = [s for s in state['sessions'] if s.get('management_job_id') == job_id]
                state['sessions'] = [s for s in state['sessions'] if s.get('management_job_id') != job_id]
                db.execute('UPDATE profile.state SET body=? WHERE id=1', (json.dumps(state, ensure_ascii=False),))
                return {'preparations_deleted': len(removed)}
            return self.store.delete(job_id, revision, confirmed, related)
