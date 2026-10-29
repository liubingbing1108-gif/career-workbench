"""Pure, deterministic migration preparation. No filesystem or network access."""
import copy
import hashlib
import json
from profile_contract import CONTRACT, RECORD_TYPES, active, install, expression_ids, fields_for


def state_hash(state):
    return hashlib.sha256(json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def prepare(original, timestamp):
    if active(original):
        return copy.deepcopy(original), dict(already_applied=True, input_hash=state_hash(original), pending=len(original.get('profile_pending', [])))
    state = copy.deepcopy(original)
    before = state_hash(original)
    state['profile_legacy_evidence'] = {key:copy.deepcopy(original.get(key, [] if key != 'profile_layouts' else {}))
                                       for key in ('entries', 'fields', 'versions', 'answer_versions', 'profile_layouts')}
    install(state)
    by_id = {v['id']:v for key in ('versions', 'answer_versions') for v in state.get(key, [])}
    pending = state['profile_pending']
    def issue(entry, kind, **details):
        identity = [entry['id'], kind, details]
        pending.append(dict(id='migration_'+state_hash(identity)[:16], entry_id=entry['id'],
                            kind=kind, state='pending', **details))
    for entry in state['entries']:
        cat = entry['category']
        removed_values={fid:value for fid,value in entry.get('values',{}).items()
                        if value and any(f['id']==fid and f.get('legacy_preserved') for f in state['fields'])}
        for fid,ref in entry.get('default_versions',{}).items():
            if ref in by_id and by_id[ref].get('content') and any(f['id']==fid and f.get('legacy_preserved') for f in state['fields']):
                removed_values[fid]=by_id[ref]['content']
        if removed_values:
            issue(entry,'removed_values',reason='已取消预设的旧内容仅供核对，不参与新的填写，也不进入30天回收站',field_ids=sorted(removed_values))
        if cat in {'social', 'preferences'} or cat == 'academic' and entry.get('record_type') == 'patent':
            entry['legacy_only'] = True
            issue(entry, 'legacy_object', reason='已取消的预设或需按平台拆分的账号，保留原值待核对')
            continue
        if cat in RECORD_TYPES and entry.get('record_type') not in dict(RECORD_TYPES[cat]):
            entry['legacy_only'] = True
            issue(entry, 'record_type', reason='旧对象类型不明确，不能按字段名自动选定；确认类型后仍需核对旧值')
            continue
        if cat == 'subjective':
            entry['legacy_only'] = True
            issue(entry, 'statement_choice', reason='旧主题需确认归入个人陈述、兴趣爱好或个人特长；不自动拼接')
            continue
        old_sets = [entry.get('profile_base_version') or dict(id='default', name='版本1', field_versions=copy.deepcopy(entry.get('default_versions', {}))),
                    *entry.get('set_versions', [])]
        deleted = set(entry.get('profile_deleted_sets', []))
        expression = set(expression_ids(state, entry))
        if expression:
            entry['expression_versions'] = []
            for version in old_sets:
                refs = {fid:vid for fid,vid in version.get('field_versions', {}).items() if fid in expression and vid in by_id}
                migrated = dict(id=version['id'], name=version.get('name', '旧版本'), field_versions=refs, revision=1)
                if version.get('profile_deleted') or version['id'] in deleted:
                    migrated['deleted_at'] = timestamp
                    state['profile_trash'].append(dict(id='version:'+entry['id']+'/'+version['id'], kind='version', entry_id=entry['id'], version_id=version['id'], deleted_at=timestamp, expires_at=timestamp+30*86400, migrated=True))
                entry['expression_versions'].append(migrated)
            chosen = entry.get('profile_default_set_id', 'default')
            entry['profile_default_set_id'] = chosen if any(v['id'] == chosen and not v.get('deleted_at') for v in entry['expression_versions']) else None
            for fid in expression:
                entry.get('values',{}).pop(fid,None)
                entry.get('sources',{}).pop(fid,None)
                entry.get('default_versions',{}).pop(fid,None)
        live_sets = [v for v in old_sets if v['id'] not in deleted and not v.get('profile_deleted')]
        exam_result = cat=='language' and entry.get('record_type')=='exam'
        result_fields={'language_score','exam_files','exam_level','obtained_date','exam_components'}
        legacy_result_fields={'exam_date','exam_subscores','exam_level'}
        if exam_result:
            # A record-version is evidence of a sitting; separate field variants
            # are not evidence that a score/date/components occurred together.
            sitting_fields=result_fields|legacy_result_fields
            bundles=[];seen=set();covered=set()
            def add_bundle(key,label,values,refs):
                nonempty={fid:value for fid,value in values.items() if value!=''}
                if not nonempty or state_hash(nonempty) in seen:return
                seen.add(state_hash(nonempty))
                bundles.append(dict(id=key,label=label,values={fid:value for fid,value in nonempty.items() if fid in result_fields-legacy_result_fields},
                                    legacy_values={fid:value for fid,value in nonempty.items() if fid in legacy_result_fields},field_versions=refs))
            for version in live_sets:
                refs={fid:ref for fid,ref in version.get('field_versions',{}).items() if fid in sitting_fields and ref in by_id}
                covered.update(refs.values())
                values={fid:by_id[ref]['content'] for fid,ref in refs.items()}
                if version['id']==old_sets[0]['id']:
                    # The default snapshot may have unversioned legacy values.
                    values={**{fid:value for fid,value in entry.get('values',{}).items() if fid in sitting_fields},**values}
                add_bundle(version['id'],version.get('name','旧考试结果'),values,refs)
            for ref,value in by_id.items():
                if value['entry_id']==entry['id'] and value['field_id'] in sitting_fields and ref not in covered and not value.get('profile_deleted'):
                    add_bundle('field:'+ref,'单字段旧值（其余结果未知）',{value['field_id']:value['content']},{value['field_id']:ref})
            if bundles:
                issue(entry,'exam_sitting',reason='请选择同一次考试的整组结果；未提供的结果保持空白，旧日期与等级需明确核对含义',bundles=bundles)
            for fid in result_fields:
                entry.setdefault('values',{}).pop(fid,None);entry.setdefault('default_versions',{}).pop(fid,None)
        for field in fields_for(state, entry):
            fid = field['id']
            if fid in expression or exam_result and fid in result_fields:continue
            candidates = []
            if entry.get('values', {}).get(fid) is not None:candidates.append(entry['values'][fid])
            for version in live_sets:
                ref = version.get('field_versions', {}).get(fid)
                if ref in by_id:candidates.append(by_id[ref]['content'])
            if not expression:
                candidates.extend(v['content'] for v in by_id.values() if v['entry_id'] == entry['id'] and v['field_id'] == fid and not v.get('profile_deleted'))
            distinct = list(dict.fromkeys(v for v in candidates if v != ''))
            if len(distinct) > 1:
                issue(entry, 'shared_fact' if expression else 'current_choice', field_id=fid, candidates=distinct)
                entry.setdefault('values', {}).pop(fid, None)
                entry.setdefault('default_versions', {}).pop(fid, None)
            elif distinct:
                value = distinct[0]
                try:
                    from lab import validate_value
                    validate_value(field, value)
                except Exception as error:
                    issue(entry, 'value_format', field_id=fid, candidates=distinct, reason=str(error))
                    entry.setdefault('values', {}).pop(fid, None)
                    entry.setdefault('default_versions', {}).pop(fid, None)
                    continue
                entry.setdefault('values', {})[fid] = value
                ref = next((v['id'] for v in by_id.values() if v['entry_id'] == entry['id'] and v['field_id'] == fid and v['content'] == value), None)
                if ref:entry.setdefault('default_versions', {})[fid] = ref
        if entry.get('profile_archived'):
            entry['deleted_at'] = timestamp
            state['profile_trash'].append(dict(id='object:'+entry['id'], kind='object', entry_id=entry['id'], deleted_at=timestamp, expires_at=timestamp+30*86400, migrated=True))
    # Duplicate identities remain isolated until a person chooses the current one.
    buckets = {}
    for entry in state['entries']:
        if entry.get('legacy_only') or entry.get('profile_archived'):continue
        fid = ('identity_type' if entry['category'] == 'identity_documents' else
               'exam_name' if entry['category'] == 'language' and entry.get('record_type') == 'exam' else
               'language_name' if entry['category'] == 'language' else None)
        value = entry.get('values', {}).get(fid, '').strip().casefold() if fid else ''
        if value:buckets.setdefault((entry['category'], entry.get('record_type'), value), []).append(entry)
    for entries in buckets.values():
        if len(entries) > 1:
            for entry in entries:
                entry['legacy_only'] = True
                issue(entry, 'duplicate_identity', related_ids=[e['id'] for e in entries])
    for session in state['sessions']:
        prep = session.get('preparation', {})
        # Preserve evidence actually stored by the executor. Never recompute old submissions.
        attempts = [('history:'+str(index), execution) for index, execution in enumerate(prep.get('execution_history', []))]
        if prep.get('execution'):attempts.append(('current', prep['execution']))
        for key, execution in attempts:
            if execution.get('confirmed_materials'):
                session.setdefault('profile_historical_materials', []).append(copy.deepcopy(execution))
            else:
                pending.append(dict(id='history:'+session['id']+':'+key, kind='historical_evidence', session_id=session['id'], attempt_key=key, affected_entry_ids=[e['id'] for e in original['entries']], state='pending', reason='该次执行缺少已展开实际内容，不能以当前资料代填；迁移前旧对象保留，迁移后新增对象不受此历史缺口影响'))
        prep.pop('preview', None)
    if not any(e['category']=='subjective' and not e.get('legacy_only') for e in state['entries']):
        state['entries'].append(dict(id='profile_subjective_'+before[:12],category='subjective',record_type='',values={},sources={},default_versions={}))
    state['profile_migration'] = dict(contract=CONTRACT, input_hash=before, applied_at=timestamp)
    return state, dict(already_applied=False, input_hash=before, output_hash=state_hash(state),
                       entries=len(state['entries']), pending=len(pending), files=len(state.get('files', [])),
                       pending_kinds={kind:sum(p['kind'] == kind for p in pending) for kind in sorted({p['kind'] for p in pending})})


def classify_entry(state, entry, record_type, timestamp):
    """Run the deferred value migration after a person chooses an object type.

    Only the chosen entry and its pending/trash records are installed. Existing
    current records, catalog edits and original evidence must not be remigrated.
    """
    isolated = copy.deepcopy(state)
    isolated.pop('profile_contract', None)
    isolated['entries'] = [copy.deepcopy(entry)]
    isolated['entries'][0].update(record_type=record_type)
    isolated['entries'][0].pop('legacy_only', None)
    isolated.update(sessions=[], profile_pending=[], profile_trash=[])
    migrated, _ = prepare(isolated, timestamp)
    replacement = next(e for e in migrated['entries'] if e['id'] == entry['id'])
    entry.clear();entry.update(replacement)
    for key in ('profile_pending', 'profile_trash'):
        existing = {item['id'] for item in state[key]}
        state[key].extend(item for item in migrated[key] if item.get('entry_id') == entry['id'] and item['id'] not in existing)
