"""Execute semantic requirement contracts against confirmed profile records.

The mapper interprets the website; this module never guesses a site's scope from
its category. Unknown profile facts stay unknown instead of being filtered out.
"""
import copy
import re
import calendar
from datetime import date
from lab import LabError


DOMAINS = {'text', 'number', 'date', 'education_level', 'employment_type', 'study_status'}
OPS = {'in', 'not_in', 'gte', 'lte', 'exists'}
LEVELS = {
    '初中': 1, 'juniorhigh': 1, '高中': 2, '普通高中': 2, '中专': 2, 'highschool': 2,
    'high_school': 2, '专科': 3, '大专': 3, 'juniorcollege': 3, 'associate': 3,
    '本科': 4, '大学本科': 4, '学士': 4, 'bachelor': 4, "bachelor's": 4,
    '硕士': 5, '硕士研究生': 5, '研究生(硕士)': 5, 'master': 5, "master's": 5,
    'mpacc': 5, 'mba': 5, '博士': 6, '博士研究生': 6, 'doctor': 6, 'phd': 6,
}


def normalized(value, domain):
    text = re.sub(r'\s+', '', str(value or '')).casefold().replace('（', '(').replace('）', ')')
    if not text:
        return None
    if domain == 'education_level':
        return LEVELS.get(text)
    if domain == 'employment_type':
        return {'实习': 'internship', '实习生': 'internship', 'intern': 'internship',
                'internship': 'internship', '全职': 'full_time', '正式': 'full_time',
                '正式工作': 'full_time', 'fulltime': 'full_time', 'full-time': 'full_time',
                'full_time': 'full_time', '兼职': 'part_time', 'parttime': 'part_time',
                'part-time': 'part_time', 'part_time': 'part_time'}.get(text)
    if domain == 'study_status':
        return {'在读': 'current', 'current': 'current', 'studying': 'current',
                '已毕业': 'completed', '毕业': 'completed', '已取得': 'completed',
                'completed': 'completed', 'graduated': 'completed'}.get(text)
    if domain == 'number':
        try:
            value = float(text)
            return value if abs(value) != float('inf') and value == value else None
        except ValueError:
            return None
    if domain == 'date':
        if text in {'至今', 'present', 'current', 'today'}:
            return date.today().isoformat()
        if re.fullmatch(r'\d{4}(?:-\d{2})?(?:-\d{2})?', text):
            try:
                date_bounds(text)
                return text
            except ValueError:
                pass
        return None
    return text


def requirement(group, selection='all', **kwargs):
    """A contract constructor also used by explicit offline test fixtures."""
    return {'group': group, 'selection': selection, 'summary': '', 'filters': [],
            'rank': None, 'required_values': [], 'min_items': None, 'max_items': None,
            **kwargs}


def validate_requirement(raw, category_id, fields):
    if not isinstance(raw, dict):
        raise LabError('缺少网站资料范围，请重新读取网站要求', 409)
    rule = requirement(raw.get('group'), **{k: v for k, v in raw.items() if k != 'group'})
    if not isinstance(rule['group'], str) or not re.fullmatch(r'[\w:.-]{1,100}', rule['group']):
        raise LabError('网站资料组标识无效', 502)
    if rule['selection'] not in {'all', 'choose', 'one', 'highest'}:
        raise LabError('网站资料集合取用方式无效', 502)
    if not isinstance(rule['summary'], str) or len(rule['summary']) > 1000:
        raise LabError('网站要求摘要无效', 502)
    for bound in ('min_items', 'max_items'):
        value = rule[bound]
        if value is not None and (type(value) is not int or not 0 <= value <= 200):
            raise LabError('网站经历条数无效', 502)
    if rule['min_items'] is not None and rule['max_items'] is not None and rule['min_items'] > rule['max_items']:
        raise LabError('网站最少条数大于最多条数', 502)

    def check_ref(part):
        field = next((f for f in fields if f['id'] == part.get('field_id') and f['category'] == category_id), None)
        if not field or part.get('domain') not in DOMAINS:
            raise LabError('网站范围引用了未知资料字段或含义', 502)
    for key in ('filters', 'required_values'):
        if not isinstance(rule[key], list) or len(rule[key]) > 30:
            raise LabError('网站范围条件格式无效', 502)
        for condition in rule[key]:
            check_ref(condition)
            if condition.get('op') not in OPS or not isinstance(condition.get('values'), list):
                raise LabError('网站范围条件无效', 502)
            if condition['op'] != 'exists' and (not condition['values'] or any(not isinstance(v, str) or normalized(v, condition['domain']) is None for v in condition['values'])):
                raise LabError('网站范围条件的值无法解释', 502)
    if rule['rank'] is not None:
        check_ref(rule['rank'])
        if rule['rank'].get('direction') not in {'asc', 'desc'}:
            raise LabError('网站记录顺序无效', 502)
    if rule['selection'] == 'highest' and not rule['rank']:
        raise LabError('最高记录需要明确比较依据', 502)
    return copy.deepcopy(rule)


