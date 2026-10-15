"""Narrow compatibility for reviewed language-ability collections.

Resolve field meanings, not candidate facts. Legacy duplicate values are checked
per record; combined listening/speaking or reading/writing is never inferred.
"""
import copy

FAMILIES = {
    'language_name': {'语种', '语言', '语言类型', '语言名称'},
    'language_level': {'总体熟练程度', '熟练程度', '掌握程度'},
}
COMBINED = {'听说': '听说综合水平', '听说能力': '听说综合水平',
            '读写': '读写综合水平', '读写能力': '读写综合水平'}


def normalize(state, website, mapping):
    """Only upgrade an already scoped, unrestricted language ability module."""
    rule = mapping.get('requirement') or {}
    if (mapping.get('category') != 'language' or not website.get('collection')
            or website.get('label') not in {'语言能力', '外语能力'}
            or not rule.get('group') or rule.get('selection') != 'all'
            or rule.get('filters') or rule.get('rank') or rule.get('required_values')
            or rule.get('max_items') is not None or mapping.get('requires_records_when')):
        return
    instructions = ''.join(website.get('instructions', '').split())
    if mapping.get('status') == 'ambiguous' and instructions not in {'', website['label'], website['label'] + '添加'}:
        return  # A scope restriction in prose still needs semantic review.
    members = copy.deepcopy(mapping.get('members', []))
    if {m['website_id'] for m in members} != {c['id'] for c in website.get('children', [])}:
        return
    for child in website.get('children', []):
        member = next(m for m in members if m['website_id'] == child['id'])
        if member.get('field_id'):
            continue  # Preserve existing reviewed references and user edits.
        canonical = next((fid for fid, labels in FAMILIES.items() if child['label'] in labels), None)
        if canonical:
            fid = state.get('profile_field_links', {}).get(canonical, canonical)
            field = next((f for f in state['fields'] if f['id'] == fid and f['category'] == 'language'), None)
            if not field:
                return
            member.update(field_id=fid, new_field=None, transform=None)
            member['equivalent_fields'] = [f['id'] for f in state['fields'] if f['category'] == 'language'
                and not f.get('entry_id') and f['id'] != fid and f['label'] in FAMILIES[canonical]]
        elif child['label'] in COMBINED:
            member.update(new_field={'label': COMBINED[child['label']], 'category': 'language',
                                     'type': 'select' if child.get('options') else 'text'}, transform=None)
        else:
            return  # Do not guess object scope or unfamiliar question meanings.
    mapping.update(status='mapped', field_id=None, members=members, record_kind='language_ability',
                   reason='复用语言能力字段；同义旧字段逐记录核对，听说和读写综合评价单独补充。')


def normalize_session(state, session):
    website = session.get('website') or {}
    fields = {f['id']: f for f in website.get('fields', [])}
    for mapping in website.get('mappings', []):
        if mapping.get('website_id') in fields:
            normalize(state, fields[mapping['website_id']], mapping)


def applicable(entry, mapping):
    if mapping.get('record_kind') != 'language_ability':
        return True
    # Exam scores alone are not an ability record. Untyped historical records
    # remain eligible when they explicitly contain a language-ability fact.
    return entry.get('record_type') != 'exam' and (entry.get('record_type') == 'ability'
        or any(entry.get('values', {}).get(k) for k in ('language_name', 'language', 'language_level', 'language_proficiency')))


def value(entry, member, session, group):
    fid = member.get('field_id')
    original = entry['values'].get(fid, '')
    if not member.get('equivalent_fields') or fid not in entry['values']:
        return original, None
    if entry['id'] + '/' + str(fid) in session.get('scoped_overrides', {}).get(group, {}):
        return original, None
    values = [entry['values'].get(k, '') for k in [fid, *member.get('equivalent_fields', [])]]
    distinct = list(dict.fromkeys(v for v in values if str(v).strip()))
    if len(distinct) > 1:
        return '', '资料库同义字段内容不一致，请确认本次使用的内容'
    return (distinct[0] if distinct else original), None
