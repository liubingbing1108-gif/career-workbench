"""Explicit migration choices; preserved source evidence is never a current answer."""
import copy
import time
from lab import LabError, find
from profile_migration import state_hash
from profile_contract import fields_for, RECORD_TYPES


def token(state, item):
    return state_hash([item, state['entries'], state['fields'], state.get('answer_versions', []), state.get('versions', [])])


def view(state):
    evidence = state.get('profile_legacy_evidence', {})
    definitions = {f['id']: f for f in evidence.get('fields', [])}
    rows = []
    for item in state.get('profile_pending', []):
        result = copy.deepcopy(item)
        if item['state'] == 'pending':result['edit_token'] = token(state, item)
        if item.get('entry_id'):
            entry = next((e for e in evidence.get('entries', []) if e['id'] == item.get('entry_id')), {})
            values = copy.deepcopy(entry.get('values', {}))
            refs = entry.get('default_versions', {})
            for value in evidence.get('versions', []) + evidence.get('answer_versions', []):
                if refs.get(value['field_id']) == value['id']:values[value['field_id']] = value['content']
            result['evidence'] = [dict(field_id=fid, label=definitions.get(fid, {}).get('label', fid), value=value)
                                  for fid, value in values.items() if value != '']
        rows.append(result)
    return rows


def resolve(state, data):
    from profile_current import save_values, validate_values
    if state.get('profile_contract') != 30:raise LabError('尚未启用迁移确认')
    request = data.get('request_id')
    if not isinstance(request, str) or not request or len(request) > 160:raise LabError('缺少确认请求标识')
    signature = state_hash(data)
    receipts = state.setdefault('profile_pending_receipts', {})
    if request in receipts:
        if receipts[request]['signature'] != signature:raise LabError('请求标识已使用', 409)
        return copy.deepcopy(receipts[request]['result'])
    item = find(state.get('profile_pending', []), data.get('id'))
    if item['state'] != 'pending' or data.get('edit_token') != token(state, item):raise LabError('待处理资料已变化，请重新核对', 409)
    if data.get('confirmed') is not True:raise LabError('请明确确认当前内容')
    kind = item['kind']
    if kind == 'historical_evidence':raise LabError('缺少历史实际内容，不能用当前资料或空值替代', 409)
    entry = find(state['entries'], item['entry_id'])
    action = data.get('action', 'choose')
    if action == 'preserve':
        # Explicitly choosing no current value keeps old evidence readable.
        result = dict(id=item['id'], state='preserved', action=action)
    elif action=='choose' and kind=='exam_sitting':
        from resume_current import EXAM_RESULT
        bundle=find(item['bundles'],data.get('bundle_id'))
        # Only explicit semantic corrections may fill the new fields. All
        # unprovided fields are cleared atomically with the chosen sitting.
        corrections=data.get('values',{})
        if not isinstance(corrections,dict) or set(corrections)-EXAM_RESULT:raise LabError('考试结果字段无效')
        values={fid:bundle['values'].get(fid,'') for fid in EXAM_RESULT}
        values.update(corrections)
        save_values(state,entry,values)
        result=dict(id=item['id'],state='resolved',entry_id=entry['id'],bundle_id=bundle['id'],action=action)
    elif action == 'choose' and kind in {'shared_fact', 'current_choice', 'value_format', 'exam_semantics'}:
        fid = data.get('field_id', item.get('field_id'))
        if kind == 'exam_semantics':
            targets = {'exam_date': {'obtained_date'}, 'exam_level': {'exam_level'}, 'exam_subscores': {'exam_components'}}
            if fid not in targets.get(item['field_id'], set()):raise LabError('请选择明确的新字段含义')
        elif fid != item['field_id']:raise LabError('当前值选择不能改写其他字段')
        value = data.get('value')
        if not isinstance(value, str):raise LabError('请填写或选择当前值')
        save_values(state, entry, {fid: value})
        result = dict(id=item['id'], state='resolved', entry_id=entry['id'], field_id=fid, action=action)
    elif action == 'choose' and kind == 'duplicate_identity':
        chosen = data.get('chosen_entry_id')
        if chosen not in item['related_ids']:raise LabError('请选择同组旧对象')
        winner = find(state['entries'], chosen)
        if winner.get('profile_archived'):raise LabError('已删除对象不可选作当前资料')
        winner.pop('legacy_only', None)
        validate_values(state, winner, {})
        for other in state['profile_pending']:
            if other['kind'] == kind and other['state'] == 'pending' and set(other['related_ids']) == set(item['related_ids']):
                other.update(state='resolved', chosen_entry_id=chosen, resolved_at=time.time())
        result = dict(id=item['id'], state='resolved', entry_id=chosen, action=action)
    elif action == 'choose' and kind == 'record_type':
        record_type = data.get('record_type')
        if record_type not in dict(RECORD_TYPES.get(entry['category'], [])):raise LabError('请选择可用对象类型')
        values = data.get('values', {})
        if not isinstance(values, dict):raise LabError('字段内容无效')
        if values:raise LabError('请先确认对象类型，再分别核对旧值或整组考试结果')
        from profile_migration import classify_entry
        classify_entry(state, entry, record_type, time.time())
        # Identity conflicts still block activation; no implicit merge or choice.
        if not entry.get('profile_archived'):validate_values(state, entry, {})
        result = dict(id=item['id'], state='resolved', entry_id=entry['id'], action=action)
    elif action == 'choose' and kind in {'statement_choice', 'legacy_object'}:
        target = find(state['entries'], data.get('target_entry_id'))
        fid = data.get('field_id')
        allowed = {'personal_statement', 'hobbies', 'personal_strengths'} if kind == 'statement_choice' else {'wechat', 'qq'} if entry['category'] == 'social' else set()
        if fid not in allowed or target.get('legacy_only') or target.get('profile_archived'):raise LabError('此旧对象仅可保留查看，或明确归入允许的当前字段')
        if fid not in {f['id'] for f in fields_for(state, target)}:raise LabError('目标字段不属于此对象')
        value = data.get('value')
        if not isinstance(value, str):raise LabError('请填写确认后的当前内容')
        save_values(state, target, {fid: value})
        result = dict(id=item['id'], state='resolved', entry_id=target['id'], field_id=fid, action=action)
    else:raise LabError('此待处理类型不支持该操作')
    item.update(state=result['state'], resolution=copy.deepcopy(result), resolved_at=time.time())
    receipts[request] = dict(signature=signature, result=copy.deepcopy(result))
    return result
