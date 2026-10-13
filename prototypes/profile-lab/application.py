"""Website requirements -> scoped record sets -> versions -> validated answers."""
import copy
import json
import re
from recognizer import RecognitionError
from lab import LabError, all_versions, default_version, find, category, put_answer, uid, validate_value
from requirements import validate_requirement, resolve_set, matches, requirement


def website_value(value, transform=None, options=None):
    """Only explicit, lossless semantic conversions from a reviewed mapping."""
    from requirements import normalized
    if not value or not transform:
        return value
    if transform == 'education_level':
        level = normalized(value, 'education_level')
        converted = {1: '初中', 2: '高中', 3: '大专', 4: '本科', 5: '硕士', 6: '博士'}.get(level, value)
        labels = [o.get('value', o.get('label')) if isinstance(o, dict) else o for o in (options or [])]
        if converted in labels:
            return converted
        # Program names such as MBA/MPAcc can establish a profile's level, but
        # are not interchangeable with a generic education-level option.
        same_level = [label for label in labels if level is not None and normalized(label, 'education_level') == level
                      and re.sub(r'\s+', '', str(label)).casefold() not in {'mba','mpacc'}]
        return same_level[0] if len(same_level) == 1 else converted
    if transform == 'academic_degree_level':
        match = re.fullmatch(r'.*(学士|硕士|博士)', str(value))
        return match.group(1) if match else value
    if transform in {'month', 'year'}:
        text = str(value)
        if re.fullmatch(r'\d{4}-\d{2}(?:-\d{2})?', text):
            return text[:7] if transform == 'month' else text[:4]
    return value


def entry_material(state, session, entry, group=None):
    values, choices = {}, []
    legacy = not group or session.get('website', {}).get('contract_version') != 2
    selected_versions = session['selected_versions'] if legacy else session.get('scoped_versions', {}).get(group, {})
    overrides = session['overrides'] if legacy else session.get('scoped_overrides', {}).get(group, {})
    for field in state['fields']:
        if field['category'] != entry['category']:
            continue
        key = entry['id'] + '/' + field['id']
        versions = all_versions(state, entry['id'], field['id'])
        selected = next((v for v in versions if v['id'] == selected_versions.get(key)), default_version(state, entry, field['id']))
        value = selected['content'] if selected else entry['values'].get(field['id'], '')
        value = overrides.get(key, overrides.get(field['id'], value) if not category(entry['category'])[2] else value)
        values[field['id']] = value
        choices.append({'field': field, 'versions': versions, 'selected': selected, 'content': value, 'key': key})
    return {'id': entry['id'], 'category': entry['category'], 'values': values, 'choices': choices}


def group_id(mapping):
    return (mapping.get('requirement') or {}).get('group') or mapping['website_id']


def value_error(value, website):
    if (website.get('required') or website.get('decision_required')) and not str(value).strip():
        return '请补充' + website['label']
    if website.get('maxLength') is not None and len(str(value)) > int(website['maxLength']):
        return website['label'] + '超过网站字数限制'
    options = website.get('options', [])
    if value and options:
        allowed = [o.get('value', o.get('label')) if isinstance(o, dict) else o for o in options]
        if value not in allowed:
            return website['label'] + '需要对应网站选项'
    return None


