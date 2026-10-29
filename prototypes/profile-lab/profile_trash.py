"""Thirty-day recoverable deletion, independent from retained application evidence."""
import copy
import time
from lab import LabError, find
from profile_current import RETENTION


def freeze(state, entry, version_id=None):
    from application import entry_material, Application
    from profile_contract import category_for
    for session in state['sessions']:
        for mapping in session.get('website', {}).get('mappings', []):
            if mapping.get('category') != entry['category']:continue
            group = (mapping.get('requirement') or {}).get('group') or mapping['website_id']
            referenced=False
            if mapping.get('requirement') and mapping.get('status')!='ambiguous':
                chosen,_,_,_=Application(None)._group(state,session,mapping,session['website']['fields'])
                referenced=entry['id'] in {e['id'] for e in chosen}
                if mapping.get('multi_source') and entry.get('record_type')=='ability':
                    from mixed_sources import source
                    for primary in chosen:
                        for member in mapping.get('members',[]):
                            linked,error=source(state,session,mapping,member,primary,group)
                            if linked and linked['id']==entry['id'] and not error:referenced=True
            elif not category_for(state,entry['category'])[2]:
                definition=next((f for f in state['fields'] if f['id']==mapping.get('field_id')),{})
                referenced=not definition.get('entry_id') or definition['entry_id']==entry['id']
            prefix=entry['id']+'/'
            referenced=referenced or any(k.startswith(prefix) for k in session.get('scoped_overrides',{}).get(group,{}))
            referenced=referenced or any(k.startswith(session['id']+'/'+group+'/'+prefix) and v.get('value') is not None for k,v in session.get('preparation',{}).get('drafts',{}).items())
            if not referenced:continue
            selected = session.get('selected_sets', {}).get(group, {}).get(entry['id'], entry.get('profile_default_set_id'))
            if version_id is not None and selected != version_id:continue
            material = entry_material(state, session, entry, group)
            session.setdefault('profile_snapshots', {}).setdefault(group, {})[entry['id']] = dict(material=copy.deepcopy(material), version_id=selected)
            refs = session.setdefault('archived_profile_refs', [])
            if entry['id'] not in refs:refs.append(entry['id'])


def version_action(state, entry, data, now=None):
    from profile_library import valid_token, view_record
    now = time.time() if now is None else now
    version = find(entry.get('expression_versions', []), data.get('version_id'))
    action = data.get('action')
    if action == 'delete' and version.get('deleted_at'):
        return dict(record=view_record(state, entry))
    if action == 'restore' and not version.get('deleted_at'):
        return dict(record=view_record(state, entry))
    if not valid_token(state, entry, data.get('edit_token')):raise LabError('版本已更新，请重新核对', 409)
    key = 'version:'+entry['id']+'/'+version['id']
    if action == 'rename':
        name = data.get('name', '')
        if not isinstance(name, str) or not name.strip() or len(name) > 180:raise LabError('请输入不超过180字的版本名称')
        if version.get('deleted_at'):raise LabError('请先恢复版本', 409)
        version['name'] = name.strip()
    elif action == 'delete':
        freeze(state, entry, version['id'])
        version['deleted_at'] = now
        state['profile_trash'].append(dict(id=key, kind='version', entry_id=entry['id'], version_id=version['id'], deleted_at=now, expires_at=now+RETENTION))
        if entry.get('profile_default_set_id') == version['id']:entry['profile_default_set_id'] = None
    elif action == 'restore':
        item = find(state['profile_trash'], key)
        if now >= item['expires_at']:raise LabError('版本已超过30天恢复期限', 409)
        version.pop('deleted_at', None)
        state['profile_trash'].remove(item)
    else:raise LabError('未知版本操作')
    return dict(record=view_record(state, entry))


