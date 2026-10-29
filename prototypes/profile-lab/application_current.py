"""Session-only material edits and explicit one-field writeback on contract 30."""
import copy
from lab import LabError, find, uid, validate_value, default_version
from profile_contract import expression_ids
from profile_current import save_values
from profile_migration import state_hash


def project(state, session):
    """Extend an in-memory plan snapshot only. Never append to the shared catalog."""
    known={f['id'] for f in state['fields']}
    state['fields'].extend(copy.deepcopy(f) for f in session.get('session_fields',[]) if f['id'] not in known)
    entries={e['id'] for e in state['entries']}
    state['entries'].extend(copy.deepcopy(e) for e in session.get('session_entries',[]) if e['id'] not in entries)


def edit(app,state,session_id,website_id,value,mode,version_id,expected_revision,name,entry_id,field_id,child_id,request_id=None,preview_token=None,relation_options=None):
    from application import group_id,value_error,website_value
    session=find(state['sessions'],session_id)
    signature=state_hash([website_id,value,mode,version_id,expected_revision,name,entry_id,field_id,child_id,preview_token,relation_options])
    if relation_options and (mode=='session' or not preview_token):raise LabError('保存对应关系需明确回库并核对差异预览')
    if mode!='session':
        if not isinstance(request_id,str) or not request_id or len(request_id)>180:raise LabError('缺少回库请求标识')
        receipt=session.get('answer_write_receipts',{}).get(request_id)
        if receipt:
            if receipt.get('signature')!=signature:raise LabError('同一回库请求不能更改内容',409)
            return copy.deepcopy(receipt['result'])
        if preview_token:
            fresh=answer_preview(app,state,dict(session_id=session_id,website_id=website_id,value=value,entry_id=entry_id,field_id=field_id,child_id=child_id))
            if fresh['token']!=preview_token:raise LabError('预览后资料或本次材料已变化，请重新核对差异',409)
    shadow=copy.deepcopy(state);draft_session=find(shadow['sessions'],session_id);project(shadow,draft_session)
    m,member,website,entry,field=app._answer_target(shadow,draft_session,website_id,entry_id,field_id,child_id)
    error=value_error(website_value(value,member.get('transform'),website.get('options')),{**website,'required':False})
    if error:raise LabError(error)
    if field is None:
        definition=member.get('new_field')
        if not definition:raise LabError('缺少已核对的新属性定义')
        app._check_definition(definition,entry['category'])
        field=app._existing_field(shadow,definition)
        if field and field.get('legacy_preserved'):raise LabError('已取消预设不能通过网站补充恢复')
        if field is None:
            field=dict(id=uid('session_field'),**definition,aliases=[],options=[],value_role='fact')
            from profile_contract import category_for
            if category_for(state,entry['category'])[2]:field.update(entry_id=entry['id'],record_types=[entry['record_type']] if entry.get('record_type') else [])
            if field['type']=='select':
                field['options']=[o.get('value',o.get('label')) if isinstance(o,dict) else o for o in website.get('options',[])]
                if not field['options']:field['type']='text'
        member['field_id']=field['id']
        if member is m:m.update(status='mapped',category=entry['category'])
    validate_value(field,value)
    group=group_id(m);key=entry['id']+'/'+field['id']
    shared_field=next((f for f in state['fields'] if f['id']==field['id']),None)
    shared_entry=next((e for e in state['entries'] if e['id']==entry['id']),None)
    if mode=='session':
        if shared_field is None and not any(f['id']==field['id'] for f in draft_session.get('session_fields',[])):
            draft_session.setdefault('session_fields',[]).append(copy.deepcopy(field))
        if shared_entry is None and not any(e['id']==entry['id'] for e in draft_session.get('session_entries',[])):
            draft_session.setdefault('session_entries',[]).append(copy.deepcopy(entry))
        draft_session.setdefault('scoped_overrides',{}).setdefault(group,{})[key]=value
    else:
        if shared_field is None:
            # Explicit writeback materializes definition and value in this one transaction.
            equivalent=app._existing_field(state,field)
            if equivalent and equivalent['id']!=field['id']:raise LabError('已有同义字段，请重新核对再回库',409)
            state['fields'].append(copy.deepcopy(field))
        if shared_entry is None:
            state['entries'].append(copy.deepcopy(entry));shared_entry=state['entries'][-1]
        expression=field['id'] in expression_ids(state,shared_entry)
        selected=draft_session.get('selected_sets',{}).get(group,{}).get(entry['id'],shared_entry.get('profile_default_set_id'))
        prior=default_version(state,shared_entry,field['id'])
        if expression and selected:
            chosen=find(shared_entry.get('expression_versions',[]),selected)
            ref=chosen['field_versions'].get(field['id'])
            prior=next((v for store in ('versions','answer_versions') for v in state.get(store,[]) if v['id']==ref),None)
        if prior and (expected_revision!=prior['revision'] or version_id!=prior['id']):raise LabError('当前资料已变化，请核对差异后再回库',409)
        if mode=='new' and not expression:raise LabError('共用事实或非版本资料只能更新当前值')
        saved=save_values(state,shared_entry,{field['id']:value},mode=mode,set_id=selected,name=name)
        if expression:draft_session.setdefault('selected_sets',{}).setdefault(group,{})[entry['id']]=saved['id']
        draft_session.setdefault('scoped_overrides',{}).setdefault(group,{}).pop(key,None)
        draft_session['session_fields']=[f for f in draft_session.get('session_fields',[]) if f['id']!=field['id']]
        draft_session['session_entries']=[e for e in draft_session.get('session_entries',[]) if e['id']!=entry['id']]
    draft_session.setdefault('preparation',{}).pop('preview',None)
    session.clear();session.update(draft_session)
    result=dict(field=field,mode=mode,entry_id=entry['id'])
    if relation_options:
        from mapping_relations import writeback_relation
        result['relation']=writeback_relation(state,session,m,member,entry,field,relation_options,request_id)
    if mode!='session':session.setdefault('answer_write_receipts',{})[request_id]=dict(signature=signature,result=copy.deepcopy(result))
    return result


