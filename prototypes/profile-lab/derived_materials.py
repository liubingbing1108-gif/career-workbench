"""Preview and confirm session-only composed/extracted material with source revision guards."""
import copy
from lab import LabError, find
from profile_migration import state_hash
from profile_contract import category_for


def preview(app, state, sid, wid, entry_ids=None):
    from application import entry_material, group_id
    from application_current import project
    state=copy.deepcopy(state);session=find(state['sessions'],sid);project(state,session)
    mapping=next((m for m in session.get('website',{}).get('mappings',[]) if m['website_id']==wid),None)
    decision=(mapping or {}).get('semantic_decision',{})
    status=decision.get('semantic_status')
    if status not in {'compose','extract_candidate','unresolved','ambiguous'} or not decision.get('sources'):raise LabError('此问题尚无可核对的来源方案')
    group=group_id(mapping);field=find(session['website']['fields'],wid)
    if category_for(state,mapping['category'])[2]:
        if entry_ids is not None:
            if not isinstance(entry_ids,list) or len(entry_ids)!=len(set(entry_ids)):raise LabError('来源对象选择无效')
            session.setdefault('group_choices',{})[group]=entry_ids
        selected,options,issues,_=app._group(state,session,mapping,session['website']['fields'])
    else:
        from profile_schema import available
        selected=[entry_material(state,session,e,group) for e in state['entries'] if e['category']==mapping['category'] and available(e,session)]
        options=selected;issues=[]
    sources=[]
    for entry in selected:
        for ref in decision['sources']:
            choice=next((c for c in entry['choices'] if c['field']['id']==ref['field_id']),None)
            if not choice:raise LabError('组合来源字段已不可用',409)
            if not choice['content']:issues.append(dict(message=choice['field']['label']+'缺少当前内容'))
            sources.append(dict(entry_id=entry['id'],field_id=ref['field_id'],label=choice['field']['label'],
                                value=choice['content'],version_id=(choice.get('selected') or {}).get('id'),
                                revision=(choice.get('selected') or {}).get('revision'),set_id=entry.get('selected_set')))
    if not sources:issues.append(dict(message='请选择有效来源对象'))
    suggestion='\n'.join(s['value'] for s in sources if s['value'])
    if decision['semantic_status']=='extract_candidate':
        source_request=session.get('extraction_requests',{}).get(wid,session.get('mapping_skill',{})).get('request',{})
        spans={x['id']:x for x in source_request.get('source_spans',[])}
        pieces=[]
        for extract in decision['plan']['extracts']:
            span=spans.get(extract.get('span_id'))
            if not span:raise LabError('摘取来源已过期，请重新核对最小原文',409)
            source=next((s for s in sources if s['entry_id']==span['entry_id'] and s['field_id']==span['field_id']),None)
            evidence=session.get('extraction_requests',{}).get(wid,{})
            if not source or source['version_id']!=span['version_id'] or (source['revision'] or 0)!=span['revision'] or evidence.get('source_value_hash',state_hash(source['value']))!=state_hash(source['value']):raise LabError('摘取所用对象版本或本次内容已变化',409)
            pieces.append(span['text'][extract['start']:extract['end']])
        suggestion='\n'.join(pieces)
    result=dict(website_id=wid,label=field['label'],sources=sources,suggestion=suggestion,
                selected_ids=[e['id'] for e in selected],options=[dict(id=e['id'],values=e['values']) for e in options],
                issues=[i['message'] for i in issues],semantic_status=decision['semantic_status'],needs_excerpt=status in {'unresolved','ambiguous'})
    result['token']=state_hash([mapping,field,sources,result['selected_ids'],session.get('mapping_skill',{}).get('bundle_sha256')])
    return result


