"""Transfer applied history only; an opportunity pool is not application intent."""
import json
import uuid
import re
from urllib.parse import urlsplit
from feishu import candidates, cell, outcome
from store import validate_job, safe_url, Invalid, Conflict

MIGRATION_ID = 'feishu-to-local-D68'
SCOPE = 'historical-applied-only-D70'
CORRECTION_ID = 'feishu-scope-D70'
RESULTS_ID = 'feishu-results-and-sources-D71'


def selected_candidates(snapshot):
    # The application table is applied history, including later interview stages.
    # Priority/undecided opportunities are never a decision to apply.
    return [row for row in candidates(snapshot) if row['historical_applied']]


def reclassify_results(store, expected_jobs, receipt_id=RESULTS_ID):
    """Classify explicit legacy results; preserve raw sources and every unrelated value."""
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        receipt=db.execute('SELECT payload FROM migrations WHERE id=?',(receipt_id,)).fetchone()
        if receipt:return {**json.loads(receipt[0]),'replayed':True}
        current=[tuple(r) for r in db.execute('SELECT * FROM jobs ORDER BY id')]
        if current!=expected_jobs:raise Conflict('备份后记录变化，未纠正，请重新核对')
        updated=[];classified=[];skipped=[]
        for jid,revision,payload in current:
            job=json.loads(payload)
            if job.get('source_kind')!='feishu':continue
            before=dict(job)
            job.setdefault('source_url',job.get('url',''))
            if not job['source_url']:job['source_url']=job.get('url','')
            job.setdefault('official_url_status','unverified')
            legacy=job.get('legacy_fields',{})
            result=outcome(legacy)
            original_stage=cell(legacy.get('面试进度'))
            if original_stage=='已投递' or job.get('role_summary'):original_stage=''
            can_classify=revision==1 or job.get('recruitment_stage','')==original_stage
            if result and can_classify:
                job.update(recruitment_stage=result,legacy_interview_review='',outcome_from_legacy_notes=True)
                job['mapping_notes']=job.get('mapping_notes',[])+['原合并备注中的明确招聘结果归入招聘进度；原文保留']
                classified.append(jid)
            elif result and job.get('recruitment_stage')!=result:
                skipped.append(jid)
            if job!=before:
                db.execute('UPDATE jobs SET revision=revision+1,payload=? WHERE id=?',(json.dumps(job,ensure_ascii=False),jid))
                updated.append(jid)
        result={'updated_ids':updated,'classified_ids':classified,'skipped_edited_ids':skipped,
                'updated':len(updated),'classified':len(classified),'source_preserved':True}
        db.execute('INSERT INTO migrations VALUES (?,?)',(receipt_id,json.dumps(result)))
        return {**result,'replayed':False}


def migrate(store, snapshot):
    all_rows = candidates(snapshot)
    rows = selected_candidates(snapshot)
    source = {t['kind']+':'+r['record_id']:r['fields'] for t in snapshot['tables'] for r in t['records']}
    if len(source) != len(all_rows): raise Conflict('来源记录标识重复，未迁移')
    prepared = []
    for row in rows:
        job = dict(row); rid = job.pop('id'); f = source[rid]
        raw_url=job['url'];markdown=re.fullmatch(r'\[[\s\S]*\]\(([\s\S]*)\)',raw_url.strip())
        try:
            job['url']=safe_url(markdown.group(1) if markdown else raw_url)
            parsed=urlsplit(job['url'])
            if job['url'] and ('.' not in parsed.hostname or parsed.username or parsed.password):raise Invalid('来源链接待补齐')
        except Invalid:
            job['url']=''
            job['mapping_notes'].append('原投递链接无法识别为完整网址，原文已保留，请补齐后启动')
        job['source_url']=job['url']
        if job.get('role_summary'): job['role'] = job['legacy_role']
        job['needs_review'] = not job['company'] or not job['role'] or job.get('role_summary',False)
        job['timeline_text'] = cell(f.get('投递时间线'))
        job['interview_notes'] = cell(f.get('面试记录'))
        job['review_notes'] = cell(f.get('复盘'))
        job['legacy_interview_review'] = '' if job.get('outcome_from_legacy_notes') else cell(f.get('面试记录及复盘'))
        job['mapping_notes'] = [n for n in job['mapping_notes'] if '选择导入' not in n]
        validate_job(job); prepared.append((rid,job))
    db=store.connect()
    try:
        with db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT payload FROM migrations WHERE id=?',(MIGRATION_ID,)).fetchone()
            if old:
                previous = json.loads(old[0])
                if previous.get('scope') != SCOPE:
                    raise Conflict('旧迁移包含机会池，请先运行已授权的范围纠正')
                return {**previous, 'replayed':True}
            ids=[]
            for rid,job in prepared:
                jid=str(uuid.uuid4()); db.execute('INSERT INTO jobs VALUES (?,1,?)',(jid,json.dumps(job,ensure_ascii=False)))
                saved=json.loads(db.execute('SELECT payload FROM jobs WHERE id=?',(jid,)).fetchone()[0])
                if saved['legacy_fields'] != source[rid]: raise Conflict('迁移回读不一致，已回滚')
                ids.append(jid)
            result={'ids':ids,'count':len(ids),'pending_review':sum(j['needs_review'] for _,j in prepared),
                    'missing_url':sum(not j['url'] for _,j in prepared),
                    'source_rows':len(source),'selected_source_rows':len(rows),
                    'excluded_source_rows':len(all_rows)-len(rows),'scope':SCOPE,
                    'source_fetched_at':snapshot['fetched_at']}
            db.execute('INSERT INTO migrations VALUES (?,?)',(MIGRATION_ID,json.dumps(result)))
        return {**result,'replayed':False}
    finally: db.close()


