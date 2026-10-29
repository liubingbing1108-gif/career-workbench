"""P25 layout metadata: five levels, stable facts and record-local fields."""
import copy
import hashlib
from profile_schema import MODULES, fields_for

MAJORS=[('personal','个人资料'),('experience','经历'),('capability','能力与成果'),('materials','求职材料')]

def install(state):
    if 'profile_tree' not in state:
        nodes=[dict(id=k,kind='major',label=v,parent=None) for k,v in MAJORS]
        for i,(key,label,cats) in enumerate(MODULES):
            nodes.append(dict(id=key,kind='module',label=label,parent=MAJORS[0 if i<2 else 1 if i<6 else 2 if i<11 else 3][0],categories=cats))
        state['profile_tree']=dict(revision=0,nodes=nodes)
    state.setdefault('profile_layouts',{})


def gid(name):return 'group_'+hashlib.sha256(name.encode()).hexdigest()[:12]


def record_layout(state,entry,view_id=None,baseline=False):
    view_id=view_id or entry['id']
    stored=state.get('profile_layouts',{}).get(view_id)
    if stored is not None and not baseline:
        result=copy.deepcopy(stored)
        if not result.get('custom') and not result.get('fixed_fields'):
            existing={f['id'] for g in result['groups'] for f in g['fields']}
            for group in record_layout(state,entry,view_id,True)['groups']:
                additions=[f for f in group['fields'] if f['id'] not in existing]
                if not additions:continue
                target=next((g for g in result['groups'] if g['id']==group['id']),None)
                if target:target['fields'].extend(additions)
                else:result['groups'].append({**group,'fields':additions})
        return result
    module=next((m[0] for m in MODULES if entry['category'] in m[2]),'basic')
    address=view_id.endswith('__address')
    groups={}
    for f in fields_for(state,entry):
        if f.get('entry_id') and f['entry_id']!=entry['id']:continue
        is_address=f['id'].startswith(('residence_','hukou_','mailing_'))
        if entry['category']=='contact' and is_address!=address:continue
        name=f.get('group') or '其他信息'
        if entry['category']=='contact' and not address:name='邮箱' if 'email' in f['id'] else '电话'
        if entry['category']=='social':name='社交平台'
        group=groups.setdefault(name,dict(id=gid(name),label=name,fields=[],supplemental=f.get('supplemental',False)))
        group['fields'].append(dict(id=f['id'],label='联系方式' if f['id']=='social_account' else f['label']))
    title='地址' if address else '联系方式' if entry['category']=='contact' else ''
    return dict(id=view_id,entry_id=entry['id'],module_id=module,title=title,groups=list(groups.values()),archived=False)


def views(state):
    for entry in state['entries']:
        yield entry,record_layout(state,entry)
        if entry['category']=='contact':yield entry,record_layout(state,entry,entry['id']+'__address')


def active_fields(layout):
    return {f['id'] for g in layout['groups'] if not g.get('archived') for f in g['fields'] if not f.get('archived')}


def visible(state,entry,fid,session=None):
    from profile_contract import active, fields_for as current_fields
    if active(state):return fid in {f['id'] for f in current_fields(state,entry)}
    field=next((f for f in state['fields'] if f['id']==fid),{})
    if field.get('entry_id') and field['entry_id']!=entry['id']:return False
    layouts=[record_layout(state,entry)]
    if entry['category']=='contact':layouts.append(record_layout(state,entry,entry['id']+'__address'))
    if any(not l.get('archived') and fid in active_fields(l) for l in layouts):return True
    if fid not in {f['id'] for l in layouts for g in l['groups'] for f in g['fields']}:return True
    return entry['id']+'/'+fid in (session or {}).get('archived_profile_fields',[])


def mapping_fields(state):
    """Supply meanings and hierarchy labels, never raw personal values."""
    from profile_contract import active
    if active(state):return copy.deepcopy([f for f in state['fields'] if not f.get('legacy_preserved')])
    nodes={n['id']:n for n in state.get('profile_tree',{}).get('nodes',[])}
    result=copy.deepcopy(state['fields']);by_id={f['id']:f for f in result}
    for entry,layout in views(state):
        if layout.get('archived') or entry.get('profile_archived'):continue
        module=nodes.get(layout['module_id'],{});major=nodes.get(module.get('parent'),{})
        for group in layout['groups']:
            if group.get('archived'):continue
            for item in group['fields']:
                if item.get('archived') or item['id'] not in by_id:continue
                f=by_id[item['id']]
                f.setdefault('record_contexts',[]).append(dict(entry_id=entry['id'],path=[major.get('label',''),module.get('label',''),layout['title'],group['label']],label=item['label']))
    return [f for f in result if not f.get('entry_id') or f.get('record_contexts')]
