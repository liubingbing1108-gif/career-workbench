"""Display names and explicitly equivalent local-field merges, with provenance."""
import copy
import time
from lab import LabError, find
from profile_contract import active, fields_for, current_values
from profile_migration import state_hash


def field(state, fid):
    if not active(state):raise LabError('此操作需要新版资料契约',409)
    result=find(state['fields'],fid)
    if result.get('legacy_preserved'):raise LabError('旧定义仅供追溯，不能改名或再次合并',409)
    return result


def compatible(source, target):
    return source['id']!=target['id'] and all(source.get(k,default)==target.get(k,default)
        for k,default in [('category',''),('type','text'),('widget',None),('unit',''),('scale',''),('value_role','fact'),('options',[])])


def preview(state, data):
    source=field(state,data.get('field_id'))
    result=dict(field=copy.deepcopy(source),token=state_hash(source))
    if data.get('operation','rename')=='rename':return result
    if data.get('operation')!='merge':raise LabError('未知字段操作')
    if source.get('preset_id') or not source.get('entry_id') or source.get('value_role','fact')!='fact':raise LabError('仅可合并当前对象的自定义事实字段；预设定义和旧全局字段保留独立身份')
    entry=find(state['entries'],source['entry_id'])
    if entry.get('profile_archived') or entry.get('purged') or entry.get('legacy_only'):raise LabError('请先恢复并核对此对象',409)
    targets=[f for f in fields_for(state,entry) if compatible(source,f)]
    result['targets']=[dict(id=f['id'],label=f['label']) for f in targets]
    if not data.get('target_id'):return result
    target=next((f for f in targets if f['id']==data['target_id']),None)
    if not target:raise LabError('合并目标的类型、单位或对象范围不一致',409)
    from profile_library import token
    values=current_values(state,entry)
    result.update(target=copy.deepcopy(target),entry_id=entry['id'],source_value=values.get(source['id'],''),target_value=values.get(target['id'],''))
    result['token']=state_hash([source,target,token(state,entry),state.get('profile_relations',[]),state.get('profile_relation_exclusions',[])])
    return result


def references(value, fid):
    if isinstance(value,list):return any(references(v,fid) for v in value)
    if not isinstance(value,dict):return False
    return value.get('field_id')==fid or fid in value.get('field_ids',[]) or any(
        (key==fid or key.endswith('/'+fid)) or references(child,fid) for key,child in value.items())


def redirect(value, source, target):
    if isinstance(value,list):return [redirect(v,source,target) for v in value]
    if not isinstance(value,dict):return value
    return {k:(target if k=='field_id' and v==source else
               list(dict.fromkeys(target if fid==source else fid for fid in v)) if k=='field_ids' else redirect(v,source,target)) for k,v in value.items()}


def refresh_relations(state, fid, before_revision, *, source_id=None):
    from mapping_skill import load_bundle
    validator,_=load_bundle();revision=int(state_hash(field(state,fid))[:8],16);changed=False
    for relation in state.get('profile_relations',[]):
        if source_id and references(relation,source_id):
            original=copy.deepcopy(relation)
            relation.update(redirect(relation,source_id,fid))
            # Multiple old inputs collapsing to one changes composition semantics.
            if len(relation['field_ids'])!=len(original['field_ids']):relation['state']='needs_review'
            relation['field_revisions']=[dict(field_id=key,revision=int(state_hash(field(state,key))[:8],16)) for key in relation['field_ids']]
            state.setdefault('profile_relation_redirects',[]).append(dict(before=original,after_id=relation['id'],source_id=source_id,target_id=fid))
            relation['revision']+=1;changed=True
        elif fid in relation['field_ids']:
            for dependency in relation['field_revisions']:
                if dependency['field_id']==fid and dependency['revision']==before_revision:dependency['revision']=revision
            relation['revision']+=1;changed=True
    if source_id:
        for exclusion in state.get('profile_relation_exclusions',[]):
            if references(exclusion,source_id):
                state.setdefault('profile_exclusion_redirects',[]).append(copy.deepcopy(exclusion))
                exclusion.update(redirect(exclusion,source_id,fid));exclusion['revision']+=1;changed=True
    relations=state.get('profile_relations',[])
    for relation in relations:
        if relation['state']!='active':continue
        peers=[r for r in relations if r['state']=='active' and r['scope']==relation['scope'] and r['semantic_fingerprint']==relation['semantic_fingerprint']]
        if len({validator.relation_signature(r) for r in peers})>1:
            for r in peers:r.update(state='needs_review',revision=r['revision']+1)
    if changed:state['profile_relation_revision']=state.get('profile_relation_revision',0)+1


