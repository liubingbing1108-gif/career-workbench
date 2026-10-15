from profile_schema import available as profile_available
from profile_hierarchy import visible as profile_field_visible
"""Atomic record versions and website-module compositions over existing field versions."""
import copy
from lab import LabError, find, all_versions, default_version, put_answer, validate_value, uid


def record_versions(state, entry):
    fields = [f for f in state['fields'] if f['category'] == entry['category'] and (not f.get('entry_id') or f['entry_id']==entry['id'])]
    defaults = {f['id']: (default_version(state, entry, f['id']) or {}).get('id') for f in fields}
    result = [copy.deepcopy(entry.get('profile_base_version') or dict(id='default', name='版本1', field_versions=defaults))]
    # Legacy field variants remain accessible without inventing combinations
    # between independently versioned facts.
    for field in fields:
        for version in all_versions(state, entry['id'], field['id']):
            if version['id'] != defaults[field['id']]:
                result.append(dict(id='field:' + version['id'], name=field['label'] + ' · ' + version['name'],
                                   field_versions={**defaults, field['id']: version['id']},profile_deleted=bool(version.get('profile_deleted'))))
    result.extend(copy.deepcopy(entry.get('set_versions', [])))
    return result


class MaterialSets:
    def __init__(self, application):
        self.app, self.lab = application, application.lab

    def target(self, state, sid, wid):
        session = find(state['sessions'], sid)
        from language_mapping import normalize_session
        normalize_session(state, session)
        website = find(session['website']['fields'], wid)
        mapping = next(m for m in session['website']['mappings'] if m['website_id'] == wid)
        if not website.get('collection') or mapping['status'] == 'ambiguous' or not mapping.get('category'):
            raise LabError('请先确定这个模块对应的资料组')
        return session, mapping, mapping['requirement']['group']

    def records(self, state, session, mapping):
        cat = mapping['category']
        return [e for e in state['entries'] if e['category'] == cat and profile_available(e,session) and not e.get('application_excluded')
                and e['id'] not in session['website'].get('excluded_entry_ids', [])]

    def snapshot(self, state, session, mapping, group, entry):
        from application import entry_material
        material = entry_material(state, session, entry, group)
        return {c['field']['id']: c['content'] for c in material['choices']}

    def decorate(self, state, plan):
        session = plan['session']
        for item in plan['automatic'] + plan['decisions']:
            if not item['website_field'].get('collection'):
                continue
            group = item['group_id']
            hidden_compositions = session.get('material_controls', {}).get('hidden_compositions', {}).get(group, [])
            item['composition_versions'] = [v for v in session.get('composition_versions', {}).get(group, []) if v['id'] not in hidden_compositions]
            item['hidden_composition_count'] = len(hidden_compositions)
            item['selected_composition'] = session.get('selected_compositions', {}).get(group, '')
            selected_composition = next((v for v in item['composition_versions'] if v['id'] == item['selected_composition']), None)
            if selected_composition and selected_composition['records'] != [dict(entry_id=e['id'], values=e['values']) for e in item['selected']]:
                item['selected_composition'] = ''
            for material in item['selected'] + item.get('catalog', []):
                entry = find(state['entries'], material['id'])
                hidden=session.get('material_controls',{}).get('hidden_versions',{}).get(group+'/'+entry['id'],[])
                pinned=session.get('selected_sets',{}).get(group,{}).get(entry['id'])
                material['set_versions'] = [v for v in record_versions(state, entry) if not v['id'].startswith('field:') and v['id'] not in hidden and (v['id']==pinned or (not v.get('profile_deleted') and v['id'] not in entry.get('profile_deleted_sets',[])))]
                material['hidden_version_count']=len(hidden)
                current = {c['field']['id']: c['content'] for c in material['choices']}
                selected = session.get('selected_sets', {}).get(group, {}).get(entry['id'])
                matching = []
                for version in material['set_versions']:
                    values = self.version_values(state, entry, version)
                    if all(current.get(k, '') == v for k, v in values.items()):
                        matching.append(version['id'])
                material['selected_set'] = selected if selected in matching else (matching[0] if matching else '')

    @staticmethod
    def version_values(state, entry, version):
        result = {}
        for field in state['fields']:
            if field['category'] != entry['category'] or (field.get('entry_id') and field['entry_id']!=entry['id']):
                continue
            vid = version['field_versions'].get(field['id'])
            result[field['id']] = find(all_versions(state, entry['id'], field['id']), vid)['content'] if vid else ''
        return result

    def apply_version(self, state, session, group, entry, version):
        ids = session.setdefault('scoped_versions', {}).setdefault(group, {})
        overrides = session.setdefault('scoped_overrides', {}).setdefault(group, {})
        for fid, value in self.version_values(state, entry, version).items():
            key = entry['id'] + '/' + fid
            vid = version['field_versions'].get(fid)
            if vid:
                ids[key] = vid
                overrides.pop(key, None)
            else:
                ids.pop(key, None)
                overrides[key] = value
        session.setdefault('selected_sets', {}).setdefault(group, {})[entry['id']] = version['id']
        session.setdefault('selected_compositions', {}).pop(group, None)
        session.setdefault('preparation', {}).pop('preview', None)

    def select(self, sid, wid, eid, vid):
        def change(state):
            session, mapping, group = self.target(state, sid, wid)
            entry = find(self.records(state, session, mapping), eid)
            self.apply_version(state, session, group, entry, find(record_versions(state, entry), vid))
        return self.lab.mutate(change)

    def save_in_state(self, state, session, mapping, group, data, mode, name):
        entry = find(self.records(state, session, mapping), data['entry_id'])
        fields = [f for f in state['fields'] if f['category'] == entry['category'] and profile_field_visible(state,entry,f['id'],session)]
        values = data.get('values')
        if not isinstance(values, dict) or set(values) != {f['id'] for f in fields}:
            raise LabError('资料组字段已变化，请重新打开完整表单', 409)
        from profile_group_versions import enabled as versions_enabled
        if not versions_enabled(state,entry):mode='session'
        current = self.snapshot(state, session, mapping, group, entry)
        if data.get('expected_values') != current:
            raise LabError('这组资料已在其他页面更改，请保留草稿并重新核对', 409)
        # Validate the complete set before changing anything; empty is valid.
        for field in fields:
            validate_value(field, values[field['id']])
        if mode=='session':
            for fid,value in values.items():session.setdefault('scoped_overrides',{}).setdefault(group,{})[entry['id']+'/'+fid]=value
            session.setdefault('selected_sets',{}).setdefault(group,{}).pop(entry['id'],None)
        else:
            if mode=='update':
                for field in fields:
                    fid=field['id'];vid=session.get('scoped_versions',{}).get(group,{}).get(entry['id']+'/'+fid)
                    version=find(all_versions(state,entry['id'],fid),vid) if vid else default_version(state,entry,fid)
                    if version and data.get('revisions',{}).get(fid)!=version['revision']:raise LabError('此资料组已经更新，请保留草稿后重新核对',409)
            from profile_group_versions import save_group
            selected=session.get('selected_sets',{}).get(group,{}).get(entry['id']) or entry.get('profile_default_set_id','default')
            if selected.startswith('field:'):selected=entry.get('profile_default_set_id','default')
            saved=save_group(state,entry,values,mode=mode,set_id=selected,name=name if mode=='new' else '')
            self.apply_version(state,session,group,entry,saved)
        session.setdefault('selected_compositions', {}).pop(group, None)
        session.setdefault('preparation', {}).pop('preview', None)
        return entry['id']

    def save(self, sid, wid, records, mode='session', name='', composition=False):
        if mode not in {'session', 'update', 'new'} or not isinstance(records, list) or not records:
            raise LabError('请选择要保存的资料组和保存方式')
        if len({r.get('entry_id') for r in records}) != len(records):
            raise LabError('资料组不能重复')
        name = name.strip() or '新版本'
        if len(name) > 180:
            raise LabError('版本名称过长')
        def change(state):
            session, mapping, group = self.target(state, sid, wid)
            ids = [self.save_in_state(state, session, mapping, group, r, mode, name) for r in records]
            if composition:
                # Store the entire confirmed composition, including intentional blanks.
                saved = dict(id=uid('composition'), name=name, records=[dict(entry_id=eid,
                    values=self.snapshot(state, session, mapping, group, find(state['entries'], eid))) for eid in ids])
                session.setdefault('composition_versions', {}).setdefault(group, []).append(saved)
                session.setdefault('selected_compositions', {})[group] = saved['id']
            return dict(entry_ids=ids)
        return self.lab.mutate(change)

    def select_composition(self, sid, wid, vid):
        def change(state):
            session, mapping, group = self.target(state, sid, wid)
            version = find(session.get('composition_versions', {}).get(group, []), vid)
            records = self.records(state, session, mapping)
            overrides = session.setdefault('scoped_overrides', {}).setdefault(group, {})
            for record in version['records']:
                entry = find(records, record['entry_id'])
                for field in state['fields']:
                    if field['category'] == entry['category'] and profile_field_visible(state,entry,field['id'],session):
                        overrides[entry['id'] + '/' + field['id']] = record['values'].get(field['id'], '')
            if mapping['requirement']['selection'] in {'all', 'choose', 'one', 'highest'}:
                ids = [r['entry_id'] for r in version['records']]
                session.setdefault('group_choices', {})[group] = ids
            # Scope, coverage and count requirements are revalidated in the plan.
            session.setdefault('selected_compositions', {})[group] = vid
            session.setdefault('preparation', {}).pop('preview', None)
        return self.lab.mutate(change)

    def control(self, sid, wid, action, entry_id=None, version_id=None, included=None):
        """Only this application's controls; never delete shared records/files."""
        def change(state):
            session = find(state['sessions'], sid)
            website = find(session['website']['fields'], wid)
            mapping = next(m for m in session['website']['mappings'] if m['website_id'] == wid)
            group = (mapping.get('requirement') or {}).get('group', wid)
            controls = session.setdefault('material_controls', {})
            if action in {'include', 'remove-module', 'restore-module'}:
                omitted = set(controls.get('omitted', [])); removed = set(controls.get('removed_modules', []))
                if action == 'include':
                    if type(included) is not bool:raise LabError('请选择本次是否使用')
                    omitted.discard(wid) if included else omitted.add(wid)
                    if included:removed.discard(wid)
                elif action == 'remove-module':omitted.add(wid);removed.add(wid)
                else:omitted.discard(wid);removed.discard(wid)
                controls.update(omitted=sorted(omitted), removed_modules=sorted(removed))
            elif action in {'remove-record', 'restore-record'}:
                if not website.get('collection'):raise LabError('此模块没有重复记录')
                entry = find(self.records(state, session, mapping), entry_id)
                removed = set(controls.setdefault('removed_records', {}).get(group, []))
                removed.add(entry['id']) if action == 'remove-record' else removed.discard(entry['id'])
                controls['removed_records'][group] = sorted(removed)
                choices = session.get('group_choices', {}).get(group)
                if choices is not None and action == 'remove-record':
                    session['group_choices'][group] = [eid for eid in choices if eid != entry_id]
            elif action in {'remove-version', 'restore-versions'}:
                if not website.get('collection'):raise LabError('此模块没有整组版本')
                entry = find(self.records(state, session, mapping), entry_id)
                key = group + '/' + entry_id
                hidden = set(controls.setdefault('hidden_versions', {}).get(key, []))
                if action == 'remove-version':
                    find(record_versions(state, entry), version_id)
                    hidden.add(version_id)
                    # Keep the reviewed current content as session-only material.
                    values = self.snapshot(state, session, mapping, group, entry)
                    overrides = session.setdefault('scoped_overrides', {}).setdefault(group, {})
                    for fid,value in values.items():overrides[entry_id+'/'+fid]=value
                    session.setdefault('selected_sets', {}).setdefault(group, {}).pop(entry_id,None)
                else:hidden.clear()
                controls['hidden_versions'][key] = sorted(hidden)
            elif action in {'remove-composition', 'restore-compositions'}:
                versions = session.get('composition_versions', {}).get(group, [])
                hidden = set(controls.setdefault('hidden_compositions', {}).get(group, []))
                if action == 'remove-composition':
                    find(versions, version_id)
                    hidden.add(version_id)
                    session.setdefault('selected_compositions', {}).pop(group,None)
                else:hidden.clear()
                controls['hidden_compositions'][group] = sorted(hidden)
            else:raise LabError('未知材料操作')
            session.setdefault('preparation', {}).pop('preview',None)
        return self.lab.mutate(change)

    def apply_controls(self, state, plan):
        session = plan['session'];controls = session.get('material_controls', {})
        omitted = controls.get('omitted', [])
        for item in plan['material_items']:
            website = item['website_field'];wid = website['id'];group = item['group_id']
            item['included'] = wid not in omitted
            item['removed'] = wid in controls.get('removed_modules', [])
            if wid not in omitted:continue
            rule=item.get('requirement',{})
            dependency=item['mapping'].get('requires_records_when')
            unresolved = [i for i in plan['missing'] if i['website_field']['id'] == wid and i['kind'] in {'scope', 'scan', 'ambiguous'}]
            needed=bool(item['mapping'].get('status') == 'ambiguous' or website.get('required') or website.get('decision_required') or rule.get('min_items') or rule.get('required_values'))
            if dependency:
                needed=needed or any(i['website_field']['id']==dependency['website_id'] and i.get('value')==dependency['equals'] for i in plan['automatic'])
            plan['missing']=[i for i in plan['missing'] if i['website_field']['id']!=wid]
            plan['missing'].extend(unresolved)
            plan['payload']=[i for i in plan['payload'] if i['website_field']['id']!=wid]
            if needed:self.app._missing(plan,item,'已取消本次使用，但官网要求此项，请重新选择',kind='selection',blocking=True)
        plan['ready']=not any(i['blocking'] for i in plan['missing'])
