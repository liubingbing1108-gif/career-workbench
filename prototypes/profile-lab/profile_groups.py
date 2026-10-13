"""Read-only profile sets, using the same resolver as website applications.

Sets contain references to canonical entries; they never copy facts or versions.
These named presets explain common education scopes, not a website requirement.
An actual application still uses its scanned requirement contract.
"""
from lab import default_version
from requirements import requirement, resolve_set, normalized


def education_presets():
    result = []
    for key, title, level in [('college', '本科起填', '本科'),
                              ('high-school', '高中起填', '高中')]:
        rule = requirement('profile:education:' + key,
            summary='网站要求从' + level + '开始，包含此后的全部教育经历。',
            filters=[dict(field_id='degree', domain='education_level', op='gte', values=[level])],
            rank=dict(field_id='degree', domain='education_level', direction='asc'),
            required_values=[dict(field_id='degree', domain='education_level', op='in', values=[level])])
        result.append(dict(id=key, label=title, requirement=rule))
    return result


def profile_groups(state):
    groups = []
    for category in state['categories']:
        if not category['repeatable']:
            continue
        fields = [f for f in state['fields'] if f['category'] == category['id']]
        entries = []
        for entry in state['entries']:
            if entry['category'] != category['id']:
                continue
            values = dict(entry['values'])
            for field in fields:
                version = default_version(state, entry, field['id'])
                if version:
                    values[field['id']] = version['content']
            entries.append(dict(id=entry['id'], values=values))
        group = dict(category=category['id'], label=category['label'],
                     entry_ids=[e['id'] for e in entries], sets=[])
        if category['id'] == 'education':
            for preset in education_presets():
                selected, _, issues = resolve_set(entries, preset['requirement'])
                levels = sorted({normalized(e['values'].get('degree'), 'education_level') for e in selected})
                group['sets'].append(dict(**preset, entry_ids=[e['id'] for e in selected],
                    composition='＋'.join({2:'高中', 3:'专科', 4:'本科', 5:'硕士', 6:'博士'}[v] for v in levels),
                    issues=issues))
            included = {eid for s in group['sets'] for eid in s['entry_ids']}
            group['unassigned_ids'] = [e['id'] for e in entries if e['id'] not in included]
        groups.append(group)
    return groups
