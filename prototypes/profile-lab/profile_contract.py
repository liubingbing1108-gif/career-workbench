"""F0.31 / V0.14 executable catalog. Activation requires an explicit migration.

Old definitions and their IDs remain readable as evidence. They are never offered
as new presets, nor silently repurposed as a field with a different meaning.
"""
import copy
import hashlib
import json

CONTRACT = 30
EXPRESSIONS = {
    'employment': ('description', 'responsibilities', 'achievements'),
    'projects': ('project_description', 'project_background',
                 'project_responsibilities', 'project_results'),
}
REMOVED = set('''backup_phone backup_phone_code backup_email social_platform social_account
education_description student_number graduation_certificate degree_certificate
exchange_description education_files project_process project_tools activity_organization
activity_location activity_duration activity_duration_unit language_description exam_date
exam_subscores exam_number exam_validity certificate_issuer certificate_validity
certificate_number award_issuer award_subject award_role doi patent_type patent_applied
patent_granted patent_application_number patent_number patent_status portfolio_role
portfolio_platform portfolio_date portfolio_number family_email statement_type
statement_title statement_content statement_language statement_scope statement_role
statement_company'''.split())
REMOVED.update('hukou_' + key for key in ('country', 'province', 'city', 'district', 'address', 'postcode'))
GRADES = ['一般', '良好', '熟练', '精通']
RECORD_TYPES = {'language': [('ability', '语言能力'), ('exam', '考试')],
                'academic': [('paper', '论文')],
                'portfolio': [('work', '作品'), ('homepage', '主页')]}


def active(state):
    return state.get('profile_contract') == CONTRACT


def category_for(state, category_id):
    from lab import category
    definition=category(category_id)
    if definition and active(state) and category_id=='subjective':return (definition[0],definition[1],False)
    return definition


def catalog():
    from profile_schema import FIELDS as legacy
    result = []
    for original in legacy:
        if original['id'] in REMOVED or original['category'] == 'preferences':
            continue
        field = copy.deepcopy(original)
        if field['type'] == 'versioned_text':
            field['type'] = 'multiline'
        if field['category'] == 'academic':
            field['record_types'] = ['paper']
        result.append(field)
    for fid, label, cat, typ, widget, types in [
        ('wechat', '微信号', 'contact', 'text', None, []),
        ('qq', 'QQ号', 'contact', 'text', None, []),
        ('is_native', '是否母语', 'language', 'text', 'boolean', ['ability']),
        ('obtained_date', '获得日期', 'language', 'partial_date', None, ['exam']),
        ('exam_components', '分项成绩', 'language', 'text', 'exam_components', ['exam']),
        ('personal_statement', '个人陈述', 'subjective', 'multiline', None, []),
        ('hobbies', '兴趣爱好', 'subjective', 'multiline', None, []),
        ('personal_strengths', '个人特长', 'subjective', 'multiline', None, []),
    ]:
        result.append(dict(id=fid, label=label, category=cat, type=typ, widget=widget,
                           record_types=types, aliases=[], options=[], supplemental=False, group=''))
    for field in result:
        fid = field['id']
        field['value_role'] = 'expression' if fid in EXPRESSIONS.get(field['category'], ()) else 'fact'
        field['save_unit'] = 'field' if field['category'] in {'basic', 'subjective'} or field['category'] == 'contact' and not fid.startswith(('residence_', 'mailing_')) else 'object'
        if fid in {'language_level', 'listening', 'speaking', 'reading', 'writing', 'skill_level'}:
            field.update(type='select', options=GRADES[:])
        if fid in {'language_score', 'skill_years'}:
            field['type'] = 'number'
        if fid == 'project_team_size':
            field['integer'] = True
        if fid == 'exam_level':
            field['label'] = '报考级别'
        if fid == 'email':
            field['label'] = '邮箱'
        if fid == 'identity_valid_until':
            field['date_markers'] = ['长期有效']
        if fid == 'is_native':
            field['boolean_values'] = ['是', '否']
        if fid == 'contact_purpose':
            field.update(widget='multi_select', options=['家庭成员', '紧急联系人', '证明人'])
    return result


def digest():
    return hashlib.sha256(json.dumps(catalog(), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def install(state):
    """Install metadata only. Called after migration, never elects current values."""
    definitions = {f['id']: f for f in catalog()}
    links = state.setdefault('profile_field_links', {})
    for spec in definitions.values():
        fid = links.get(spec['id'], spec['id'])
        field = next((f for f in state['fields'] if f['id'] == fid), None)
        if field is None:
            field = copy.deepcopy(spec)
            state['fields'].append(field)
        else:
            aliases = [] if spec['id']=='exam_level' and not field.get('display_label') else list(dict.fromkeys([*field.get('aliases', []), field['label'], *spec['aliases']]))
            field.update(copy.deepcopy(spec), id=fid, aliases=aliases)
        field['preset_id'] = spec['id']
        if field.get('display_label'):field['label']=field['display_label']
        field.pop('legacy_preserved', None)
        links[spec['id']] = fid
    from profile_schema import FIELDS as legacy
    old_ids = {f['id'] for f in legacy}
    for field in state['fields']:
        preset = next((key for key, value in links.items() if value == field['id']), field['id'])
        if field['category'] in {'social', 'preferences'} or preset in old_ids and preset not in definitions:
            field['legacy_preserved'] = True
    state['profile_record_types'] = copy.deepcopy(RECORD_TYPES)
    state['profile_catalog_hash'] = digest()
    state.setdefault('profile_relations', [])
    state.setdefault('language_exam_links', [])
    state.setdefault('profile_trash', [])
    state.setdefault('profile_pending', [])
    state.setdefault('profile_drafts', {})
    state['profile_contract'] = CONTRACT


def expression_ids(state, entry):
    return tuple(state.get('profile_field_links', {}).get(fid, fid)
                 for fid in EXPRESSIONS.get(entry['category'], ()))


def fields_for(state, entry):
    return [f for f in state['fields'] if not f.get('legacy_preserved')
            and f['category'] == entry['category']
            and (not f.get('entry_id') or f['entry_id'] == entry['id'])
            and (not f.get('record_types') or entry.get('record_type') in f['record_types'])]


def current_values(state, entry, version_id=None):
    """Exact selected expression set plus current shared facts; no blank fallback."""
    fields = fields_for(state, entry)
    expression = set(expression_ids(state, entry))
    refs = entry.get('default_versions', {})
    by_id = {v['id']: v for key in ('versions', 'answer_versions') for v in state.get(key, [])}
    values = {f['id']: by_id[refs[f['id']]]['content'] if refs.get(f['id']) in by_id
              else entry.get('values', {}).get(f['id'], '') for f in fields if f['id'] not in expression}
    selected = entry.get('profile_default_set_id') if version_id is None else version_id
    version = next((v for v in entry.get('expression_versions', []) if v['id'] == selected and not v.get('deleted_at')), None)
    for fid in expression:
        vid = (version or {}).get('field_versions', {}).get(fid)
        values[fid] = by_id[vid]['content'] if vid in by_id else ''
    return values
