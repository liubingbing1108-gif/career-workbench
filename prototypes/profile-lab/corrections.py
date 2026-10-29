"""Bound correction previews over stopped attempts, with explicit old-value guards."""
import copy
import json
from lab import LabError, find, uid
from profile_migration import state_hash


def references(content):
    if content.get('corrections'):
        for item in content['corrections']:
            yield dict(website_id=item['website_id'], source_ref=item['source_ref'], value=item['value'])
        return
    for row in content.get('rows', []):
        if 'records' in row:
            for record in row['records']:
                for value in record['values']:yield value
        else:yield row


def mapping_revision(session):
    return state_hash([session.get('website', {}).get('mappings', []), session.get('mapping_skill', {}).get('context')])


def accept_issues(session, job, incoming):
    if not isinstance(incoming, list) or len(incoming) > 500:raise LabError('结构化问题数量无效')
    content = job['confirmed_materials']
    results = []
    for issue in incoming:
        if not isinstance(issue, dict) or len(json.dumps(issue, ensure_ascii=False)) > 20000:raise LabError('结构化问题内容无效')
        ref = issue.get('source_ref')
        matches = [v for v in references(content) if v.get('website_id') == issue.get('website_id') and v.get('source_ref') == ref]
        if len(matches) != 1 or issue.get('expected_value') != matches[0].get('value'):raise LabError('问题不属于已确认材料', 409)
        for key in ('field_id','label','section_id','record_id','snapshot_id','error_type'):
            if not isinstance(issue.get(key), str) or len(issue[key]) > 800:raise LabError('问题定位格式无效')
        if not isinstance(issue.get('observed_value'), (str,list,bool)):raise LabError('缺少可观察官网旧值')
        if not isinstance(issue.get('record_fields', []), list):raise LabError('记录定位无效')
        identity = state_hash([job['id'], issue['website_id'], ref, issue['field_id']])[:24]
        results.append({**copy.deepcopy(issue), 'id': 'issue_'+identity,
                        'session_id': session['id'], 'job_id': session.get('management_job_id'),
                        'attempt_id': job['id'], 'material_digest': job['digest'],
                        'mapping_revision': content.get('mapping_revision'),
                        'allowed_actions': ['edit', 'retry'], 'readback_status': 'needs_review'})
    return results


def preview(preparation, sid, issue_ids):
    if not isinstance(issue_ids, list) or not issue_ids or len(set(issue_ids)) != len(issue_ids):raise LabError('请选择要修正的问题')
    with preparation.lab.lock:
        state = preparation.lab.state(); session = find(state['sessions'], sid)
        previous = session.get('preparation', {}).get('execution', {})
        if previous.get('status') in {'running', 'awaiting_executor'}:raise LabError('请先停止旧批次，并等待停止确认', 409)
        if previous.get('stop_unconfirmed'):raise LabError('旧插件连接中断，尚不能确认已停止；请先在原页停止并重新连接核对',409)
        if previous.get('executor_capabilities', {}).get('correctionRetry') != 1:raise LabError('当前插件尚不支持受限修正，请更新并连接', 409)
        if mapping_revision(session) != previous.get('confirmed_materials', {}).get('mapping_revision'):raise LabError('字段对应已变化，请重新读取官网并核对', 409)
        current = preparation.current(sid)
        if current.get('pending'):raise LabError('请先保存编辑草稿并核对当前材料', 409)
        issues = [find(previous.get('structured_issues', []), key) for key in issue_ids]
        assignments = []
        for issue in issues:
            if issue['attempt_id'] != previous['id']:raise LabError('问题属于旧执行，请重新核对', 409)
            matches = [v for v in references(current) if v['website_id'] == issue['website_id'] and
                       all(v.get('source_ref', {}).get(k) == issue['source_ref'].get(k) for k in ('entry_id','field_id','row_entry_id'))]
            if len(matches) != 1 or matches[0].get('pending') or matches[0].get('manual'):raise LabError('修正字段尚无唯一有效材料', 409)
            if matches[0].get('value') in ('', None):raise LabError('修正不得用缺失值清空官网')
            assignments.append(dict(issue_id=issue['id'], website_id=issue['website_id'],
                                    field_id=issue['field_id'], label=issue['label'], section_id=issue['section_id'], record_id=issue['record_id'],
                                    record_fields=copy.deepcopy(issue.get('record_fields', [])),
                                    expected_current=issue['observed_value'], value=matches[0]['value'],
                                    source_ref=copy.deepcopy(matches[0].get('source_ref', {}))))
        result = dict(url=current['url'], title=current['title'], session_id=sid, parent_attempt=previous['id'],
                      mapping_revision=mapping_revision(session), current_digest=current['digest'],
                      corrections=assignments, rows=[], attachment=None, retry=True, preserve_unsaved_page=True)
        result['digest'] = state_hash(result)
        def save(latest):
            owner=find(latest['sessions'],sid)
            if owner.get('preparation',{}).get('execution',{}).get('id') != previous['id']:raise LabError('执行状态已改变',409)
            owner['preparation']['correction_preview']=copy.deepcopy(result)
        preparation.lab.mutate(save)
        return result


def start(preparation, sid, digest):
    with preparation.lab.lock:
        state=preparation.lab.state();session=find(state['sessions'],sid);prep=session.get('preparation',{})
        proposed=prep.get('correction_preview',{})
        current_job=prep.get('execution',{})
        if current_job.get('correction_digest') == digest:return current_job
        if proposed.get('digest') != digest:raise LabError('请先查看并确认修正预览',409)
        fresh=preview(preparation,sid,[x['issue_id'] for x in proposed['corrections']])
        if fresh['digest'] != digest:raise LabError('材料或官网旧值已变化，请重新确认',409)
        def queue(latest):
            owner=find(latest['sessions'],sid);p=owner['preparation'];old=p['execution']
            if old['id'] != fresh['parent_attempt'] or old['status'] in {'running','awaiting_executor'}:raise LabError('旧批次尚未停止或已变化',409)
            if any(s['id']!=sid and (s.get('preparation',{}).get('execution',{}).get('status') in {'running','awaiting_executor'} or s.get('preparation',{}).get('execution',{}).get('stop_unconfirmed')) and (s.get('website') or s.get('target') or {}).get('url')==fresh['url'] for s in latest['sessions']):raise LabError('同一官网仍有其他岗位正在执行或等待停止确认',409)
            p.setdefault('execution_history',[]).append({k:copy.deepcopy(v) for k,v in old.items() if k!='connection'})
            content=copy.deepcopy(fresh)
            # Keep source rows solely for validating executor reports; correction runner writes only its explicit list.
            current=preparation.current(sid);content['rows']=current['rows']
            job=dict(id=uid('correction'),digest=digest,correction_digest=digest,status='awaiting_executor',confirmed_materials=content,
                     filled=0,verified=0,saved=False,message='已确认局部修正；等待核对官网旧值后执行。')
            p['execution']=job;p.pop('correction_preview',None)
            return job
        return preparation.lab.mutate(queue)