def matches(entry, condition):
    raw = entry['values'].get(condition['field_id'], '')
    if condition['op'] == 'exists':
        return bool(str(raw).strip())
    value = normalized(raw, condition['domain'])
    if value is None:
        return None
    values = [normalized(v, condition['domain']) for v in condition['values']]
    if condition['domain'] == 'date' and condition['op'] in {'gte', 'lte'}:
        low, high = date_bounds(value)
        threshold_low, threshold_high = date_bounds(values[0])
        if condition['op'] == 'gte':
            return True if low >= threshold_low else False if high < threshold_low else None
        return True if high <= threshold_high else False if low > threshold_high else None
    if condition['op'] == 'in':
        return value in values
    if condition['op'] == 'not_in':
        return value not in values
    if condition['op'] == 'gte':
        return value >= values[0]
    return value <= values[0]


def date_bounds(value):
    parts = [int(p) for p in value.split('-')]
    year = parts[0]
    if len(parts) == 1:
        return date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat()
    month = parts[1]
    if len(parts) == 2:
        return date(year, month, 1).isoformat(), date(year, month, calendar.monthrange(year, month)[1]).isoformat()
    return date(*parts).isoformat(), date(*parts).isoformat()


def resolve_set(entries, rule, selected_ids=None):
    eligible, issues = [], []
    for entry in entries:
        results = [(condition, matches(entry, condition)) for condition in rule['filters']]
        if any(result is False for _, result in results):
            continue
        unknown = [c['field_id'] for c, result in results if result is None]
        if unknown:
            issues.extend({'kind': 'scope', 'entry_id': entry['id'], 'field_id': fid,
                           'message': '缺少或无法理解范围判断所需资料'} for fid in unknown)
            continue
        eligible.append(entry)
    rank = rule['rank']
    if rank:
        known = []
        for entry in eligible:
            value = normalized(entry['values'].get(rank['field_id']), rank['domain'])
            if value is None:
                issues.append({'kind': 'scope', 'entry_id': entry['id'], 'field_id': rank['field_id'], 'message': '无法确定此记录的等级或顺序'})
            else:
                known.append((entry, value))
        known.sort(key=lambda pair: pair[1], reverse=rank['direction'] == 'desc')
        eligible = [e for e, _ in known]
        if rule['selection'] == 'highest' and known:
            best = known[0][1]
            eligible = [e for e, value in known if value == best]
    for condition in rule['required_values']:
        if not any(matches(e, condition) is True for e in eligible):
            issues.append({'kind': 'coverage', 'field_id': condition['field_id'],
                           'message': '网站要求的资料尚缺：' + '／'.join(condition['values']), 'condition': condition})
    if rule['selection'] in {'choose', 'one', 'highest'}:
        if selected_ids is None:
            selected = eligible[:rule['max_items']] if rule['selection'] == 'choose' and rule['max_items'] is not None else eligible
        else:
            by_id = {e['id']: e for e in eligible}
            selected = [by_id[eid] for eid in selected_ids if eid in by_id]
            if any(eid not in by_id for eid in selected_ids):
                issues.append({'kind': 'selection', 'message': '网站范围已变化，请重新确认所选记录'})
    else:
        selected = eligible
    if selected_ids is not None:
        for condition in rule['required_values']:
            if not any(matches(e, condition) is True for e in selected) and not any(i.get('condition') == condition for i in issues):
                issues.append({'kind': 'coverage', 'field_id': condition['field_id'], 'condition': condition,
                               'message': '所选资料没有覆盖网站要求：' + '／'.join(condition['values'])})
    if rule['selection'] in {'one', 'highest'} and len(selected) > 1:
        issues.append({'kind': 'ambiguous', 'message': '符合该问题的记录仍有多条，需要确定具体对象'})
    minimum = rule['min_items'] or 0
    maximum = rule['max_items']
    if len(selected) < minimum:
        issues.append({'kind': 'count', 'message': f'网站至少需要 {minimum} 条资料，当前只有 {len(selected)} 条'})
    if maximum is not None and len(selected) > maximum:
        issues.append({'kind': 'count', 'message': f'网站最多允许 {maximum} 条，要求范围内有 {len(selected)} 条，不能自动截掉必要资料'})
    return selected, eligible, issues
