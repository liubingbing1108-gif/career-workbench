"""P27: user-visible versions belong to a complete record, never a field."""
import copy
from lab import all_versions,default_version,put_answer,find,uid,LabError

VERSION_MODULES={'employment','projects','campus','preferences','subjective'}

def enabled(state,entry,layout=None):
    from profile_contract import active, EXPRESSIONS
    if active(state):return entry['category'] in EXPRESSIONS
    from profile_hierarchy import record_layout
    return bool(entry.get('import_representation_versions')) or (layout or record_layout(state,entry))['module_id'] in VERSION_MODULES

def base_version(state,entry):
    from profile_contract import active
    if active(state):
        return copy.deepcopy(next((v for v in entry.get('expression_versions',[]) if v['id']==entry.get('profile_default_set_id')),dict(id=None,name='',field_versions={})))
    return copy.deepcopy(entry.get('profile_base_version') or dict(id='default',name=entry.get('profile_default_name') or '版本1',field_versions={f['id']:(default_version(state,entry,f['id']) or {}).get('id') for f in state['fields'] if f['category']==entry['category'] and (not f.get('entry_id') or f['entry_id']==entry['id'])}))

def versions(state,entry):
    from profile_contract import active
    if active(state):return copy.deepcopy([v for v in entry.get('expression_versions',[]) if not v.get('deleted_at')]) if enabled(state,entry) else []
    if not enabled(state,entry):return []
    hidden=entry.get('profile_deleted_sets',[])
    return [v for v in [base_version(state,entry),*copy.deepcopy(entry.get('set_versions',[]))] if v['id'] not in hidden and not v.get('profile_deleted')]

def set_defaults(state,entry,refs):
    for fid,vid in refs.items():
        if vid:
            v=find(all_versions(state,entry['id'],fid),vid)
            entry.setdefault('default_versions',{})[fid]=vid
            if find(state['fields'],fid)['type']!='versioned_text':
                entry['values'][fid]=v['content'];entry['sources'][fid]=v.get('source',{})

def save_group(state,entry,values,*,mode='update',set_id='default',name='',layout=None,versioned=True):
    from profile_contract import active
    if active(state):
        from profile_current import save_values
        return save_values(state,entry,values,mode=mode,set_id=set_id,name=name)
    if mode=='new' and not versioned:raise LabError('这个子模块不使用版本，请直接保存资料组')
    if versioned:entry.setdefault('profile_base_version',base_version(state,entry))
    selected=entry['profile_base_version'] if versioned and set_id=='default' else next((v for v in entry.get('set_versions',[]) if v['id']==set_id),None)
    if mode=='update' and versioned and (not selected or selected.get('profile_deleted') or set_id in entry.get('profile_deleted_sets',[])):
        raise LabError('当前资料组版本已删除，请另存为新版本',409)
    prior_defaults=copy.deepcopy(entry.get('default_versions',{}));prior_values=copy.deepcopy(entry['values']);prior_sources=copy.deepcopy(entry['sources'])
    refs={**(selected['field_versions'] if selected else prior_defaults)}
    # Immutable field storage protects other record versions, even when values were shared.
    for fid,value in values.items():
        field=find(state['fields'],fid)
        refs[fid]=put_answer(state,entry,field,value,mode='new',name='资料组内容')['id']
    entry['default_versions']=prior_defaults;entry['values']=prior_values;entry['sources']=prior_sources
    if not versioned:
        set_defaults(state,entry,refs);return dict(id='default',field_versions=refs)
    had_versions=bool(versions(state,entry))
    if mode=='new':
        saved=dict(id=uid('set'),name=name or '版本'+str(len(entry.get('set_versions',[]))+2),field_versions=refs)
        entry.setdefault('set_versions',[]).append(saved)
    else:
        saved=selected;saved['field_versions']=refs
        if name:saved['name']=name
    if layout is None:
        from profile_hierarchy import record_layout
        layout=copy.deepcopy((selected or {}).get('layout') or record_layout(state,entry))
    layout['fixed_fields']=True
    entry['profile_base_version'].setdefault('layout',copy.deepcopy(layout))
    saved['layout']=copy.deepcopy(layout)
    if mode=='new' and not had_versions:
        entry['profile_default_set_id']=saved['id'];set_defaults(state,entry,refs)
    if mode=='update' and set_id==entry.get('profile_default_set_id','default'):set_defaults(state,entry,refs)
    return saved