def update(state, data):
    request_id=data.get('request_id')
    if not isinstance(request_id,str) or not request_id or len(request_id)>180:raise LabError('缺少字段操作请求标识')
    receipts=state.setdefault('profile_field_receipts',{});signature=state_hash(data)
    if request_id in receipts:
        saved=receipts[request_id]
        if saved['signature']!=signature:raise LabError('字段请求标识已用于不同内容',409)
        return {**copy.deepcopy(saved['result']),'replayed':True}
    shown=preview(state,data)
    if shown['token']!=data.get('token'):raise LabError('字段或内容已更新，请重新核对',409)
    source=field(state,data['field_id']);operation=data.get('operation','rename')
    if operation=='rename':
        label=data.get('label','')
        if not isinstance(label,str) or not label.strip() or len(label)>100:raise LabError('名称须为1至100字')
        label=label.strip()
        if any(f['id']!=source['id'] and label.casefold() in {str(x).strip().casefold() for x in [f['label'],*f.get('aliases',[])]} for f in state['fields']):raise LabError('此名称已用于另一字段；等价字段请核对后合并',409)
        before=copy.deepcopy(source);revision=int(state_hash(source)[:8],16)
        source.setdefault('meaning',source['label'])
        source['aliases']=list(dict.fromkeys([*source.get('aliases',[]),source['label'],label]))
        source.update(label=label,display_label=label)
        refresh_relations(state,source['id'],revision)
        state.setdefault('profile_field_history',[]).append(dict(operation='rename',before=before,after=copy.deepcopy(source),request_id=request_id,at=time.time()))
        result=dict(field=copy.deepcopy(source),replayed=False)
    else:
        if 'target' not in shown or data.get('confirmed_equivalent') is not True:raise LabError('请明确确认两字段含义、单位和对象范围等价')
        choice=data.get('value_choice')
        if choice not in {'source','target'}:raise LabError('请选择合并后采用哪份当前内容')
        if choice=='source' and shown['source_value']=='' and shown['target_value'] and data.get('confirmed_clear') is not True:raise LabError('采用空值会清空目标当前内容，请明确确认')
        sid=source['id'];target=field(state,data['target_id']);tid=target['id'];entry=find(state['entries'],shown['entry_id'])
        affected=[s for s in state['sessions'] if references(s.get('website',{}),sid)]
        if any(s.get('preparation',{}).get('execution',{}).get('status') in {'running','awaiting_executor'} or s.get('preparation',{}).get('execution',{}).get('stop_unconfirmed') for s in affected):raise LabError('此字段仍有执行任务，请先停止并确认后合并',409)
        audit=dict(operation='merge',source=copy.deepcopy(source),target=copy.deepcopy(target),entry_id=entry['id'],source_value=shown['source_value'],target_value=shown['target_value'],value_choice=choice,source_ref=entry.get('default_versions',{}).get(sid),target_ref=entry.get('default_versions',{}).get(tid),request_id=request_id,at=time.time())
        if choice=='source':
            from profile_current import save_values
            save_values(state,entry,{tid:shown['source_value']})
        target_revision=int(state_hash(target)[:8],16)
        # A local alias must not become an alias on a global preset for all objects.
        if target.get('entry_id')==entry['id']:target['aliases']=list(dict.fromkeys([*target.get('aliases',[]),source['label'],*source.get('aliases',[])]))
        refresh_relations(state,tid,target_revision,source_id=sid)
        source.update(legacy_preserved=True,merged_into=tid)
        state.setdefault('profile_field_redirects',{})[sid]=tid
        state.setdefault('profile_field_history',[]).append(audit)
        entry['profile_revision']=entry.get('profile_revision',0)+1
        for session in affected:
            session['mapping_relations_stale']=True
            session.setdefault('preparation',{}).pop('preview',None);session['preparation'].pop('correction_preview',None)
        for draft in state.get('profile_drafts',{}).values():
            if references(draft.get('body',{}),sid):draft['reference_invalid']=True
        result=dict(field=copy.deepcopy(target),merged_field_id=sid,entry_id=entry['id'],replayed=False)
    receipts[request_id]=dict(signature=signature,result=copy.deepcopy(result))
    return result
