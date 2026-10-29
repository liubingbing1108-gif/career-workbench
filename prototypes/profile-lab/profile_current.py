"""Flat profile mutations within Lab's existing SQLite transaction."""
import copy
import json
import time
from lab import LabError, find, uid, validate_value, put_answer
from profile_contract import EXPRESSIONS, RECORD_TYPES, fields_for, expression_ids, current_values

RETENTION = 30 * 24 * 60 * 60


def add_custom_field(state, data):
    from profile_library import valid_token
    from profile_migration import state_hash
    entry = find(state['entries'], data.get('entry_id'))
    if entry.get('legacy_only') or entry.get('profile_archived') or entry.get('purged'):raise LabError('对象不可编辑', 409)
    if not valid_token(state, entry, data.get('edit_token')):raise LabError('对象已变化，请重新核对', 409)
    if data.get('confirmed_new_attribute') is not True:raise LabError('请先查找全部字段并确认是新属性')
    label, kind = data.get('label', ''), data.get('type', 'text')
    if not isinstance(label, str) or not label.strip() or len(label) > 100 or kind not in {'text','multiline','number','partial_date','select'}:raise LabError('字段名称或类型无效')
    # Look up the entire catalog, including hidden and preserved definitions.
    key = label.strip().casefold()
    matches = [f for f in state['fields'] if key in {str(x).strip().casefold() for x in [f['label'], *f.get('aliases', [])]}]
    if matches:raise LabError('已有同名或别名字段，请使用原字段或先核对含义', 409)
    options = data.get('options', [])
    if not isinstance(options, list) or any(not isinstance(x, str) or not x.strip() for x in options) or kind == 'select' and not options:raise LabError('选项无效')
    field = dict(id=uid('custom'), label=label.strip(), type=kind, category=entry['category'], entry_id=entry['id'], aliases=[], options=options, value_role='fact', save_unit='object')
    state['fields'].append(field)
    entry['profile_revision'] = entry.get('profile_revision', 0) + 1
    return field


def validate_values(state, entry, values):
    fields = {f['id']: f for f in fields_for(state, entry)}
    if not isinstance(values, dict) or set(values) - fields.keys():
        raise LabError('包含不属于当前对象的字段；旧字段只可在迁移记录中查看', 409)
    for fid, value in values.items():
        field = fields[fid]
        validate_value(field, value)
        if field.get('widget') in {'file', 'files'} and value:
            ids = value.split('\n')
            if field['widget'] == 'file' and len(ids) != 1:
                raise LabError('请选择一份原件')
            for file_id in ids:
                find(state['files'], file_id, '原件不存在')
    prospective = {**current_values(state, entry), **values}
    unique = ('identity_type' if entry['category'] == 'identity_documents' else
              'exam_name' if entry['category'] == 'language' and entry.get('record_type') == 'exam' else
              'language_name' if entry['category'] == 'language' and entry.get('record_type') == 'ability' else None)
    if unique and prospective.get(unique, '').strip():
        key = prospective[unique].strip().casefold()
        if any(e['id'] != entry['id'] and e['category'] == entry['category']
               and e.get('record_type') == entry.get('record_type') and not e.get('profile_archived')
               and not e.get('legacy_only') and current_values(state, e).get(unique, '').strip().casefold() == key
               for e in state['entries']):
            raise LabError('已有同类型当前记录，请编辑该记录或先处理迁移冲突', 409)
    return fields