def correct_scope(store, snapshot, profile_path, expected_jobs, expected_profile):
    """D70 repair of the exact old import, atomically with linked preparations."""
    source_rows = candidates(snapshot)
    eligible = {row['id'] for row in selected_candidates(snapshot)}
    db = store.connect()
    try:
        with db:
            db.execute('ATTACH DATABASE ? AS profile', (str(profile_path),))
            if any(db.execute(f'PRAGMA {name}.journal_mode').fetchone()[0]
                   not in ('delete', 'truncate', 'persist') for name in ('main', 'profile')):
                raise Conflict('数据库事务模式不支持范围纠正，未修改')
            db.execute('BEGIN IMMEDIATE')
            done = db.execute('SELECT payload FROM migrations WHERE id=?', (CORRECTION_ID,)).fetchone()
            if done:
                return {**json.loads(done[0]), 'replayed':True}
            current_jobs = [tuple(r) for r in db.execute('SELECT * FROM jobs ORDER BY id')]
            body = db.execute('SELECT body FROM profile.state WHERE id=1').fetchone()[0]
            if current_jobs != expected_jobs or body != expected_profile:
                raise Conflict('备份后记录发生变化，未修改，请重新核对')
            state = json.loads(body)
            if any(s.get('preparation', {}).get('execution', {}).get('status') in ('queued', 'running')
                   for s in state['sessions']):
                raise Conflict('官网任务仍在执行，未修改')
            old = db.execute('SELECT payload FROM migrations WHERE id=?', (MIGRATION_ID,)).fetchone()
            if not old:
                raise Conflict('原迁移账本不存在，未修改')
            ledger = json.loads(old[0])
            if len(ledger['ids']) != len(source_rows):
                raise Conflict('原迁移账本与来源数量不一致，未修改')
            existing = {jid:(revision,json.loads(payload)) for jid,revision,payload in current_jobs}
            keep, remove = [], []
            for jid, row in zip(ledger['ids'], source_rows):
                if jid in existing:
                    revision, job = existing[jid]
                    if job.get('source_kind') != 'feishu' or job.get('source_record_id') != row['source_record_id']:
                        raise Conflict('原迁移记录归属不一致，未修改')
                if row['id'] in eligible:
                    keep.append(jid)
                elif jid in existing:
                    if revision != 1 or job.get('application_status') != '未投递':
                        raise Conflict('原机会记录已被维护，未批量移出，请先核对')
                    remove.append(jid)
            removed_sessions = [s for s in state['sessions'] if s.get('management_job_id') in remove]
            if removed_sessions:
                state['sessions'] = [s for s in state['sessions'] if s.get('management_job_id') not in remove]
                db.execute('UPDATE profile.state SET body=? WHERE id=1', (json.dumps(state,ensure_ascii=False),))
            db.executemany('DELETE FROM jobs WHERE id=?', [(jid,) for jid in remove])
            retained = [existing[jid][1] for jid in keep if jid in existing]
            ledger.update(ids=keep, count=len(keep), scope=SCOPE,
                selected_source_rows=len(keep), excluded_source_rows=len(source_rows)-len(keep),
                pending_review=sum(j.get('needs_review',False) for j in retained),
                missing_url=sum(not j.get('url') for j in retained))
            db.execute('UPDATE migrations SET payload=? WHERE id=?', (json.dumps(ledger),MIGRATION_ID))
            result = {'removed_ids':remove, 'removed':len(remove),
                'removed_preparations':len(removed_sessions), 'retained_migration_records':len(retained), 'scope':SCOPE}
            db.execute('INSERT INTO migrations VALUES (?,?)', (CORRECTION_ID,json.dumps(result)))
        return {**result, 'replayed':False}
    finally:
        db.close()


def separate_links(store, expected_jobs):
    """One-time D76 field separation after a caller-owned backup and precheck."""
    from store import link_fields
    receipt_id='source-and-official-links-D76'
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        receipt=db.execute('SELECT payload FROM migrations WHERE id=?',(receipt_id,)).fetchone()
        if receipt:return {**json.loads(receipt[0]),'replayed':True}
        current=[tuple(r) for r in db.execute('SELECT * FROM jobs ORDER BY id')]
        if current!=expected_jobs:raise Conflict('备份后记录变化，未拆分链接字段')
        changed=verified=0
        for jid,revision,payload in current:
            original=json.loads(payload);job=link_fields(original)
            if job.get('official_url_status')!='verified':job['official_url']=''
            if job['official_url']:verified+=1
            if job!=original:
                db.execute('UPDATE jobs SET revision=revision+1,payload=? WHERE id=?',(json.dumps(job,ensure_ascii=False),jid));changed+=1
        result={'updated':changed,'official_verified':verified,'total':len(current)}
        db.execute('INSERT INTO migrations VALUES (?,?)',(receipt_id,json.dumps(result)))
        return {**result,'replayed':False}