def answer_preview(app,state,data):
    from application import group_id,entry_material
    from profile_library import token
    shadow=copy.deepcopy(state);session=find(shadow['sessions'],data['session_id']);project(shadow,session)
    mapping,member,website,entry,field=app._answer_target(shadow,session,data['website_id'],data.get('entry_id'),data.get('field_id'),data.get('child_id'))
    if not field:raise LabError('请先核对新属性并保存为本次内容，再预览回库')
    group=group_id(mapping);shared=next((e for e in state['entries'] if e['id']==entry['id']),None)
    selected=session.get('selected_sets',{}).get(group,{}).get(entry['id'],entry.get('profile_default_set_id'))
    from profile_contract import current_values
    old=current_values(state,shared,selected).get(field['id'],'') if shared and any(f['id']==field['id'] for f in state['fields']) else ''
    material=entry_material(shadow,session,entry,group);choice=next(c for c in material['choices'] if c['field']['id']==field['id'])
    prior=default_version(state,shared,field['id']) if shared else None
    expression=field['id'] in expression_ids(shadow,entry)
    if expression and selected and shared:
        version=find(shared.get('expression_versions',[]),selected);ref=version['field_versions'].get(field['id'])
        prior=next((v for store in ('versions','answer_versions') for v in state.get(store,[]) if v['id']==ref),None)
    value=data.get('value');validate_value(field,value)
    new_definition=not any(f['id']==field['id'] for f in state['fields'])
    result=dict(entry_id=entry['id'],field_id=field['id'],label=field['label'],old=old,new=value,current=choice['content'],
                version_id=(prior or {}).get('id'),expected_revision=(prior or {}).get('revision'),new_definition=new_definition,
                expression=expression,impact='所选表达版本' if expression else '此对象当前事实（各版本共用）',
                relation_revision=state.get('profile_relation_revision',0),site_scope_available=bool(session['website'].get('tenant') and session['website'].get('form_key')))
    result['token']=state_hash([result,token(state,shared) if shared else None,mapping,selected,field])
    return result