def confirm(app,state,data):
    from application import value_error
    session=find(state['sessions'],data['session_id']);wid=data['website_id']
    fresh=preview(app,state,session['id'],wid,data.get('entry_ids'))
    if fresh['needs_excerpt']:raise LabError('来源含义尚未明确，请先核对摘取方案')
    if fresh['token']!=data.get('token') or fresh['issues']:raise LabError('来源已变化或未完整，请重新核对草稿',409)
    if data.get('confirmed') is not True:raise LabError('请确认组合或摘取后的本次内容')
    value=data.get('value')
    if not isinstance(value,str) or len(value)>30000:raise LabError('草稿内容无效')
    website=find(session['website']['fields'],wid);error=value_error(value,website)
    if error:raise LabError(error)
    session.setdefault('derived_answers',{})[wid]=dict(value=value,token=fresh['token'],entry_ids=fresh['selected_ids'],sources=fresh['sources'])
    session.setdefault('preparation',{}).pop('preview',None)
    return dict(mode='session',website_id=wid,value=value)


def confirmed_value(app,state,session,mapping):
    saved=session.get('derived_answers',{}).get(mapping['website_id'])
    if not saved:return None
    try:fresh=preview(app,state,session['id'],mapping['website_id'],saved['entry_ids'])
    except LabError:return None
    return saved['value'] if fresh['token']==saved['token'] and not fresh['issues'] else None


def request_excerpt(app,data):
    """Only a user-selected local excerpt crosses the configured model boundary."""
    from mapping_skill import load_bundle,request
    from lab import uid
    import json
    if data.get('confirmed_excerpt') is not True:raise LabError('请确认仅发送选中的原文片段')
    if not app.mapper:raise LabError('尚未配置字段对应模型',503)
    state=app.lab.state();sid=data['session_id'];wid=data['website_id'];session=find(state['sessions'],sid)
    current=preview(app,state,sid,wid,data.get('entry_ids'))
    if current['token']!=data.get('token') or current['issues']:raise LabError('来源已变化，请重新选择最小原文',409)
    source=next((s for s in current['sources'] if s['entry_id']==data.get('entry_id') and s['field_id']==data.get('field_id')),None)
    start,end=data.get('start'),data.get('end')
    if not source or type(start) is not int or type(end) is not int or not 0<=start<end<=len(source['value']) or end-start>4000:raise LabError('请选择一个来源字段中不超过4000字的最小片段')
    validator,bundle=load_bundle();req,_=request(state,session,session['website'],validator)
    req['questions']=[copy.deepcopy(find(req['questions'],wid))]
    req['questions'][0]['object'].update(entry_id=source['entry_id'],allowed_entry_ids=[source['entry_id']])
    span=dict(id=uid('span'),field_id=source['field_id'],entry_id=source['entry_id'],version_id=source['version_id'],revision=source['revision'] or 0,text=source['value'][start:end])
    req['source_spans']=[span]
    prompt=bundle['rules']+'\n仅核对用户选中的最小原文，返回来源范围摘取候选；不能补写原文外事实。仍不明确则返回未解决。\n'+json.dumps(req,ensure_ascii=False)
    from mapping_skill import model_response_schema
    response,usage=app.mapper.call(prompt,model_response_schema(bundle))
    validator.validate_pair(req,response,bundle['schema'])
    decision=response['decisions'][0]
    if decision['semantic_status']!='extract_candidate' or {s['field_id'] for s in decision['sources']}!={source['field_id']}:raise LabError('模型仍未确认可用的摘取范围；原文与草稿保持不变',409)
    def save(latest):
        fresh=preview(app,latest,sid,wid,data.get('entry_ids'))
        if fresh['token']!=current['token']:raise LabError('摘取期间来源或对应已变化，候选未采用',409)
        owner=find(latest['sessions'],sid);mapping=next(m for m in owner['website']['mappings'] if m['website_id']==wid)
        mapping['semantic_decision']=copy.deepcopy(decision);mapping['status']='ambiguous'
        if mapping.get('requirement'):
            mapping['requirement'].update({k:v for k,v in decision['selector'].items() if k!='entry_ids'})
            mapping['entry_ids']=[source['entry_id']]
        owner.setdefault('extraction_requests',{})[wid]=dict(request=req,response=response,usage=usage,source_value_hash=state_hash(source['value']))
        owner.setdefault('preparation',{}).pop('preview',None)
        return dict(website_id=wid,status='draft_required')
    return app.lab.mutate(save)
