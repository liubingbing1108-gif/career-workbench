"""Transactional profile maintenance, independent from application-local choices."""
import copy
import hashlib
import json
import time
import re
from pathlib import Path
from lab import LabError, find, uid, all_versions, default_version, put_answer, validate_value
from profile_schema import fields_for, RECORD_TYPES
from profile_hierarchy import record_layout, views, active_fields
from profile_group_versions import enabled as versions_enabled, versions as group_versions, save_group, base_version, set_defaults


def token(state, entry):
    versions=[v for store in ('versions','answer_versions') for v in state.get(store,[]) if v['entry_id']==entry['id']]
    return hashlib.sha256(json.dumps([entry,versions,{k:v for k,v in state.get("profile_layouts",{}).items() if v["entry_id"]==entry["id"]}],sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def valid_token(state,entry,value):
    if value==token(state,entry):return True
    # Pre-P25 drafts used the same facts/versions hash without layout metadata.
    if any(v['entry_id']==entry['id'] for v in state.get('profile_layouts',{}).values()):return False
    versions=[v for store in ('versions','answer_versions') for v in state.get(store,[]) if v['entry_id']==entry['id']]
    legacy=hashlib.sha256(json.dumps([entry,versions],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return value==legacy


def view_record(state, entry):
    return {**copy.deepcopy(entry),'edit_token':token(state,entry),'record_versions':group_versions(state,entry),'versions_enabled':versions_enabled(state,entry)}


class ProfileLibrary:
    def __init__(self,lab):self.lab=lab

    def view(self):
        state=self.lab.state()
        return dict(records=[{**view_record(state,e),'id':layout['id'],'source_entry_id':e['id'],'layout':layout,'profile_archived':bool(e.get('profile_archived') or layout.get('archived'))} for e,layout in views(state)],drafts=state.get('profile_drafts',{}),tree=state['profile_tree'],saved_requests={key:item['result'].get('view_id') for key,item in state.get('profile_receipts',{}).items() if item.get('complete')})

    def draft(self,data):
        key=data.get('key','')
        if not isinstance(key,str) or not key or len(key)>240:raise LabError('草稿标识无效')
        def change(state):
            drafts=state.setdefault('profile_drafts',{})
            prior=drafts.get(key)
            if data.get('revision',0)!=(prior or {}).get('revision',0):raise LabError('草稿已在其他页面更改，请保留本页内容后重新载入',409)
            if data.get('discard'):
                drafts.pop(key,None);return dict(revision=0)
            body=data.get('body')
            if not isinstance(body,dict) or len(json.dumps(body))>500000:raise LabError('草稿内容无效或过长')
            saved=dict(body=copy.deepcopy(body),revision=(prior or {}).get('revision',0)+1,updated_at=time.time())
            drafts[key]=saved
            return saved
        return self.lab.mutate(change)

    def save(self,data):
        return self.lab.mutate(lambda state:self._save(state,data))

    def _save(self,state,data):
        request_id=data.get('request_id','')
        receipt=state.setdefault('profile_receipts',{}).get(request_id)
        signature=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        if not request_id or len(request_id)>160:raise LabError('缺少保存请求标识')
        if receipt:
            if receipt['signature']!=signature:raise LabError('保存请求已使用，请重新保存',409)
            return receipt['result']
        new=not data.get('entry_id')
        if new:
            cat=data.get('category')
            from lab import category
            if not category(cat) or cat=='attachments':raise LabError('请选择有效资料模块')
            if not data.get('layout') and not category(cat)[2] and any(e['category']==cat and not e.get('profile_archived') for e in state['entries']):raise LabError('此模块已有资料，请展开编辑',409)
            record_type=data.get('record_type','')
            if cat in RECORD_TYPES and record_type not in dict(RECORD_TYPES[cat]):raise LabError('请选择资料类型')
            entry=dict(id=uid(cat),category=cat,record_type=record_type,values={},sources={},default_versions={})
            state['entries'].append(entry)
        else:
            entry=find(state['entries'],data['entry_id'])
            if entry.get('profile_archived'):raise LabError('请先恢复这条资料',409)
            if not valid_token(state,entry,data.get('edit_token')):raise LabError('这条资料已更新，草稿已保留；请重新载入后核对',409)
        view_id=data.get('view_id') or entry['id']
        previous_layout=record_layout(state,entry,entry['id'] if new else view_id)
        if versions_enabled(state,entry,previous_layout):
            previous_layout['fixed_fields']=True
            entry.setdefault('profile_base_version',base_version(state,entry))
            entry['profile_base_version'].setdefault('layout',copy.deepcopy(previous_layout))
            chosen=next((v for v in group_versions(state,entry) if v['id']==data.get('set_id','default')),None)
            if chosen and chosen.get('layout') and data.get('scope'):
                state['profile_layouts'][view_id]=copy.deepcopy(chosen['layout'])
        layout=self._layout(state,entry,data,new) if data.get('layout') else None
        fields=fields_for(state,entry);values=data.get('values')
        if not isinstance(values,dict) or set(values)-{f['id'] for f in fields}:raise LabError('包含不属于当前资料的字段，草稿已保留',409)
        if layout and (data.get('scope') or {}).get('kind')=='group':
            target=next(g for g in layout['groups'] if g['id']==data['scope']['id'])
            if set(values)-{f['id'] for f in target['fields'] if not f.get('archived')}:raise LabError('信息组保存不能包含其他组的字段')
        if layout and set(values)-active_fields(layout):raise LabError('不能保存已删除的信息组或字段')
        # A newly discovered field must not force a form reload or clear facts.
        fields=[f for f in fields if f['id'] in values]
        mode=data.get('mode','update')
        if mode not in ('update','new'):raise LabError('未知保存方式')
        refs=data.get('field_versions',{})
        for field in fields:
            value=validate_value(field,values[field['id']])
            if field.get('widget')=='boolean' and value not in ('','是','否','不适用'):raise LabError(field['label']+'请选择是、否、未提供或不适用')
            if field.get('widget') in ('file','files') and value:
                for fid in value.split('\n'):
                    find(state['files'],fid,'附件不存在，请重新选择')
            if refs.get(field['id']):find(all_versions(state,entry['id'],field['id']),refs[field['id']])
        versioned=versions_enabled(state,entry,layout)
        if layout and versioned:layout['fixed_fields']=True
        if data.get('scope') and mode=='new':raise LabError('信息组保存不会新增版本，请在资料组底部另存为新版本')
        saved=save_group(state,entry,values,mode=mode,set_id=data.get('set_id') or 'default',name=str(data.get('name','')).strip()[:120],layout=layout,versioned=versioned)
        if layout and versioned and (mode=='new' or saved['id']!=entry.get('profile_default_set_id','default')):
            state['profile_layouts'][layout['id']]=previous_layout
        entry['profile_updated_at']=time.time()
        key=data.get('draft_key')
        if key:
            draft=state.get('profile_drafts',{}).get(key)
            if draft and draft.get('revision')!=data.get('draft_revision'):raise LabError('草稿已更新，请等待暂存完成后保存',409)
            state.get('profile_drafts',{}).pop(key,None)
        result=dict(record=view_record(state,entry),field_versions=saved['field_versions'],set_id=saved['id'],view_id=layout['id'] if layout else entry['id'])
        state['profile_receipts'][request_id]=dict(signature=signature,result=copy.deepcopy(result),complete=not data.get('scope'))
        # Bounded idempotency journal; it never contains uploaded file bytes.
        while len(state['profile_receipts'])>100:state['profile_receipts'].pop(next(iter(state['profile_receipts'])))
        return result

    @staticmethod
    def _retain_fields(state,entry,ids):
        for session in state['sessions']:
            mappings=session.get('website',{}).get('mappings',[])
            used={m.get('field_id') for m in mappings if m.get('category')==entry['category']}
            used.update(c.get('field_id') for m in mappings if m.get('category')==entry['category'] for c in m.get('members',[]))
            for fid in set(ids)&used:
                key=entry['id']+'/'+fid
                refs=session.setdefault('archived_profile_fields',[])
                if key not in refs:refs.append(key)

    def _layout(self,state,entry,data,new):
        incoming=copy.deepcopy(data['layout'])
        if not isinstance(incoming,dict):raise LabError('资料结构无效')
        view_id=entry['id'] if new else data.get('view_id',entry['id'])
        if view_id not in (entry['id'],entry['id']+'__address'):raise LabError('资料归属无效')
        previous=record_layout(state,entry,view_id)
        module=find(state['profile_tree']['nodes'],incoming.get('module_id'))
        if module['kind']!='module' or module.get('archived'):raise LabError('子模块已删除或不存在')
        groups=incoming.get('groups')
        if not isinstance(groups,list) or len(groups)>80:raise LabError('信息组无效或过多')
        allids=[f['id'] for g in groups for f in g.get('fields',[])]
        if any(not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}',g.get('id','')) for g in groups):raise LabError('信息组标识无效')
        if len(allids)!=len(set(allids)) or len(allids)>400 or len({g['id'] for g in groups})!=len(groups):raise LabError('信息组或字段重复')
        for text in [incoming.get('title',''),*[g.get('label','') for g in groups],*[f.get('label','') for g in groups for f in g['fields']]]:
            if not isinstance(text,str) or len(text)>120:raise LabError('名称过长或无效')
        scope=data.get('scope') or {}
        if scope:
            merged=copy.deepcopy({**incoming,'groups':[]} if new else previous)
            if scope.get('kind')=='group':
                group=next((g for g in groups if g['id']==scope['id']),None)
                if not group:raise LabError('信息组不存在')
                merged['groups']=[g for g in merged['groups'] if g['id']!=group['id']]+[group]
            elif scope.get('kind')=='field':
                parent=next((g for g in groups if any(f['id']==scope['id'] for f in g['fields'])),None)
                if not parent:raise LabError('字段不存在')
                item=next(f for f in parent['fields'] if f['id']==scope['id'])
                target=next((g for g in merged['groups'] if g['id']==parent['id']),None)
                if not target:
                    target={**parent,'fields':[]};merged['groups'].append(target)
                target['fields']=[f for f in target['fields'] if f['id']!=item['id']]+[item]
            else:raise LabError('保存范围无效')
            incoming=merged
        # Validate the submitted scope after merging. Deleted placeholders and
        # unfinished groups outside a partial save must not block visible edits.
        for g in incoming['groups']:
            if g.get('archived'):continue
            if not g.get('label','').strip():raise LabError('请填写信息组名称（字段内容可以留空）')
            for f in g['fields']:
                if not f.get('archived') and not f.get('label','').strip():raise LabError('「'+g['label']+'」中有未命名字段，请填写字段名称（内容可以留空）')
        incoming.update(id=view_id,entry_id=entry['id'])
        incoming['archived']=bool(incoming.get('archived'))
        needed=active_fields(incoming)
        for definition in data.get('field_definitions',[]):
            if definition['id'] not in needed:continue
            old=next((f for f in state['fields'] if f['id']==definition['id']),None)
            if old:
                if old.get('entry_id')!=entry['id']:raise LabError('字段标识已占用')
                continue
            spec={**definition,'category':entry['category'],'entry_id':entry['id'],'aliases':definition.get('aliases',[]),'options':definition.get('options',[])}
            if not spec['id'].startswith('local_') or len(spec['id'])>100:raise LabError('自定义字段标识无效')
            if spec['type'] not in ('text','multiline','partial_date','number','select','versioned_text'):raise LabError('字段类型无效')
            if spec.get('widget') not in (None,'boolean','file','files'):raise LabError('字段控件无效')
            if not spec.get('label') or len(spec['label'])>120 or any(not isinstance(v,str) for v in spec['aliases']+spec['options']):raise LabError('字段定义无效')
            state['fields'].append(spec)
        for fid in needed:
            field=find(state['fields'],fid)
            if field['category']!=entry['category'] or (field.get('entry_id') and field['entry_id']!=entry['id']):raise LabError('不能使用另一条资料的字段')
        self._retain_fields(state,entry,active_fields(previous)-active_fields(incoming))
        state['profile_layouts'][view_id]=incoming
        return incoming

    def tree(self,data):
        def change(state):
            tree=state['profile_tree']
            old_tokens={e['id']:token(state,e) for e in state['entries']} if data.get('action') in ('archive','restore') else {}
            if data.get('revision')!=tree['revision']:raise LabError('资料层级已在其他页面更新，请核对后重试',409)
            action=data.get('action');nodes=tree['nodes']
            if action=='create':
                parent=next((n for n in nodes if n['id']==data.get('parent')),None)
                if data.get('kind')=='module' and (not parent or parent['kind']!='major' or parent.get('archived')):raise LabError('请选择有效大模块')
                if data.get('kind')!='module':raise LabError('大模块固定，请在大模块旁新增子模块')
                node=dict(id=uid('module'),kind=data['kind'],parent=parent['id'] if parent else None,label='',categories=['additional'])
                nodes.append(node)
            else:node=find(nodes,data['id'])
            if action in ('create','save'):
                label=data.get('label','').strip()
                if not label or len(label)>100:raise LabError('请填写不超过100字的名称')
                node['label']=label
            elif action in ('archive','restore'):
                if node['kind']=='major' and action=='archive':raise LabError('大模块固定，支持改名和新增子模块')
                archived=action=='archive';node['archived']=archived
                targets={node['id']}|{n['id'] for n in nodes if n.get('parent')==node['id']}
                for n in nodes:
                    if n.get('parent')==node['id']:
                        if archived and not n.get('archived'):n['archived']=True;n['archived_by']=node['id']
                        elif not archived and n.get('archived_by')==node['id']:n['archived']=False;n.pop('archived_by',None)
                for entry,layout in list(views(state)):
                    if layout['module_id'] not in targets:continue
                    if archived:
                        if not layout.get('archived'):layout['archived_by']=node['id'];layout['archived']=True
                        self._retain_fields(state,entry,active_fields(layout))
                    elif layout.get('archived_by')==node['id']:
                        layout['archived']=False;layout.pop('archived_by',None)
                    state['profile_layouts'][layout['id']]=layout
                # Entry flags enforce the existing application selection contract.
                for entry in state['entries']:
                    related=[l for e,l in views(state) if e['id']==entry['id']]
                    if archived and related and all(l.get('archived') for l in related) and not entry.get('profile_archived'):
                        entry['profile_archived']=True;entry['profile_archived_by']=node['id']
                        for session in state['sessions']:
                            if session.get('website'):
                                refs=session.setdefault('archived_profile_refs',[])
                                if entry['id'] not in refs:refs.append(entry['id'])
                    elif not archived and entry.get('profile_archived_by')==node['id']:
                        entry['profile_archived']=False;entry.pop('profile_archived_by',None)
            else:raise LabError('层级操作无效')
            # Parent saves atomically include only submitted descendant drafts.
            targets={node['id']}|{n['id'] for n in nodes if n.get('parent')==node['id']}
            results=[]
            requests=copy.deepcopy(data.get('records',[]))
            for request in requests:
                if request.get('layout',{}).get('module_id') not in targets:raise LabError('不能保存其他模块的草稿')
                if request.get('entry_id') and not valid_token(state,find(state['entries'],request['entry_id']),request.get('edit_token')):raise LabError('资料已更新，所有草稿已保留',409)
            for request in requests:
                if request.get('entry_id'):request['edit_token']=token(state,find(state['entries'],request['entry_id']))
                results.append(self._save(state,request))
            # Archive/restore changes metadata only; keep matching drafts usable.
            for draft in state.get('profile_drafts',{}).values():
                body=draft['body'];eid=body.get('entry_id')
                if eid in old_tokens and body.get('edit_token')==old_tokens[eid]:
                    new_token=token(state,find(state['entries'],eid))
                    if new_token!=old_tokens[eid]:
                        body.setdefault('previous_edit_tokens',[]).append(old_tokens[eid])
                        body['previous_edit_token']=old_tokens[eid];body['edit_token']=new_token
                        draft['revision']+=1
            tree['revision']+=1
            return dict(tree=tree,node=node,results=results)
        return self.lab.mutate(change)

    def field_version(self,data):
        def change(state):
            entry=find(state['entries'],data['entry_id'])
            if not valid_token(state,entry,data.get('edit_token')):raise LabError('资料已更新，请刷新核对后再新增版本',409)
            field=find(state['fields'],data['field_id'])
            if field['category']!=entry['category'] or entry.get('profile_archived'):raise LabError('字段或资料状态无效')
            content=data.get('content','')
            if field.get('widget') in {'file','files'} and content:
                for fid in content.split('\n'):find(state['files'],fid,'请选择已保存附件')
            version=put_answer(state,entry,field,content,name=data.get('name','新版本'))
            return dict(record=view_record(state,entry),version=version)
        return self.lab.mutate(change)

    def default(self,data):
        def change(state):
            entry=find(state['entries'],data['entry_id'])
            if not valid_token(state,entry,data.get('edit_token')):raise LabError('资料已更新，请刷新后重试',409)
            refs=data.get('field_versions',{})
            if data.get('set_id'):
                chosen=find(group_versions(state,entry),data['set_id'])
                refs=chosen['field_versions'];entry['profile_default_set_id']=chosen['id']
                if chosen.get('layout'):state['profile_layouts'][chosen['layout']['id']]=copy.deepcopy(chosen['layout'])
            if not isinstance(refs,dict):raise LabError('版本引用无效')
            for fid,vid in refs.items():
                field=find(state['fields'],fid)
                if field['category']!=entry['category']:raise LabError('字段不属于该资料')
                if vid:
                    version=find(all_versions(state,entry['id'],fid),vid)
                    if version.get('profile_deleted'):raise LabError('已删除的版本不能设为默认')
            for fid,vid in refs.items():
                if not vid:continue
                version=find(all_versions(state,entry['id'],fid),vid)
                entry.setdefault('default_versions',{})[fid]=vid
                field=find(state['fields'],fid)
                if field['type']!='versioned_text':
                    entry['values'][fid]=version['content'];entry['sources'][fid]=version.get('source',{})
            return view_record(state,entry)
        return self.lab.mutate(change)

    def version(self,data):
        """Delete library choices without destroying references in saved applications."""
        def change(state):
            entry=find(state['entries'],data['entry_id'])
            if not valid_token(state,entry,data.get('edit_token')):raise LabError('资料已更新，草稿已保留，请重新核对',409)
            action=data.get('action');fid=data.get('field_id');vid=data.get('version_id')
            if action not in ('rename','delete'):raise LabError('未知版本操作')
            if fid:
                version=find(all_versions(state,entry['id'],fid),vid)
                if version.get('profile_deleted'):raise LabError('版本已删除',409)
            elif vid=='default':
                if vid in entry.get('profile_deleted_sets',[]):raise LabError('版本已删除',409)
                entry.setdefault('profile_base_version',base_version(state,entry))
                version=entry['profile_base_version']
            else:
                version=find(entry.get('set_versions',[]),vid)
                if version.get('profile_deleted'):raise LabError('版本已删除',409)
            if action=='rename':
                name=data.get('name','')
                if not isinstance(name,str) or not name.strip() or len(name)>120:raise LabError('请输入不超过120字的版本名称')
                if vid=='default' and not fid:entry['profile_default_name']=name.strip();version['name']=name.strip()
                else:version['name']=name.strip()
            elif fid:
                # Freeze already prepared defaults before changing future library defaults.
                key=entry['id']+'/'+fid
                for session in state['sessions']:
                    for mapping in session.get('website',{}).get('mappings',[]):
                        if mapping.get('category')!=entry['category']:continue
                        group=(mapping.get('requirement') or {}).get('group') or mapping['website_id']
                        session.setdefault('scoped_versions',{}).setdefault(group,{}).setdefault(key,entry.get('default_versions',{}).get(fid))
                        session.setdefault('selected_versions',{}).setdefault(key,entry.get('default_versions',{}).get(fid))
                version['profile_deleted']=True
                if entry.get('default_versions',{}).get(fid)==vid:
                    remaining=[v for v in all_versions(state,entry['id'],fid) if not v.get('profile_deleted')]
                    entry['default_versions'].pop(fid,None)
                    if remaining:entry['default_versions'][fid]=remaining[0]['id']
                    if find(state['fields'],fid)['type']!='versioned_text':
                        entry['values'][fid]=remaining[0]['content'] if remaining else ''
                        entry['sources'][fid]=remaining[0].get('source',{}) if remaining else {}
            else:
                entry.setdefault('profile_deleted_sets',[]).append(vid)
                if version is not None:version['profile_deleted']=True
                if vid==entry.get('profile_default_set_id','default'):
                    remaining=group_versions(state,entry)
                    if remaining:
                        chosen=remaining[0];entry['profile_default_set_id']=chosen['id'];set_defaults(state,entry,chosen['field_versions'])
                        if chosen.get('layout'):state['profile_layouts'][chosen['layout']['id']]=copy.deepcopy(chosen['layout'])
                    else:entry['profile_default_set_id']='unversioned'
            return dict(record=view_record(state,entry))
        return self.lab.mutate(change)

    def archive(self,data):
        eid=data.get('entry_id');archived=data.get('archived')
        if type(archived) is not bool:raise LabError('请选择删除或恢复')
        with self.lab.lock:
            # Existing prepared selections keep their references; future selections skip archived data.
            from application import Application
            refs=[]
            for session in self.lab.state()['sessions']:
                if not session.get('website'):continue
                plan=Application(self.lab).plan(session['id'])
                if any(e.get('id')==eid for item in plan.get('automatic',[])+plan.get('decisions',[]) for e in item.get('selected',[])):
                    refs.append(session['id'])
                if any(item.get('entry_id')==eid for item in plan.get('payload',[])):refs.append(session['id'])
            def change(state):
                entry=find(state['entries'],eid)
                if not valid_token(state,entry,data.get('edit_token')):raise LabError('资料已更新，请刷新后重试',409)
                if data.get('view_id'):
                    layout=record_layout(state,entry,data['view_id']);layout['archived']=archived
                    self._retain_fields(state,entry,active_fields(layout))
                    state['profile_layouts'][layout['id']]=layout
                    if layout['id']!=entry['id'] or entry['category']=='contact':return view_record(state,entry)
                entry['profile_archived']=archived
                for session in state['sessions']:
                    if archived and (session['id'] in refs or eid in json.dumps(session,ensure_ascii=False)):
                        ids=session.setdefault('archived_profile_refs',[])
                        if eid not in ids:ids.append(eid)
                return view_record(state,entry)
            return self.lab.mutate(change)

    def attachment(self,data):
        def change(state):
            item=find(state['files'],data['file_id'])
            if data.get('revision',0)!=item.get('profile_revision',0):raise LabError('附件信息已更新，请刷新重试',409)
            metadata=data.get('metadata',{})
            allowed={'display_name','attachment_type','language','version_name','target_role','target_company','linked_entry','archived'}
            if set(metadata)-allowed:raise LabError('附件字段无效')
            for k,v in metadata.items():
                if k=='archived':
                    if type(v) is not bool:raise LabError('归档状态无效')
                elif not isinstance(v,str) or len(v)>3000:raise LabError('附件信息无效')
            if metadata.get('linked_entry'):find(state['entries'],metadata['linked_entry'])
            item.update(metadata);item['profile_revision']=item.get('profile_revision',0)+1
            return item
        return self.lab.mutate(change)

    def import_identity(self,data):
        def change(state):
            preview=find(state['imports'],data['import_id'])
            if data.get('revision')!=preview.get('revision',1):raise LabError('导入预览已变化，请刷新',409)
            rows=[c for c in preview['candidates'] if c['group']==data['group']]
            if not rows or any(c.get('saved') for c in rows):raise LabError('此组已保存或不存在')
            eid=data.get('entry_id')
            if eid:
                entry=find(state['entries'],eid)
                if entry['category']!=rows[0]['category']:raise LabError('不能合并不同模块的资料')
                if eid not in rows[0].get('identity_choices',[]):raise LabError('请选择待核对的已有记录')
            preview.setdefault('identity_decisions',{})[data['group']]={'entry_id':eid}
            preview['revision']=preview.get('revision',1)+1
            return dict(saved=True)
        return self.lab.mutate(change)

    def upload_attachment(self,filename,raw):
        filename=Path(filename.replace('\\','/')).name
        if not filename or len(filename)>180 or not raw or len(raw)>8*1024*1024:raise LabError('请选择不超过 8 MiB 的文件')
        def change(state):
            checksum=hashlib.sha256(raw).hexdigest()
            existing=next((f for f in state['files'] if f.get('sha256')==checksum and f['name']==filename and not f.get('archived')),None)
            if existing:return existing
            item=dict(id=uid('file'),name=filename,display_name=filename,size=len(raw),sha256=checksum,uploaded_at=time.time(),profile_revision=0)
            self.lab.db.execute('INSERT INTO files VALUES (?,?)',(item['id'],raw))
            state['files'].append(item);return item
        return self.lab.mutate(change)