def save_material_record(service,state,session,mapping,group,data,mode,name):
    from profile_library import token
    from profile_contract import fields_for,current_values,EXPRESSIONS
    projected=copy.deepcopy(state);local_session=find(projected['sessions'],session['id']);project(projected,local_session)
    entry=find(service.records(projected,local_session,mapping),data['entry_id'])
    current=service.snapshot(projected,local_session,mapping,group,entry)
    if current!=data.get('expected_values'):raise LabError('本次材料已变化，请保留草稿并重新核对',409)
    values=data.get('values')
    allowed={f['id']:f for f in fields_for(projected,entry)}
    if not isinstance(values,dict) or set(values)-allowed.keys():raise LabError('字段不属于此对象')
    for fid,value in values.items():validate_value(allowed[fid],value)
    overrides=session.setdefault('scoped_overrides',{}).setdefault(group,{})
    if mode=='session':
        for fid,value in values.items():
            if value!=current.get(fid,''):overrides[entry['id']+'/'+fid]=value
        session.setdefault('preparation',{}).pop('preview',None)
        return entry['id']
    selected=data.get('selected_fields')
    if not isinstance(selected,list) or len(selected)!=len(set(selected)) or set(selected)-values.keys():raise LabError('请先预览并选择要回库的字段')
    relations=data.get('relations',[])
    if not isinstance(relations,list) or any(not isinstance(r,dict) for r in relations):raise LabError('对应选择无效')
    if not selected and not relations:return entry['id']
    shared=next((e for e in state['entries'] if e['id']==entry['id']),None)
    if shared and data.get('edit_token')!=token(state,shared):raise LabError('资料库在预览后已变化，请重新核对差异',409)
    if mode=='new' and entry['category'] not in EXPRESSIONS:raise LabError('此类资料只能更新当前内容')
    if shared is None:
        if not selected:raise LabError('新对象的关系须与选中资料共同保存')
        shared=copy.deepcopy(entry);state['entries'].append(shared)
    for fid in selected:
        if not any(f['id']==fid for f in state['fields']):
            if fid not in data.get('confirmed_field_ids',[]):raise LabError('请明确确认选中的新属性定义')
            equivalent=service.app._existing_field(state,allowed[fid])
            if equivalent and equivalent['id']!=fid:raise LabError('已有同义字段，请重新核对后回库',409)
            state['fields'].append(copy.deepcopy(allowed[fid]))
    set_id=session.get('selected_sets',{}).get(group,{}).get(entry['id'],shared.get('profile_default_set_id'))
    if selected:
        saved=save_values(state,shared,{fid:values[fid] for fid in selected},mode=mode,set_id=set_id,name=name)
        if shared['category'] in EXPRESSIONS:session.setdefault('selected_sets',{}).setdefault(group,{})[entry['id']]=saved['id']
    seen=set()
    for options in relations:
        qid=options.get('question_id')
        if qid in seen:raise LabError('不能重复保存同一问题对应')
        seen.add(qid)
        member=next((m for m in mapping.get('members',[]) if m.get('website_id')==qid),None)
        if not member or member.get('field_id') not in allowed:raise LabError('对应不属于此对象字段',409)
        fid=member['field_id'];definition=next((f for f in state['fields'] if f['id']==fid),None)
        if not definition:raise LabError('新属性对应须与其定义及答案共同保存')
        from mapping_relations import writeback_relation
        writeback_relation(state,session,mapping,member,shared,definition,options,data['request_id'])
    for fid in selected:overrides.pop(entry['id']+'/'+fid,None)
    session['session_fields']=[f for f in session.get('session_fields',[]) if f['id'] not in selected]
    session['session_entries']=[e for e in session.get('session_entries',[]) if e['id']!=entry['id']]
    session.setdefault('preparation',{}).pop('preview',None)
    return entry['id']


def sync_preview(app,state,data):
    from material_sets import MaterialSets
    from profile_contract import current_values,fields_for,expression_ids
    from profile_library import token
    service=MaterialSets(app);session,mapping,group=service.target(state,data['session_id'],data['website_id'])
    projected=copy.deepcopy(state);local=find(projected['sessions'],session['id']);project(projected,local)
    result=[]
    for record in data['records']:
        entry=find(service.records(projected,local,mapping),record['entry_id'])
        shared=next((e for e in state['entries'] if e['id']==entry['id']),None)
        selected=session.get('selected_sets',{}).get(group,{}).get(entry['id'],entry.get('profile_default_set_id'))
        old=current_values(state,shared,selected) if shared else {}
        fields={f['id']:f for f in fields_for(projected,entry)}
        if not isinstance(record.get('values'),dict) or set(record['values'])-fields.keys():raise LabError('字段不属于本次对象')
        shared_ids={f['id'] for f in state['fields']}
        differences=[dict(field_id=fid,label=fields[fid]['label'],old=old.get(fid,''),new=value,clear=value=='',new_definition=fid not in shared_ids,
                          impact='所选表达版本' if fid in expression_ids(projected,entry) else '本对象当前事实（各版本共用）') for fid,value in record['values'].items() if value!=old.get(fid,'')]
        website=find(session['website']['fields'],data['website_id'])
        candidates=[dict(question_id=m['website_id'],field_id=m['field_id'],label=find(website['children'],m['website_id'])['label'],field_label=fields[m['field_id']]['label'],new_definition=m['field_id'] not in shared_ids) for m in mapping.get('members',[]) if m.get('field_id') in fields]
        current=service.snapshot(projected,local,mapping,group,entry)
        if current!=record.get('expected_values'):raise LabError('本次内容已变化，请重新打开差异',409)
        item=dict(entry_id=entry['id'],edit_token=token(state,shared) if shared else None,selected_set=selected,differences=differences,relation_candidates=candidates)
        item['sync_token']=state_hash([item,current,record['values'],list(fields.values()),mapping,state.get('profile_relation_revision',0)])
        result.append(item)
    return dict(records=result,site_scope_available=bool(session['website'].get('tenant') and session['website'].get('form_key')))
