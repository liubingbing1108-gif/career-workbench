"""Skill import reconciliation and atomic complete-object version decisions.

Only explicitly tagged new imports use this contract. Historical confirmed imports
are never reinterpreted. All storage remains in the existing profile state.
"""
import copy
import hashlib
import json
import re
from collections import defaultdict
from lab import LabError, find, category, default_version, validate_value, candidate_pending
from recognizer import compact


def groups(candidates):
    out=defaultdict(list)
    for c in candidates:out[c['group']].append(c)
    return out


def comparison_token(values):
    return hashlib.sha256(json.dumps(values,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def entry_values(state,entry):
    values=dict(entry.get('values',{}))
    for f in state['fields']:
        v=default_version(state,entry,f['id'])
        if v:values[f['id']]=v['content']
    return {k:v for k,v in values.items() if v}


def representations(state,entry):
    from profile_group_versions import versions
    sets=versions(state,entry)
    if not sets:return [{'id':'default','name':'当前资料','values':entry_values(state,entry)}]
    by_id={v['id']:v for store in ('versions','answer_versions') for v in state.get(store,[])}
    return [{'id':s['id'],'name':s['name'],'values':{fid:by_id[vid]['content'] for fid,vid in s['field_versions'].items() if vid in by_id and by_id[vid]['content']}} for s in sets]


def record_token(state,entry):
    return comparison_token({'values':entry_values(state,entry),'variants':representations(state,entry),'revision':entry.get('profile_revision',0),'archived':entry.get('profile_archived',False)})


def identity(cat,values,record_type=''):
    anchors={'education':['school','major','graduation_date'],'employment':['company','role','started','ended'],
             'honors':['award_name','award_date'],'projects':['project_name','project_started','project_ended'],
             'campus':['campus_title','campus_started','campus_ended'],'language':['exam_name','exam_date'] if record_type=='exam' else ['language_name'],
             'skills':['skill_name'],'certificates':['certificate_name','certificate_date']}.get(cat)
    if not category(cat)[2]:return cat
    if not anchors or not all(values.get(k) for k in anchors):return None
    return cat+':'+record_type+':'+json.dumps([compact(values[k]) for k in anchors],ensure_ascii=False)


def compatible(rows,entry):
    return entry['category']==rows[0]['category'] and not entry.get('profile_archived') and not entry.get('application_excluded') and (not rows[0].get('record_type') or not entry.get('record_type') or rows[0]['record_type']==entry['record_type'])


def conflicts(rows,old):
    result=[]
    expression={'award_name','award_details','description','project_description','campus_description','education_description','language_description','subjective_text'}
    for c in rows:
        fid=c['field_id'];a=old.get(fid,'');b=c['value']
        if not a or compact(a)==compact(b):continue
        if fid in expression or c['type'] in {'multiline','versioned_text'}:
            x=re.findall(r'\d+(?:\.\d+)?\s*[%％年月日万亿元人个次项]',a); y=re.findall(r'\d+(?:\.\d+)?\s*[%％年月日万亿元人个次项]',b)
            if x and y and set(x)!=set(y):result.append(fid)
        else:result.append(fid)
    return result


def reconcile(state):
    index={}; entries={e['id']:e for e in state['entries']}; pending={}
    for p in state['imports']:
        if p.get('parser_contract'):
            for g,rows in groups(p['candidates']).items():pending['pending:'+p['id']+'/'+g]=(p,g,rows)
    def canonical(ref,seen=None):
        seen=set(seen or [])
        if ref in seen:return ref
        seen.add(ref)
        if ref not in pending:return ref
        p,g,rows=pending[ref]
        saved=next((c.get('created_entry') for c in rows if c.get('created_entry')),None)
        if saved:return 'entry:'+saved
        decision=p.get('identity_decisions',{}).get(g)
        if decision and decision.get('entry_id'):return canonical(decision['entry_id'] if decision['entry_id'].startswith('pending:') else 'entry:'+decision['entry_id'],seen)
        vals={c['field_id']:c['value'] for c in rows}
        return identity(rows[0]['category'],vals,rows[0].get('record_type','')) or ref
    for ref,(p,g,rows) in pending.items():
        if all(c.get('saved') or c.get('disposition')=='ignore' for c in rows):continue
        before=json.dumps(rows,sort_keys=True,ensure_ascii=False)
        vals={c['field_id']:c['value'] for c in rows}; cat=rows[0]['category']; key=canonical(ref)
        decision=p.get('identity_decisions',{}).get(g); target=None;choices=[];reason=[];semantic_conflicts=[]
        if decision and decision.get('entry_id'):
            dest=canonical(decision['entry_id']) if decision['entry_id'].startswith('pending:') else 'entry:'+decision['entry_id']
            target=entries.get(dest.removeprefix('entry:'));key=dest
            if target and not compatible(rows,target):target=None;reason.append('关联资料已删除或类型变化，请重新确认')
        elif not decision:
            exact=[e for e in state['entries'] if compatible(rows,e) and identity(cat,entry_values(state,e),e.get('record_type',''))==key]
            if len(exact)==1:target=exact[0];key='entry:'+target['id']
            for e in state['entries']:
                if not compatible(rows,e) or not entry_values(state,e):continue
                old=entry_values(state,e)
                if cat=='employment' and vals.get('company') and vals.get('role') and all(compact(vals.get(f,''))==compact(old.get(f,'')) for f in ('company','role')):choices.append(e['id'])
                if cat=='honors' and vals.get('award_name') and compact(vals['award_name'])==compact(old.get('award_name','')):choices.append(e['id'])
            for hint in p.get('comparison_hints',{}).get(g,[]):
                eid=hint['target_id'];e=entries.get(eid)
                if e and compatible(rows,e) and comparison_token(entry_values(state,e))==hint['target_token']:
                    choices.append(eid);reason.append(hint.get('reason',''));semantic_conflicts.extend(hint.get('conflict_fields',[]))
                elif e and compatible(rows,e):
                    choices.append(eid);reason.append('已有资料在语义比较后发生变化，请重新核对关联')
                elif eid in pending:
                    _,_,other=pending[eid]
                    if comparison_token({c['field_id']:c['value'] for c in other})==hint['target_token']:
                        dest=canonical(eid);saved_target=entries.get(dest.removeprefix('entry:'))
                        choices.append(saved_target['id'] if saved_target else eid);reason.append(hint.get('reason',''))
            if p.get('comparison_failed') and not target:
                choices.extend(e['id'] for e in state['entries'] if compatible(rows,e) and entry_values(state,e))
                choices.extend(r for r,(_,_,other) in pending.items() if r!=ref and other[0]['category']==cat and not all(c.get('disposition')=='ignore' for c in other))
                reason.append('语义比较未完成，请核对已有对象；不同则选择独立资料')
            if target:choices=[]
        elif not decision.get('entry_id'):key=ref+'/separate'
        # Keep the semantic conflict finding after the user's identity decision.
        if target:
            for hint in p.get('comparison_hints',{}).get(g,[]):
                if hint['target_id']==target['id'] and comparison_token(entry_values(state,target))==hint['target_token']:semantic_conflicts.extend(hint.get('conflict_fields',[]))
        if not target:
            target=next((e for e in state['entries'] if e.get('resume_identity')==key and compatible(rows,e)),None)
        versions=representations(state,target) if target else []
        same=any(all(compact(v['values'].get(f,''))==compact(value) for f,value in vals.items()) for v in versions)
        old=entry_values(state,target) if target else {}; factual=sorted(set(conflicts(rows,old)+semantic_conflicts)) if target else []
        choices=list(dict.fromkeys(choices)); validation=any(c.get('validation_issues') for c in rows)
        duplicate=index.get((key,comparison_token(vals))) if not target and not choices else None
        status='需核验原文' if validation else '需确认归属' if choices else '一致' if same else '已合并' if duplicate else '事实冲突' if factual else '表述版本待确认' if target else '新增'
        options=[]
        for eid in choices:
            if eid.startswith('pending:'):
                q,_,rr=pending[eid];options.append({'id':eid,'label':q['filename']+' · '+rr[0].get('group_title','待处理资料')})
            else:options.append({'id':eid,'label':str(next(iter(entry_values(state,entries[eid]).values()),eid))})
        for c in rows:
            c.update(import_id=p['id'],identity_key=key,entry_id=target['id'] if target else None,
                     identity_review=bool(choices),identity_choices=choices,identity_options=options,identity_reason='；'.join(dict.fromkeys(reason)),
                     existing=old.get(c['field_id'],''),existing_versions=[],default_version_id=None,
                     representation_versions=versions,conflict_fields=factual,duplicate_of=duplicate,
                     target_token=record_token(state,target) if target else None)
            if not c.get('saved') and c.get('disposition')!='ignore':
                c['status']=status;c['selected']=status=='新增'
            elif c.get('disposition')=='ignore':c['status']='已忽略';c['selected']=False
        if not duplicate and not choices:index[(key,comparison_token(vals))]=rows[0]['id']
        if before!=json.dumps(rows,sort_keys=True,ensure_ascii=False):p['revision']=p.get('revision',1)+1


def resolve(lab,state,decisions):
    from profile_group_versions import save_group, base_version, set_defaults
    rows_by_id={c['id']:(p,c) for p in state['imports'] for c in p['candidates'] if p.get('parser_contract')}
    requested={d['candidate_id']:d for d in decisions};saved=ignored=0;receipts=[]
    affected=defaultdict(list)
    initial_tokens={e['id']:record_token(state,e) for e in state['entries']}
    for cid,d in requested.items():
        if cid not in rows_by_id:raise LabError('增量记录不存在')
        p,c=rows_by_id[cid];affected[(p['id'],c['group'])].append(d)
    for (pid,g),chosen in affected.items():
        p=find(state['imports'],pid);rows=[c for c in p['candidates'] if c['group']==g];first=rows[0]
        if all(not candidate_pending(c) for c in rows):continue
        if set(d['candidate_id'] for d in chosen)!={c['id'] for c in rows if candidate_pending(c)} or len({d['mode'] for d in chosen})!=1:raise LabError('请按完整资料组处理',409)
        mode=chosen[0]['mode']
        if mode not in {'replace','new','ignore'}:raise LabError('请选择保留本次版、都保留或保留已有版/忽略')
        if mode=='ignore':
            for c in rows:c.update(disposition='ignore',status='已忽略',selected=False);ignored+=1
            p.setdefault('ignored_groups',[]).append(comparison_token({c['field_id']:c['value'] for c in rows}))
            continue
        if first.get('identity_review'):raise LabError('请先确认是否同一条资料',409)
        if any(c.get('validation_issues') for c in rows):raise LabError('原文或字段对应尚未核验，不能保存此组',409)
        target=find(state['entries'],first['entry_id']) if first.get('entry_id') else None
        if target and initial_tokens.get(target['id'])!=first.get('target_token'):raise LabError('资料或版本已变化，请刷新增量预览',409)
        if not target:
            target=next((e for e in state['entries'] if e.get('resume_identity')==first['identity_key']),None)
        is_new=target is None
        if is_new:
            target=lab.new_entry(state,first['category']);target['resume_identity']=first['identity_key'];target['record_type']=first.get('record_type','')
        values={};sources={}
        for c in rows:
            d=requested.get(c['id'],{});value=d.get('value') if d.get('value') is not None else c['value']
            definition=next((f for f in state['fields'] if f['id']==c['field_id']),None)
            if definition is None:
                definition=copy.deepcopy(c['definition'])
                if any(f['category']==definition['category'] and definition['label'] in [f['label'],*f.get('aliases',[])] for f in state['fields']):raise LabError('已有同义字段，请重新核对对应',409)
                state['fields'].append(definition)
            if definition['category']!=target['category'] or definition.get('entry_id') and definition['entry_id']!=target['id']:raise LabError('字段不属于此对象')
            values[c['field_id']]=validate_value(definition,value);sources[c['field_id']]=c['source']
        factual=conflicts([{**c,'value':values[c['field_id']]} for c in rows],entry_values(state,target)) if not is_new else []
        semantic=[fid for fid in first.get('conflict_fields',[]) if values.get(fid)==next((c['value'] for c in rows if c['field_id']==fid),None)]
        if not is_new and (factual or semantic):
            if mode=='new':raise LabError('事实冲突不能用都保留跳过；请核对事实后保留本次版或保留已有版',409)
            if not all(d.get('confirm_facts') is True for d in chosen):raise LabError('请明确确认采用本次事实后再保存',409)
        default_id=target.get('profile_default_set_id','default')
        if not is_new and mode=='new':target['import_representation_versions']=True
        # Snapshot the existing complete group before adding an alternative.
        if not is_new:target.setdefault('profile_base_version',base_version(state,target))
        from profile_hierarchy import record_layout
        layout=copy.deepcopy(record_layout(state,target))
        present={f['id'] for g in layout['groups'] for f in g['fields']}
        extra=[{'id':fid,'label':find(state['fields'],fid)['label']} for fid in values if fid not in present]
        if extra:layout['groups'].append({'id':'import_extra','label':'补充资料','fields':extra})
        result=save_group(state,target,values,mode='update' if is_new or mode=='replace' else 'new',set_id=default_id,
                          name=p['filename'],versioned=True,layout=layout)
        if mode=='replace' and not is_new:
            # Keep only incoming as an active representation, retain historical refs.
            target['profile_deleted_sets']=[v['id'] for v in [base_version(state,target),*target.get('set_versions',[])] if v['id']!=result['id']]
        by_id={v['id']:v for store in ('versions','answer_versions') for v in state.get(store,[])}
        for fid,source in sources.items():
            vid=result['field_versions'][fid];v=by_id[vid]
            v.setdefault('import_sources',[])
            if source not in v['import_sources']:v['import_sources'].append(copy.deepcopy(source))
            if v.get('source',{}).get('kind')=='manual':v['source']=copy.deepcopy(source)
        if is_new or mode=='replace':set_defaults(state,target,result['field_versions'])
        target['profile_revision']=target.get('profile_revision',0)+1
        for c in rows:c.update(saved=True,disposition=mode,created_entry=target['id'],saved_set_id=result['id']);saved+=1
        receipt={'entry_id':target['id'],'set_id':result['id'],'field_values':values}
        # Verify selected set, not defaults (which deliberately stay unchanged on both).
        actual=next(v for v in representations(state,target) if v['id']==result['id'])['values']
        if any(actual.get(k,'')!=v for k,v in values.items()):raise LabError('保存回读不一致',409)
        receipts.append(receipt)
    return {'saved':saved,'ignored':ignored,'groups':receipts}
