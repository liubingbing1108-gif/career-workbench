"""Confirmed semantic relations in the same profile transaction; never answers."""
import copy
from datetime import datetime, timezone
from lab import LabError, find, uid
from mapping_skill import load_bundle, context
from profile_migration import state_hash


def writeback_relation(state,session,mapping,member,entry,field,options,request_id):
    """Called inside the answer transaction after an explicit joint preview."""
    from mapping_skill import request
    from profile_contract import category_for
    if not isinstance(options,dict) or options.get('confirmed') is not True:raise LabError('请明确确认字段对应及复用范围')
    level=options.get('scope')
    if level not in {'general','site'}:raise LabError('复用范围无效')
    validator,_=load_bundle();req,_=request(state,session,session['website'],validator)
    q=copy.deepcopy(find(req['questions'],member.get('website_id') or mapping['website_id']))
    if field.get('entry_id'):q['object']['entry_id']=field['entry_id']
    rule=member.get('source_mapping',mapping)
    selector=None
    if category_for(state,entry['category'])[2]:
        selector={k:copy.deepcopy(v) for k,v in rule['requirement'].items() if k not in {'group','summary'}}
        selector['entry_ids']=[entry['id']] if field.get('entry_id') else rule.get('entry_ids',[])
    plan=dict(kind='transform' if member.get('transform') else 'alias',transform=member.get('transform'),extracts=[])
    if level=='site' and not req['site']['tenant']:raise LabError('租户与表单范围不明，不能保存本站对应')
    scope=dict(level=level,**(req['site'] if level=='site' else dict(origin='',tenant='',form_key='')),
               category=entry['category'],record_type=entry.get('record_type',''),entry_id=field.get('entry_id') or q['object']['entry_id'])
    if validator.excluded(req,q,[field['id']],scope['category'],scope['record_type'],selector,plan):raise LabError('此字段对应已被用户排除，请先纠正关系',409)
    validator.check_field({f['id']:f for f in req['catalog']},field['id'],scope['category'],scope['record_type'],q)
    validator.check_selector(selector,{f['id']:f for f in req['catalog']},scope['category'],scope['record_type'],q)
    candidate=dict(id=uid('relation'),revision=1,state='active',kind='alias',scope=scope,semantic_fingerprint=q['semantic_fingerprint'],
                   question_label=q['label'],question_context=q['section'] or '未命名分区',field_ids=[field['id']],
                   field_revisions=[dict(field_id=field['id'],revision=find(req['catalog'],field['id'])['revision'])],selector=selector,plan=plan,
                   confirmation_id=request_id,confirmation_basis='用户在回库差异中明确确认问题、属性和'+level+'复用范围',confirmed_at=datetime.now(timezone.utc).isoformat(),
                   supersedes=None,rules_version=validator.RULES,contract_version=validator.CONTRACT)
    validator.validate_shape(candidate,'relation')
    relations=state.setdefault('profile_relations',[])
    matches=[r for r in relations if r['state']=='active' and r['scope']==scope and r['semantic_fingerprint']==candidate['semantic_fingerprint']]
    if any(validator.relation_signature(r)!=validator.relation_signature(candidate) for r in matches):raise LabError('已有其他有效对应，请先纠正，当前回库未保存',409)
    if matches:return copy.deepcopy(matches[0])
    relations.append(candidate);state['profile_relation_revision']=state.get('profile_relation_revision',0)+1
    return copy.deepcopy(candidate)


