"""Coordinate independent management jobs with their preparation records."""
import json
from urllib.parse import urlsplit, parse_qs
from lab import LabError


class JobSessions:
    def __init__(self, lab, store, preparation):
        self.lab, self.store, self.preparation = lab, store, preparation

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
                        a,b=urlsplit(url),urlsplit(target)
                        identity=parse_qs(b.query).get('jobAdId')
                        return bool(identity and a.scheme==b.scheme=='https' and a.netloc==b.netloc and
                                    a.path=='/form' and parse_qs(a.query).get('jobAdId')==identity)
                    existing=[s for s in self.lab.state()['sessions'] if s.get('management_job_id')==job_id and belongs(s)]
                    if existing:
                        return max(existing,key=lambda s:(bool(s.get('preparation',{}).get('execution')),bool(s.get('website')),bool(s.get('form_analysis'))))
                if data.get('application_url'):
                    # The public role link stays in management. A browser-observed
                    # applicant form belongs only to this local preparation record.
                    form=urlsplit(data['application_url']);role=urlsplit(target)
                    identity=parse_qs(role.query).get('jobAdId')
                    if (job.get('official_entry',{}).get('verification')!='browser' or
                        form.scheme!='https' or form.netloc!=role.netloc or form.username or form.password or
                        form.path!='/form' or not identity or parse_qs(form.query).get('jobAdId')!=identity):
                        raise LabError('申请表与已核验的官网岗位不一致')
                    target=data['application_url']
                return self.preparation.open_target(target, job['role'], job_id,
                    job.get('requires_preference', False))
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
        a,b=urlsplit(actual),urlsplit(target);identity=parse_qs(b.query).get('jobAdId')
        if actual!=target and not (identity and a.scheme==b.scheme=='https' and a.netloc==b.netloc and a.path=='/form' and parse_qs(a.query).get('jobAdId')==identity):
            raise LabError('当前申请表不属于这条官网投递链接，请重新开始投递')

    def counts(self):
        result = {}
        for session in self.lab.state()['sessions']:
            job_id = session.get('management_job_id')
            if job_id:
                summary = result.setdefault(job_id, {'preparation_count': 0, 'execution_count': 0})
                summary['preparation_count'] += 1
                summary['execution_count'] += bool(session.get('preparation', {}).get('execution'))
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