def archive(state, data, now=None):
    from profile_library import valid_token, view_record
    from profile_contract import current_values
    now = time.time() if now is None else now
    entry = find(state['entries'], data.get('entry_id'))
    archived = data.get('archived')
    if type(archived) is not bool:raise LabError('请选择删除或恢复')
    if entry.get('purged'):raise LabError('资料已到期清理，不能恢复',409)
    if archived and entry.get('deleted_at'):return dict(record=view_record(state, entry), conflicts=[])
    if not archived and not entry.get('profile_archived'):return dict(record=view_record(state, entry), conflicts=[])
    if not valid_token(state, entry, data.get('edit_token')):raise LabError('资料已更新，请重新核对', 409)
    key = 'object:'+entry['id']
    conflicts = []
    if archived:
        freeze(state, entry)
        links = []
        relations = []
        for link in state.get('language_exam_links', []):
            if link.get('active') and entry['id'] in {link['ability_id'], link['exam_id']}:
                link.update(active=False, revision=link.get('revision', 1)+1, reason=key)
                links.append(dict(id=link['id'], revision=link['revision']))
        local_fields={f['id'] for f in state['fields'] if f.get('entry_id')==entry['id']}
        for relation in state.get('profile_relations',[]):
            if relation.get('state')=='active' and (relation.get('scope',{}).get('entry_id')==entry['id'] or entry['id'] in (relation.get('selector') or {}).get('entry_ids',[]) or local_fields.intersection(relation.get('field_ids',[]))):
                relation.update(state='needs_review',revision=relation['revision']+1)
                relations.append(dict(id=relation['id'],revision=relation['revision']))
        if relations:state['profile_relation_revision']=state.get('profile_relation_revision',0)+1
        entry.update(profile_archived=True, deleted_at=now)
        state['profile_trash'].append(dict(id=key, kind='object', entry_id=entry['id'], deleted_at=now, expires_at=now+RETENTION, links=links, relations=relations))
    else:
        item = find(state['profile_trash'], key)
        if now >= item['expires_at']:raise LabError('资料已超过30天恢复期限', 409)
        entry['profile_archived'] = False;entry.pop('deleted_at', None)
        # An identity created after deletion must not be silently duplicated.
        from profile_current import validate_values
        validate_values(state, entry, {})
        for saved in item.get('links', []):
            link = next((x for x in state['language_exam_links'] if x['id'] == saved['id']), None)
            if not link or link['revision'] != saved['revision'] or link.get('reason') != key:
                conflicts.append(dict(link_id=saved['id'], reason='关联在删除后已改变'));continue
            ability = next((x for x in state['entries'] if x['id'] == link['ability_id'] and not x.get('profile_archived')), None)
            exam = next((x for x in state['entries'] if x['id'] == link['exam_id'] and not x.get('profile_archived')), None)
            left = current_values(state, ability).get('language_name', '').strip().casefold() if ability else ''
            right = current_values(state, exam).get('exam_language', '').strip().casefold() if exam else ''
            if not ability or not exam or left and right and left != right:
                conflicts.append(dict(link_id=link['id'], reason='原关联对象不可用或语种已变化'));continue
            link.update(active=True, revision=link['revision']+1, reason='restored')
        from profile_migration import state_hash
        definitions={f['id']:f for f in state['fields'] if not f.get('legacy_preserved')}
        for saved in item.get('relations',[]):
            relation=next((r for r in state.get('profile_relations',[]) if r['id']==saved['id']),None)
            if not relation or relation['revision']!=saved['revision'] or relation['state']!='needs_review':
                conflicts.append(dict(relation_id=saved['id'],reason='对应关系在删除后已由用户更改'));continue
            if any(ref['field_id'] not in definitions or int(state_hash(definitions[ref['field_id']])[:8],16)!=ref['revision'] for ref in relation['field_revisions']):
                conflicts.append(dict(relation_id=saved['id'],reason='对应字段定义已改变，需要重新核对'));continue
            targets=set((relation.get('selector') or {}).get('entry_ids',[]))
            if relation.get('scope',{}).get('entry_id'):targets.add(relation['scope']['entry_id'])
            if any(not any(e['id']==eid and not e.get('profile_archived') and not e.get('legacy_only') for e in state['entries']) for eid in targets):
                conflicts.append(dict(relation_id=saved['id'],reason='原对应的其他对象不可用'));continue
            relation.update(state='active',revision=relation['revision']+1)
            state['profile_relation_revision']=state.get('profile_relation_revision',0)+1
        state['profile_trash'].remove(item)
    return dict(record=view_record(state, entry), conflicts=conflicts)