def save_values(state, entry, values, *, mode='update', set_id=None, name=''):
    """Partial facts + exact expression set; immutable value refs protect history."""
    if entry.get('profile_archived') or entry.get('purged'):raise LabError('已删除资料不能通过保存或导入恢复，请重新选择当前对象',409)
    fields = validate_values(state, entry, values)
    expression = set(expression_ids(state, entry))
    versioned = entry['category'] in EXPRESSIONS
    if mode not in {'new', 'update'} or mode == 'new' and not versioned:
        raise LabError('仅任职与项目可以另存表达版本')
    if versioned and 'expression_versions' not in entry:
        initial = dict(id='default', name='版本1', field_versions={}, revision=1)
        entry['expression_versions'] = [initial]
        entry['profile_default_set_id'] = initial['id']
    selected_id = entry.get('profile_default_set_id') if set_id is None else set_id
    selected = next((v for v in entry.get('expression_versions', []) if v['id'] == selected_id and not v.get('deleted_at')), None)
    if versioned and mode == 'update' and expression.intersection(values) and selected is None:
        raise LabError('请选择要编辑的表达版本；当前没有默认版本', 409)
    if mode == 'new' and set_id not in (None, '') and selected is None:
        raise LabError('原版本已变化，请重新选择或新建空白版本', 409)
    if mode == 'new':
        selected = dict(id=uid('expression'), name=name.strip()[:180] or '新版本',
                        field_versions=copy.deepcopy((selected or {}).get('field_versions', {})), revision=0)
        entry['expression_versions'].append(selected)
    refs = {}
    for fid, value in values.items():
        prior = copy.deepcopy(entry.get('default_versions', {}))
        saved = put_answer(state, entry, fields[fid], value, mode='new', name='已确认内容')
        entry['default_versions'] = prior
        refs[fid] = saved['id']
        if fid in expression:
            selected['field_versions'][fid] = saved['id']
        else:
            entry['default_versions'][fid] = saved['id']
            entry.setdefault('values', {})[fid] = value
            entry.setdefault('sources', {})[fid] = saved.get('source', {})
    if selected and (expression.intersection(values) or mode == 'new'):
        selected['revision'] = selected.get('revision', 0) + 1
        if name.strip():selected['name'] = name.strip()[:180]
    for fid in expression:
        entry.get('values',{}).pop(fid,None)
        entry.get('sources',{}).pop(fid,None)
        entry.get('default_versions',{}).pop(fid,None)
    entry['profile_revision'] = entry.get('profile_revision', 0) + 1
    return dict(id=(selected or {}).get('id'), field_versions={**refs, **(selected or {}).get('field_versions', {})})


def link_exams(state, ability, exam_ids, *, expected_revision):
    if ability['category'] != 'language' or ability.get('record_type') != 'ability':
        raise LabError('考试只能关联到语言能力')
    if expected_revision != ability.get('links_revision', 0):
        raise LabError('考试关联已更新，请保留草稿并重新载入', 409)
    if not isinstance(exam_ids, list) or len(set(exam_ids)) != len(exam_ids):
        raise LabError('考试关联列表无效')
    language = current_values(state, ability).get('language_name', '').strip().casefold()
    for eid in exam_ids:
        exam = find(state['entries'], eid)
        if exam['category'] != 'language' or exam.get('record_type') != 'exam' or exam.get('profile_archived') or exam.get('legacy_only'):
            raise LabError('所选考试不可用', 409)
        exam_language = current_values(state, exam).get('exam_language', '').strip().casefold()
        if language and exam_language and language != exam_language:
            raise LabError('考试语种与当前能力不一致')
    links = state.setdefault('language_exam_links', [])
    for link in links:
        if link['ability_id'] == ability['id'] and link.get('active') and link['exam_id'] not in exam_ids:
            link.update(active=False, revision=link.get('revision', 1)+1, reason='manual')
    for eid in exam_ids:
        link = next((x for x in links if x['ability_id'] == ability['id'] and x['exam_id'] == eid), None)
        if link is None:
            links.append(dict(id=uid('link'), ability_id=ability['id'], exam_id=eid, active=True, revision=1))
        elif not link.get('active'):
            link.update(active=True, revision=link.get('revision', 1)+1, reason='manual')
    ability['links_revision'] = ability.get('links_revision', 0)+1


def flat_view(state):
    from profile_library import token
    records = []
    for entry in state['entries']:
        if entry.get('purged') or entry.get('legacy_only') or entry['category'] in {'preferences', 'social', 'attachments'}:
            continue
        versions = [copy.deepcopy(v) for v in entry.get('expression_versions', []) if not v.get('deleted_at')]
        records.append({**copy.deepcopy(entry), 'edit_token': token(state, entry),
                        'values': current_values(state, entry), 'fields': fields_for(state, entry),
                        'record_versions': versions, 'versions_enabled': entry['category'] in EXPRESSIONS,
                        'version_values': {v['id']: current_values(state, entry, v['id']) for v in versions}})
    from profile_pending import view as pending_view
    return dict(contract=30, records=records, drafts=state.get('profile_drafts', {}),
                visibility=state.get('profile_visibility', {}),
                pending=pending_view(state), trash=state.get('profile_trash', []),
                relations=state.get('profile_relations', []), links=state.get('language_exam_links', []),
                relation_revision=state.get('profile_relation_revision',0),
                saved_requests={key:item['result'].get('view_id') for key,item in state.get('profile_receipts',{}).items() if item.get('complete')})