def update(state, data):
    request_id=data.get('request_id')
    if not isinstance(request_id,str) or not request_id or len(request_id)>180:raise LabError('缺少关系操作请求标识')
    signature=state_hash(data);receipts=state.setdefault('profile_relation_receipts',{})
    if request_id in receipts:
        receipt=receipts[request_id]
        if receipt['signature']!=signature:raise LabError('同一请求标识不能更改内容',409)
        result=copy.deepcopy(receipt['result'])
        current=next((r for r in state.get('profile_relations',[]) if r['id']==result['relation']['id']),{})
        return {**result,'replayed':True,'current_revision':current.get('revision'),'current_state':current.get('state')}
    validator,bundle=load_bundle()
    relations=state.setdefault('profile_relations',[]);exclusions=state.setdefault('profile_relation_exclusions',[])
    revision=state.get('profile_relation_revision',0)
    if data.get('expected_relation_revision')!=revision:raise LabError('对应关系已更新，请重新查看',409)
    operation=data.get('operation')
    if operation not in {'confirm','correct','reconfirm','disable','invalidate'}:raise LabError('未知关系操作')
    old=find(relations,data['relation_id']) if data.get('relation_id') else None
    if (old or {}).get('revision',0)!=data.get('expected_revision',0):raise LabError('此对应已被修改',409)
    if old and old['state'] in {'disabled','superseded'}:raise LabError('停用或已更正的对应不能由旧确认恢复',409)
    if operation in {'disable','invalidate','correct','reconfirm'} and not old:raise LabError('缺少原对应')
    if data.get('confirmed') is not True:raise LabError('请明确确认对应内容及复用范围')
    if operation in {'disable','correct'}:
        match=data.get('exclusion_match','target')
        if match not in {'target','plan'}:raise LabError('排除类型无效')
        exclusion=dict(id=uid('exclusion'),scope=copy.deepcopy(old['scope']),semantic_fingerprint=old['semantic_fingerprint'],field_ids=old['field_ids'][:],
                       revision=revision+1,reason=data.get('reason') or '用户更正或停用',match=match,selector=copy.deepcopy(old['selector']),plan=copy.deepcopy(old['plan']))
        validator.validate_shape(exclusion,'exclusion');exclusions.append(exclusion)
    if operation in {'disable','invalidate'}:
        old.update(state='disabled' if operation=='disable' else 'needs_review',revision=old['revision']+1)
        saved=old
    else:
        session=find(state['sessions'],data.get('session_id'))
        skill=session.get('mapping_skill')
        if not skill:raise LabError('缺少本次受控对应预览')
        req=copy.deepcopy(skill['request']);resp=skill['response']
        current=context(state,session,session['website'])
        if any(current[k]!=req['context'][k] for k in ('catalog_revision','profile_revision','target_revision')):raise LabError('资料或网站已变化，请重新准备对应',409)
        decision=next((d for d in resp['decisions'] if d['question_id']==data.get('question_id')),None)
        if data.get('field_ids') is not None:
            if operation not in {'correct','reconfirm'}:raise LabError('手工选择仅用于纠正或重新核对已有对应')
            q=find(req['questions'],data.get('question_id'))
            chosen=data['field_ids'];kind=data.get('plan_kind','alias')
            if not isinstance(chosen,list) or not chosen or any(not isinstance(fid,str) for fid in chosen) or len(set(chosen))!=len(chosen):raise LabError('请选择不重复的目标字段')
            if kind not in {'alias','compose','month','year','education_level','academic_degree_level','is_full_time'}:raise LabError('对应方式无效')
            semantic='equivalent' if kind=='alias' else 'compose' if kind=='compose' else 'transform'
            decision=dict(question_id=q['id'],proposal_state='candidate',semantic_status=semantic,category=old['scope']['category'],record_type=old['scope']['record_type'],
                          selector=copy.deepcopy(old['selector']),sources=[dict(field_id=fid,covers=q['label']) for fid in chosen],alternatives=[],coverage=dict(covered=[q['label']],uncovered=[],partial=False),
                          plan=dict(kind='transform' if semantic=='transform' else kind,transform=kind if semantic=='transform' else None,extracts=[]),availability=dict(status='not_evaluated',check_id=None),relation_id=None,
                          new_attribute=None,request_expand_catalog=False,reason='用户明确纠正既有对应，保留原问题与适用范围',clarification='')
            checked={**req,'questions':[q],'relations':copy.deepcopy(relations),'exclusions':copy.deepcopy(exclusions)}
            try:validator.validate_pair(checked,dict(contract_version=validator.CONTRACT,request_id=req['request_id'],context=req['context'],decisions=[decision]),bundle['schema'])
            except ValueError as error:raise LabError('所选字段或对应方式不符合原问题范围：'+str(error),409) from error
        if not decision or decision['semantic_status'] not in {'equivalent','transform','compose','extract_candidate'}:raise LabError('此候选尚不能保存为确定对应')
        q=find(req['questions'],decision['question_id'])
        # Recheck against current exclusions and active relationships inside the transaction.
        req['relations']=copy.deepcopy(relations);req['exclusions']=copy.deepcopy(exclusions)
        ids=[s['field_id'] for s in decision['sources']]
        if validator.excluded(req,q,ids,decision['category'],decision['record_type'],decision['selector'],decision['plan']):raise LabError('此对应已被纠错排除',409)
        level=data.get('scope','site')
        if level not in {'site','general'}:raise LabError('复用范围无效')
        scope=dict(level=level,**(req['site'] if level=='site' else dict(origin='',tenant='',form_key='')),
                   category=decision['category'],record_type=decision['record_type'],entry_id=q['object']['entry_id'])
        if old and (old['scope']!=scope or old['semantic_fingerprint']!=q['semantic_fingerprint']):raise LabError('纠正须保留原问题及适用范围；不能借纠正提升为通用规则',409)
        if level=='site' and not scope['tenant']:raise LabError('尚未明确网站租户/表单范围，不能保存可复用的本站对应')
        plan={**copy.deepcopy(decision['plan']),'extracts':[]}
        candidate=dict(id=old['id'] if operation=='reconfirm' else uid('relation'),revision=(old['revision']+1 if operation=='reconfirm' else 1),state='active',
                       kind='alias' if plan['kind'] in {'alias','transform'} else 'recipe',scope=scope,semantic_fingerprint=q['semantic_fingerprint'],
                       question_label=q['label'],question_context=q['section'] or '未命名分区',field_ids=ids,
                       field_revisions=[dict(field_id=fid,revision=find(req['catalog'],fid)['revision']) for fid in ids],selector=copy.deepcopy(decision['selector']),plan=plan,
                       confirmation_id=request_id,confirmation_basis='用户确认字段对应及'+level+'复用范围',confirmed_at=datetime.now(timezone.utc).isoformat(),
                       supersedes=old['id'] if operation=='correct' else None,rules_version=validator.RULES,contract_version=validator.CONTRACT)
        validator.validate_shape(candidate,'relation')
        matching=[r for r in relations if r['state']=='active' and r is not old and r['scope']==scope and r['semantic_fingerprint']==q['semantic_fingerprint']]
        if any(validator.relation_signature(r)!=validator.relation_signature(candidate) for r in matching):raise LabError('已有不同目标的有效对应，请先纠正冲突',409)
        if matching:saved=matching[0]
        elif operation=='reconfirm':old.update(candidate);saved=old
        else:relations.append(candidate);saved=candidate
        if operation=='correct':old.update(state='superseded',revision=old['revision']+1)
    state['profile_relation_revision']=revision+1
    for session in state['sessions']:
        changed={saved['id'],(old or {}).get('id')}-{None}
        used={d.get('relation_id') for d in session.get('mapping_skill',{}).get('response',{}).get('decisions',[])}-{None}
        request=session.get('mapping_skill',{}).get('request',{})
        affected=old and any(q['semantic_fingerprint']==old['semantic_fingerprint'] and validator.scope_applies(old['scope'],q,request['site'],old['scope']['category'],old['scope']['record_type']) for q in request.get('questions',[]))
        if used & changed or affected:
            session.setdefault('preparation',{}).pop('preview',None)
            session['preparation'].pop('correction_preview',None)
            session['mapping_relations_stale']=True
    result=dict(relation=copy.deepcopy(saved),relation_revision=revision+1,profile_write='none',replayed=False)
    receipts[request_id]=dict(signature=signature,result=copy.deepcopy(result))
    return result