def expire(state, now=None):
    """No blob deletion. History keeps expanded content, not restorable library objects."""
    now = time.time() if now is None else now
    expired = [x for x in state.get('profile_trash', []) if now >= x['expires_at']]
    for item in expired:
        if item['kind']=='attachment':
            original=next((f for f in state['files'] if f['id']==item['file_id']),None)
            if original:
                original['library_removed']=True;original.pop('attachment_type',None)
            state['profile_trash'].remove(item)
            continue
        entry = next((e for e in state['entries'] if e['id'] == item['entry_id']), None)
        if not entry:
            state['profile_trash'].remove(item);continue
        # Missing historical evidence blocks destructive cleanup, never fabricate it.
        def history_might_reference(p):
            if p.get('state')!='pending' or p.get('kind')!='historical_evidence':return False
            # Current mappings cannot prove the scope of an older execution.
            # Narrow a hold only when historical evidence names its affected IDs.
            return 'affected_entry_ids' not in p or entry['id'] in p['affected_entry_ids']
        if any(history_might_reference(p) for p in state.get('profile_pending', [])):
            item['cleanup_blocked'] = '历史实际内容尚未核对';continue
        if item['kind'] == 'version':
            removed=next((v for v in entry.get('expression_versions',[]) if v['id']==item['version_id']),{})
            entry['expression_versions'] = [v for v in entry.get('expression_versions', []) if v['id'] != item['version_id']]
            retained={ref for e in state['entries'] for v in e.get('expression_versions',[]) for ref in v['field_versions'].values()}
            retained.update(ref for e in state['entries'] for ref in e.get('default_versions',{}).values())
            discarded=set(removed.get('field_versions',{}).values())-retained
            for store in ('versions','answer_versions'):
                state[store]=[v for v in state.get(store,[]) if v['id'] not in discarded]
            evidence=state.get('profile_legacy_evidence',{})
            for old in evidence.get('entries',[]):
                if old['id']!=entry['id']:continue
                if old.get('profile_base_version',{}).get('id')==item['version_id']:old.pop('profile_base_version',None)
                old['set_versions']=[v for v in old.get('set_versions',[]) if v['id']!=item['version_id']]
            for store in ('versions','answer_versions'):
                if store in evidence:evidence[store]=[v for v in evidence[store] if v['id'] not in discarded]
        else:
            eid = entry['id']
            entry.clear();entry.update(id=eid, category='retired', profile_archived=True, purged=True)
            for store in ('versions', 'answer_versions'):
                state[store] = [v for v in state.get(store, []) if v['entry_id'] != eid]
            for key,draft in state.get('profile_drafts', {}).items():
                if eid in key:draft['reference_invalid']=True
            state['language_exam_links'] = [x for x in state.get('language_exam_links', []) if eid not in {x['ability_id'], x['exam_id']}]
            evidence=state.get('profile_legacy_evidence',{})
            for store in ('entries','versions','answer_versions'):
                if store in evidence:evidence[store]=[v for v in evidence[store] if (v['id'] if store=='entries' else v['entry_id'])!=eid]
            state['profile_layouts']={key:value for key,value in state.get('profile_layouts',{}).items() if value.get('entry_id')!=eid}
            if 'profile_layouts' in evidence:evidence['profile_layouts']={key:value for key,value in evidence['profile_layouts'].items() if value.get('entry_id')!=eid}
        state['profile_trash'].remove(item)
        for key, receipt in list(state.get('profile_receipts', {}).items()):
            if receipt.get('result', {}).get('record', {}).get('id') == item['entry_id']:state['profile_receipts'].pop(key)


def file_action(state,data,now=None):
    now=time.time() if now is None else now
    original=find(state['files'],data.get('file_id'))
    key='attachment:'+original['id']
    if data['action']=='delete' and original.get('archived'):return original
    if data['action']=='restore' and not original.get('archived'):return original
    if original.get('profile_revision',0)!=data.get('revision',0):raise LabError('附件信息已改变，请重新载入',409)
    if data['action']=='delete':
        original.update(archived=True,deleted_at=now)
        state['profile_trash'].append(dict(id=key,kind='attachment',file_id=original['id'],deleted_at=now,expires_at=now+RETENTION))
    else:
        item=find(state['profile_trash'],key)
        if now>=item['expires_at']:raise LabError('附件记录已超过恢复期限；原件仍保留供历史引用',409)
        original['archived']=False;original.pop('deleted_at',None);state['profile_trash'].remove(item)
    original['profile_revision']=original.get('profile_revision',0)+1
    return original