class Application:
    def __init__(self, lab, mapper=None):
        self.lab, self.mapper = lab, mapper

    def scan(self, session_id, manifest):
        if not re.match(r'^https?://', manifest.get('url', '')):
            raise LabError('请提供具体表单链接')
        fields = manifest.get('fields', [])
        if not fields or len(fields) > 300 or len({f['id'] for f in fields}) != len(fields):
            raise LabError('网页字段清单为空、重复或过大')
        for field in fields:
            if not isinstance(field.get('label'), str) or not field['label'].strip():
                raise LabError('网页字段必须有名称与上下文')
            children = field.get('children', [])
            if len(children) > 100 or len({c['id'] for c in children}) != len(children):
                raise LabError('集合子字段重复或过多')
        if self.mapper is None:
            raise LabError('未配置语义映射器', 503)
        try:
            output = self.mapper.map(fields, self.lab.state()['fields'])
        except RecognitionError as error:
            raise LabError(str(error), 502)
        if output.get('website_fields'):
            manifest = {**manifest, 'fields': output['website_fields']}
            fields = manifest['fields']
        try:return self.install_mapping(session_id, manifest, output)
        except LabError as error:
            # Retry a malformed semantic contract once. Never relax reference or
            # object-scope validation, and never include personal answers.
            from mapping import WebsiteMapper
            if error.status!=502 or not isinstance(self.mapper,WebsiteMapper):raise
            try:corrected=self.mapper.map(fields,self.lab.state()['fields'],str(error))
            except RecognitionError as failure:raise LabError(str(failure),502)
            return self.install_mapping(session_id,manifest,corrected)

    def install_mapping(self, session_id, manifest, output):
        """Install a model-reviewed mapping, with the same reference validation as scan."""
        fields = manifest.get('fields', [])
        if not re.match(r'^https?://', manifest.get('url', '')) or not fields or len(fields) > 300:
            raise LabError('网站字段清单无效')
        if len({f['id'] for f in fields}) != len(fields):
            raise LabError('网站字段重复')
        mappings = copy.deepcopy(output['mappings'])
        if len(mappings) != len(fields) or {m['website_id'] for m in mappings} != {f['id'] for f in fields}:
            raise LabError('模型未覆盖全部网页字段', 502)

        def save(state):
            session = find(state['sessions'], session_id)
            if session.get('form_analysis') and session['form_analysis']['url'] != manifest['url']:
                raise LabError('资料方案与已读取的招聘链接不一致')
            groups = {}
            for m in mappings:
                website = find(fields, m['website_id'])
                if m.get('transform') not in {None,'education_level','academic_degree_level','month','year'}:
                    raise LabError('不支持的字段转换',502)
                cat = m.get('category')
                definition = m.get('new_field')
                if m['status'] == 'ambiguous':
                    # A partly recognised field is diagnostic, never an executable mapping.
                    m['field_id'] = None
                    continue
                if m['status'] not in {'new', 'mapped'}:
                    raise LabError('网站对应状态无效', 502)
                if m['status'] == 'new' and not definition:
                    # Compatibility for older scalar-only manifests. No repeated scope is inferred.
                    definition = {'label': website['label'], 'category': 'additional', 'type': 'partial_date' if website.get('type') == 'date' else 'text'}
                    m['new_field'] = definition
                    cat = m['category'] = 'additional'
                if not category(cat):
                    raise LabError('未知资料分类', 502)
                dependency = m.get('requires_records_when')
                if dependency:
                    if not isinstance(dependency, dict) or set(dependency) != {'website_id', 'equals', 'message'} or not all(isinstance(v, str) for v in dependency.values()):
                        raise LabError('条件资料要求无效')
                    source_question = find(fields, dependency['website_id'])
                    if source_question.get('collection') or not website.get('collection'):
                        raise LabError('条件资料必须由单项问题决定集合')
                if 'entry_ids' in m:
                    if not isinstance(m['entry_ids'], list) or len(set(m['entry_ids'])) != len(m['entry_ids']):
                        raise LabError('语义筛选的记录无效')
                    for eid in m['entry_ids']:
                        if find(state['entries'], eid)['category'] != cat:
                            raise LabError('语义筛选引用了其他对象的记录')
                    if any(eid not in m['entry_ids'] for eid in m.get('recommended_ids', [])):
                        raise LabError('推荐记录超出已匹配范围')
                if m.get('field_id'):
                    field = find(state['fields'], m['field_id'])
                    if field['category'] != cat:
                        raise LabError('字段不属于该资料对象', 502)
                elif m['status'] == 'mapped' and not website.get('collection'):
                    raise LabError('单项字段缺少资料位置', 502)
                if definition:
                    self._check_definition(definition, cat)
                if category(cat)[2]:
                    rule = validate_requirement(m.get('requirement'), cat, state['fields'])
                    m['requirement'] = rule
                    if rule['group'] in groups and groups[rule['group']] != (cat, rule):
                        raise LabError('同一网站资料组的范围不一致', 502)
                    groups[rule['group']] = (cat, rule)
                elif m.get('requirement'):
                    raise LabError('单项资料不能套用重复记录范围', 502)
                children, members = website.get('children', []), m.setdefault('members', [])
                if {c['id'] for c in children} != {c['website_id'] for c in members} or len(children) != len(members):
                    raise LabError('未完整对应集合子字段', 502)
                for member in members:
                    if member.get('transform') not in {None, 'education_level', 'academic_degree_level', 'month', 'year'}:
                        raise LabError('不支持的字段转换')
                    if member.get('field_id'):
                        if find(state['fields'], member['field_id'])['category'] != cat:
                            raise LabError('集合子字段不属于同一对象', 502)
                    elif member.get('new_field'):
                        self._check_definition(member['new_field'], cat)
                    else:
                        raise LabError('集合子字段含义未确定', 502)
                    if member.get('required_when'):
                        validate_requirement(requirement('condition', filters=member['required_when']), cat, state['fields'])
            old_website = session.get('website', {})
            # Wording and a model's renamed group ID do not erase a user's
            # choices. Reuse the established group for the same website object.
            for m in mappings:
                previous = next((p for p in old_website.get('mappings', []) if p['website_id'] == m['website_id'] and p.get('category') == m.get('category') and p.get('requirement')), None)
                if previous and m.get('requirement'):
                    old_group, new_group = group_id(previous), group_id(m)
                    for peer in mappings:
                        if peer.get('requirement') and group_id(peer) == new_group:
                            peer['requirement']['group'] = old_group
            groups = {group_id(m): (m['category'], m['requirement']) for m in mappings if m.get('requirement')}
            old_rules = {group_id(m): m.get('requirement') for m in old_website.get('mappings', [])}
            old_fields = {f['id']:f for f in old_website.get('fields', [])}
            for mapping in mappings:
                cat=mapping.get('category')
                if not cat or category(cat)[2] or not mapping.get('field_id'):
                    continue
                label=find(fields,mapping['website_id'])['label']
                peers=[m for m in old_website.get('mappings',[]) if m.get('category')==cat and m.get('field_id')==mapping['field_id']
                       and old_fields.get(m['website_id'],{}).get('label')==label]
                if len(peers)==1 and group_id(peers[0])!=group_id(mapping):
                    for key in ('scoped_versions','scoped_overrides'):
                        if group_id(peers[0]) in session.get(key,{}):
                            session.setdefault(key,{})[group_id(mapping)]=copy.deepcopy(session[key][group_id(peers[0])])
            if old_website and old_website.get('contract_version') != 2:
                for m in mappings:
                    cat, group = m.get('category'), group_id(m)
                    if not cat or m['status'] == 'ambiguous':
                        continue
                    entries = [e for e in state['entries'] if e['category'] == cat]
                    for entry in entries:
                        for field in state['fields']:
                            if field['category'] != cat:
                                continue
                            key = entry['id'] + '/' + field['id']
                            if key in session['selected_versions']:
                                session.setdefault('scoped_versions', {}).setdefault(group, {})[key] = session['selected_versions'][key]
                            if key in session['overrides'] or (not category(cat)[2] and field['id'] in session['overrides']):
                                session.setdefault('scoped_overrides', {}).setdefault(group, {})[key] = session['overrides'].get(key, session['overrides'].get(field['id']))
                    if (m.get('requirement') or {}).get('selection') == 'choose' and cat in session.get('selected_entries', {}):
                        session.setdefault('group_choices', {}).setdefault(group, session['selected_entries'][cat])
            # Changed scopes are revalidated by resolve_set. Retain explicit
            # choices instead of silently falling back to selecting every row.
            for group, (_, rule) in groups.items():
                if old_website.get('contract_version') == 2 and group in old_rules and {k:v for k,v in old_rules[group].items() if k != 'summary'} != {k:v for k,v in rule.items() if k != 'summary'}:
                    session.setdefault('preparation', {}).pop('preview', None)
            session['website'] = {**copy.deepcopy(manifest), 'mappings': mappings, 'contract_version': 2,
                                  'engine': output.get('engine', '虚构夹具映射')}
            return session['website']
        return self.lab.mutate(save)

    @staticmethod
    def _check_definition(definition, cat):
        if definition.get('category') != cat or not definition.get('label') or definition.get('type') not in {'text', 'multiline', 'partial_date', 'date', 'number', 'select', 'versioned_text'}:
            raise LabError('新字段归属或类型无效', 502)

    def _group(self, state, session, mapping, website_fields):
        cat, rule = mapping['category'], copy.deepcopy(mapping['requirement'])
        group = rule['group']
        peers = [m for m in session['website']['mappings'] if group_id(m) == group and m.get('requirement')]
        if any(find(website_fields, m['website_id']).get('required') for m in peers):
            rule['min_items'] = max(1, rule['min_items'] or 0)
        drafts = session.get('group_drafts', {}).get(group, [])
        entries = [entry_material(state, session, e, group) for e in state['entries'] if e['category'] == cat and not e.get('application_excluded') and
                   e['id'] not in session['website'].get('excluded_entry_ids',[]) and
                   ('entry_ids' not in mapping or e['id'] in mapping['entry_ids'] or e['id'] in drafts) and
                   (e['values'] or e['id'] in drafts or any(v['entry_id'] == e['id'] for v in state['versions'] + state['answer_versions']))]
        selected, options, issues = resolve_set(entries, rule, session.get('group_choices', {}).get(group, mapping.get('recommended_ids')))
        # New rows stay editable while their scope fields are being completed.
        for entry in entries:
            if entry['id'] in drafts and entry not in selected and not any(entry['values'].values()):
                selected.append(entry)
        return selected, options, issues, rule

    def select_entries(self, session_id, cat, entry_ids, group=None):
        def select(state):
            session = find(state['sessions'], session_id)
            mappings = [m for m in session.get('website', {}).get('mappings', []) if m.get('category') == cat and m.get('requirement')]
            groups = {group_id(m) for m in mappings}
            if group is None:
                if len(groups) != 1:
                    raise LabError('请选择具体网站问题，不能按整个资料分类改动')
                target = next(iter(groups))
            else:
                target = group
            mapping = next((m for m in mappings if group_id(m) == target), None)
            if not mapping or mapping['requirement']['selection'] not in {'choose', 'one', 'highest'}:
                raise LabError('网站要求完整或指定资料，此集合不提供任意勾选')
            if len(set(entry_ids)) != len(entry_ids):
                raise LabError('经历选择重复')
            if mapping['requirement']['selection'] in {'one', 'highest'} and len(entry_ids) != 1:
                raise LabError('此问题需要确定一个对象')
            _, options, _, _ = self._group(state, session, mapping, session['website']['fields'])
            if any(eid not in {e['id'] for e in options} for eid in entry_ids):
                raise LabError('所选记录不在此网站要求的范围内')
            session.setdefault('group_choices', {})[target] = list(entry_ids)
            # Legacy consumers may read this only when there is one question for the category.
            if len(groups) == 1:
                session.setdefault('selected_entries', {})[cat] = list(entry_ids)
            return session
        return self.lab.mutate(select)

    def plan(self, session_id):
        state = self.lab.state()
        session = find(state['sessions'], session_id)
        website = session.get('website')
        result = {'website': website, 'decisions': [], 'automatic': [], 'missing': [], 'payload': [], 'session': session}
        if not website:
            return result
        if website.get('contract_version') != 2:
            first = website['fields'][0]
            self._missing(result, {'website_field': first, 'mapping': {'status': 'ambiguous'}, 'group_id': first['id']},
                          '填写逻辑已更新，请重新读取网站要求；已保存资料与本次编辑会保留', kind='scan')
            result['ready'] = False
            return result
        emitted = set()
        for m in website['mappings']:
            field = find(website['fields'], m['website_id'])
            group = group_id(m)
            item = {'website_field': field, 'mapping': m, 'group_id': group}
            if m['status'] == 'ambiguous':
                self._missing(result, item, m.get('reason') or '网站问题含义尚未确定', editable=False)
                continue
            cat = m.get('category') or 'additional'
            if category(cat)[2] and not m.get('requirement'):
                self._missing(result, item, '旧扫描没有资料范围，请重新读取网站要求', editable=False)
                continue
            if category(cat)[2]:
                selected, options, issues, rule = self._group(state, session, m, website['fields'])
                item.update(category=cat, selected=selected, options=options, requirement=rule)
                # Eligibility must never silently hide a record or its versions.
                eligible={e['id'] for e in options}
                item['catalog']=[]
                for stored in state['entries']:
                    if stored['category']!=cat or stored['id'] in website.get('excluded_entry_ids',[]) or stored.get('application_excluded'):
                        continue
                    material=entry_material(state,session,stored,group)
                    if not any(material['values'].values()):continue
                    unknown=[i['field_id'] for i in issues if i.get('entry_id')==stored['id'] and i.get('field_id')]
                    material['eligibility']='eligible' if stored['id'] in eligible else 'needs_scope' if unknown else 'outside_scope'
                    material['scope_fields']=unknown
                    material['scope_message']='请补充经历性质或范围资料后选择' if unknown else '不在本网站要求范围内' if stored['id'] not in eligible else ''
                    item['catalog'].append(material)
                for issue in issues:
                    signature = (group, json.dumps(issue, sort_keys=True, ensure_ascii=False))
                    if signature not in emitted:
                        emitted.add(signature)
                        self._missing(result, item, issue['message'], issue.get('entry_id'), issue.get('field_id'),
                                      editable=bool(issue.get('entry_id') and issue.get('field_id')), kind=issue['kind'])
                if rule['selection'] in {'one', 'highest'} and len(options) > 1 and not field.get('collection'):
                    result['decisions'].append(item)
                if field.get('collection'):
                    item['value'] = []
                    for entry in selected:
                        projected = {}
                        choices = []
                        members = m.get('members') or [{'website_id': f['id'], 'field_id': f['id']} for f in state['fields'] if f['category'] == cat]
                        for member in members:
                            child = next((c for c in field.get('children', []) if c['id'] == member['website_id']), None)
                            fid = member.get('field_id')
                            child = child or {'id': member['website_id'], 'label': find(state['fields'], fid)['label']}
                            value = entry['values'].get(fid, '')
                            if not fid:
                                value = session.get('new_answers', {}).get(group + '/' + entry['id'] + '/' + child['id'], '')
                            value = website_value(value, member.get('transform'), child.get('options'))
                            key = fid or child['id']
                            projected[key] = value
                            choice = next((c for c in entry['choices'] if c['field']['id'] == fid), None)
                            if choice:
                                choices.append({**choice, 'website_id': field['id'], 'child_id': child['id'], 'group_id': group})
                            constraints = dict(child)
                            conditions = member.get('required_when', [])
                            evaluations = [matches(entry, c) for c in conditions]
                            if conditions:
                                constraints['required'] = all(v is True for v in evaluations)
                            if conditions and not any(v is False for v in evaluations):
                                for c, outcome in zip(conditions, evaluations):
                                    if outcome is None:
                                        self._missing(result, item, '需补充条件判断资料', entry['id'], c['field_id'], editable=True, kind='scope')
                            error = value_error(value, constraints)
                            if value and child.get('type') in {'month', 'year'} and not re.fullmatch(r'\d{4}-\d{2}' if child['type'] == 'month' else r'\d{4}', str(value)):
                                error = child['label'] + '需要明确的' + ('年月' if child['type'] == 'month' else '年份')
                            if error:
                                self._missing(result, item, error, entry['id'], fid, child['id'], True, blocking=bool(constraints.get('required')))
                            elif not fid:
                                self._missing(result, item, '可选补充：' + child['label'], entry['id'], None, child['id'], True)
                        entry['answer_choices'] = choices
                        entry['answer_values'] = projected
                        item['value'].append(projected)
                    bucket = 'decisions' if rule['selection'] == 'choose' or (rule['selection'] in {'one', 'highest'} and len(options) > 1) else 'automatic'
                    result[bucket].append(item)
                    if not issues and not any(x['website_field']['id'] == field['id'] for x in result['missing']):
                        result['payload'].append(item)
                    continue
                index = field.get('row_index')
                if index is None and len(selected) != 1:
                    if not issues:
                        self._missing(result, item, '尚不能确定此问题对应哪一条记录', editable=False)
                    continue
                if not selected or (index is not None and (type(index) is not int or not 0 <= index < len(selected))):
                    if not issues:
                        self._missing(result, item, '缺少此问题对应的资料记录', editable=False, kind='count')
                    continue
                entry = selected[index or 0]
            else:
                entry = next((entry_material(state, session, e, group) for e in state['entries'] if e['category'] == cat and e['id'] not in website.get('excluded_entry_ids',[])), None)
            fid = m.get('field_id')
            choice = next((c for c in entry['choices'] if c['field']['id'] == fid), None) if entry else None
            value = choice['content'] if choice else session.get('new_answers', {}).get(group + '/' + (entry['id'] if entry else '') + '/' + field['id'], '')
            value = website_value(value,m.get('transform'),field.get('options'))
            item.update(value=value, choice=choice, entry_id=entry['id'] if entry else None)
            error = value_error(value, field)
            if error or (m['status'] == 'new' and not value):
                self._missing(result, item, error or ('请确认：' if field.get('decision_required') else '补充（可留空）：') + field['label'], item['entry_id'], fid, editable=True, blocking=bool(field.get('decision_required')))
            elif not any(x['group_id'] == group for x in result['missing']):
                result['automatic'].append(item)
                result['payload'].append(item)
        for item in result['automatic'] + result['decisions']:
            dependency = item['mapping'].get('requires_records_when')
            if dependency and not item.get('selected'):
                answer = next((i.get('value') for i in result['automatic'] if i['website_field']['id'] == dependency['website_id']), None)
                if answer == dependency['equals']:
                    self._missing(result, item, dependency['message'], kind='count')
        result['ready'] = not any(i['blocking'] for i in result['missing'])
        # Session-only answers never become shared facts implicitly. Offer the
        # exact previously confirmed answer for this same object, not a blank
        # repeat question or an answer borrowed from another education record.
        for item in result['missing']:
            fid, eid = item.get('field_id'), item.get('entry_id')
            definition = next((f for f in state['fields'] if f['id'] == fid), None)
            if not definition or definition['type'] in {'versioned_text', 'multiline'} or not eid:
                continue
            answers = set()
            for previous in state['sessions']:
                if previous['id'] == session_id:
                    continue
                confirmed = previous.get('preparation', {}).get('execution', {}).get('confirmed_materials', {})
                for row in confirmed.get('rows', []):
                    values = [v for record in row.get('records', []) for v in record['values']] if 'records' in row else [row]
                    for value in values:
                        ref = value.get('source_ref', {})
                        if ref.get('entry_id') == eid and ref.get('field_id') == fid and value.get('value'):
                            answers.add(str(value['value']))
            site = next((c for c in item['website_field'].get('children', []) if c['id'] == item.get('child_id')), item['website_field'])
            member = next((m for m in item['mapping'].get('members', []) if m['website_id'] == item.get('child_id')), item['mapping'])
            answers = {website_value(answer, member.get('transform'), site.get('options')) for answer in answers}
            if len(answers) == 1:
                answer = next(iter(answers))
                if not value_error(answer, site):
                    item['previous_answer'] = answer
        return result

    @staticmethod
    def _missing(result, item, message, entry_id=None, field_id=None, child_id=None, editable=False, kind='value', blocking=False):
        result['missing'].append({**item, 'message': message, 'entry_id': entry_id, 'field_id': field_id,
                                  'child_id': child_id, 'editable': editable, 'kind': kind,
                                  'blocking': blocking or bool(item['website_field'].get('required')) or kind != 'value'})

    def add_entry(self, session_id, website_id):
        def add(state):
            session = find(state['sessions'], session_id)
            m = next((m for m in session['website']['mappings'] if m['website_id'] == website_id), None)
            if m is None:
                raise LabError('网站问题不存在')
            if not m.get('requirement') or not category(m['category'])[2]:
                raise LabError('此问题不支持新增资料记录')
            entry = self.lab.new_entry(state, m['category'])
            group = group_id(m)
            session.setdefault('group_drafts', {}).setdefault(group, []).append(entry['id'])
            return entry
        return self.lab.mutate(add)

    def _answer_target(self, state, session, website_id, entry_id=None, field_id=None, child_id=None):
        website = find(session['website']['fields'], website_id)
        mapping = next(m for m in session['website']['mappings'] if m['website_id'] == website_id)
        if mapping['status'] == 'ambiguous':
            raise LabError('请先明确网站问题的资料范围，不能保存任意文本代替')
        member, constraint = mapping, website
        if website.get('collection'):
            if child_id:
                member = next((c for c in mapping.get('members', []) if c['website_id'] == child_id), None)
                constraint = find(website.get('children', []), child_id) if website.get('children') else None
            else:
                member = next((c for c in mapping.get('members', []) if c.get('field_id') == field_id), None)
                constraint = None
            if member is None:
                # Scope facts can also need completion, even when not requested as a visible child.
                scope_fields = {c['field_id'] for c in (mapping.get('requirement') or {}).get('filters', [])}
                scope_fields |= {c['field_id'] for c in (mapping.get('requirement') or {}).get('required_values', [])}
                scope_fields |= {c['field_id'] for member in mapping.get('members', []) for c in member.get('required_when', [])}
                if mapping.get('requirement', {}).get('rank'):
                    scope_fields.add(mapping['requirement']['rank']['field_id'])
                if field_id not in scope_fields and mapping.get('members'):
                    raise LabError('字段不属于本次问题')
                member = {'field_id': field_id}
            constraint = constraint or {'id': field_id, 'label': find(state['fields'], field_id)['label']}
        cat = mapping.get('category') or 'additional'
        if category(cat)[2]:
            if not entry_id:
                selected, _, _, _ = self._group(state, session, mapping, session['website']['fields'])
                index = website.get('row_index')
                if len(selected) == 1:
                    entry_id = selected[0]['id']
                elif type(index) is int and 0 <= index < len(selected):
                    entry_id = selected[index]['id']
                else:
                    raise LabError('请明确要修改的资料记录')
            entry = find(state['entries'], entry_id)
            if entry['category'] != cat:
                raise LabError('答案不属于此资料对象')
            selected, options, issues, _ = self._group(state, session, mapping, session['website']['fields'])
            permitted = {e['id'] for e in selected + options} | {i.get('entry_id') for i in issues}
            permitted |= set(session.get('group_drafts', {}).get(group_id(mapping), []))
            if entry_id not in permitted:
                raise LabError('此记录不属于该网站问题的范围')
        else:
            entry = self.lab.new_entry(state, cat)
        fid = member.get('field_id')
        definition = find(state['fields'], fid) if fid else None
        return mapping, member, constraint, entry, definition

    def select_version(self, session_id, website_id, version_id, entry_id=None, field_id=None, child_id=None):
        def select(state):
            session = find(state['sessions'], session_id)
            m, member, website, entry, field = self._answer_target(state, session, website_id, entry_id, field_id, child_id)
            if not field:
                raise LabError('此字段尚无版本')
            version = find(all_versions(state, entry['id'], field['id']), version_id)
            key = entry['id'] + '/' + field['id']
            group = group_id(m)
            session.setdefault('scoped_versions', {}).setdefault(group, {})[key] = version['id']
            session.setdefault('scoped_overrides', {}).setdefault(group, {}).pop(key, None)
            return session
        return self.lab.mutate(select)

    def edit_answer(self, session_id, website_id, value, mode, version_id=None, expected_revision=None, name='', entry_id=None, field_id=None, child_id=None):
        if mode not in {'update', 'new', 'session'}:
            raise LabError('未知保存方式')
        def save(state):
            session = find(state['sessions'], session_id)
            m, member, website, entry, field = self._answer_target(state, session, website_id, entry_id, field_id, child_id)
            error = value_error(website_value(value, member.get('transform'),website.get('options')), {**website, 'required': False})
            if error:
                raise LabError(error)
            if field is None:
                definition = member.get('new_field') or {'label': website['label'], 'category': entry['category'], 'type': 'text'}
                self._check_definition(definition, entry['category'])
                field = next((f for f in state['fields'] if f['category'] == entry['category'] and f['label'] == definition['label']), None)
                if field is None:
                    options = [o.get('value', o.get('label')) if isinstance(o, dict) else o for o in website.get('options', [])]
                    # Unopened custom dropdowns expose no domain. Store the user
                    # fact as text; the executor must still check real options.
                    if definition['type'] == 'select' and not options:
                        definition = {**definition, 'type': 'text'}
                    field = {'id': uid('website'), **definition, 'aliases': [], 'options': options}
                    state['fields'].append(field)
                elif field['id'].startswith('website_') and field['type'] == 'select' and not field.get('options') and not all_versions(state, entry['id'], field['id']):
                    field['type'] = 'text'
                member['field_id'] = field['id']
                if member is m:
                    m.update(status='mapped', category=field['category'])
            validate_value(field, value)
            versions = all_versions(state, entry['id'], field['id'])
            version = find(versions, version_id) if version_id else default_version(state, entry, field['id'])
            if mode == 'update' and version and expected_revision is not None and version['revision'] != expected_revision:
                raise LabError('此版本已经更新，请刷新后重新编辑', 409)
            key, group = entry['id'] + '/' + field['id'], group_id(m)
            overrides = session.setdefault('scoped_overrides', {}).setdefault(group, {})
            if mode == 'session':
                overrides[key] = value
            else:
                target = put_answer(state, entry, field, value, 'replace' if mode == 'update' else 'new',
                                    version['id'] if version else None, name=name or '官网补充版本')
                session.setdefault('scoped_versions', {}).setdefault(group, {})[key] = target['id']
                overrides.pop(key, None)
            return {'field': field, 'mode': mode, 'entry_id': entry['id']}
        return self.lab.mutate(save)