def visibility(state, data):
    entry=find(state['entries'],data.get('entry_id'))
    if data.get('field_id') not in {f['id'] for f in fields_for(state,entry)}:raise LabError('字段不属于此对象')
    if type(data.get('hidden')) is not bool:raise LabError('显示选项无效')
    item=state.setdefault('profile_visibility',{}).setdefault(entry['id'],dict(revision=0,fields=[]))
    if item['revision']!=data.get('revision',0):raise LabError('显示设置已变化，请重新载入',409)
    fields=set(item['fields'])
    if data['hidden']:fields.add(data['field_id'])
    else:fields.discard(data['field_id'])
    item.update(fields=sorted(fields),revision=item['revision']+1)
    return item


def save_record(state, data):
    from profile_library import valid_token, view_record
    new = not data.get('entry_id')
    if new:
        cat = data.get('category')
        allowed = {f['category'] for f in state['fields'] if not f.get('legacy_preserved')}
        if cat not in allowed or cat in {'preferences', 'social', 'attachments'}:
            raise LabError('此类资料已不属于当前目录')
        rt = data.get('record_type', '')
        if cat in RECORD_TYPES and rt not in dict(RECORD_TYPES[cat]):raise LabError('请选择资料类型')
        if cat in {'basic', 'contact', 'subjective', 'additional'} and any(e['category'] == cat and not e.get('profile_archived') for e in state['entries']):
            raise LabError('请编辑已有本人字段', 409)
        entry = dict(id=uid(cat), category=cat, record_type=rt, values={}, sources={}, default_versions={})
        state['entries'].append(entry)
    else:
        entry = find(state['entries'], data['entry_id'])
        if entry.get('profile_archived') or entry.get('legacy_only'):raise LabError('此对象不可编辑', 409)
        if not valid_token(state, entry, data.get('edit_token')):raise LabError('资料已变化，草稿已保留，请重新核对', 409)
        if (data.get('record_type', entry.get('record_type')) or '') != (entry.get('record_type') or ''):
            raise LabError('不能通过编辑字段改变对象类型')
    if data.get('layout') or data.get('scope'):raise LabError('新版资料不提供层级维护')
    saved = save_values(state, entry, data.get('values'), mode=data.get('mode', 'update'), set_id=data.get('set_id'), name=data.get('name', ''))
    # Linked exam edits and links participate in this same Lab transaction.
    exam_ids=list(data.get('exam_ids',[]))
    new_exams=data.get('new_exams',[])
    if not isinstance(new_exams,list) or len(new_exams)>20:raise LabError('新增考试列表无效')
    if new_exams:
        if entry['category']!='language' or entry.get('record_type')!='ability' or not data.get('confirm_exam_updates'):raise LabError('请确认在此语言能力下新增并关联考试')
        for values in new_exams:
            if not isinstance(values,dict) or not values.get('exam_name','').strip():raise LabError('请填写新考试名称')
            created=save_record(state,dict(category='language',record_type='exam',values=values))
            exam_ids.append(created['record']['id'])
    for edit in data.get('exam_edits', []):
        if not data.get('confirm_exam_updates'):raise LabError('请确认同步更新关联考试')
        eid = edit.get('entry_id')
        if eid not in data.get('exam_ids', []):raise LabError('只能修改当前选择关联的考试')
        exam = find(state['entries'], eid)
        if exam.get('record_type') != 'exam' or exam['category'] != 'language':raise LabError('考试对象无效')
        save_record(state, edit)
    if 'exam_ids' in data or new_exams:
        link_exams(state, entry, exam_ids, expected_revision=data.get('links_revision', 0))
    # Changes to either language must preserve all active link type constraints.
    for link in state.get('language_exam_links', []):
        if not link.get('active') or entry['id'] not in {link['ability_id'], link['exam_id']}:continue
        ability = find(state['entries'], link['ability_id']); exam = find(state['entries'], link['exam_id'])
        left = current_values(state, ability).get('language_name', '').strip().casefold()
        right = current_values(state, exam).get('exam_language', '').strip().casefold()
        if left and right and left != right:raise LabError('修改后关联考试语种不一致，请先解除关联')
    key = data.get('draft_key')
    if key:
        draft = state.get('profile_drafts', {}).get(key)
        if draft and draft.get('revision') != data.get('draft_revision'):raise LabError('草稿已更新', 409)
        state.get('profile_drafts', {}).pop(key, None)
    return dict(record=view_record(state, entry), field_versions=saved['field_versions'], set_id=saved['id'], view_id=entry['id'])
