"""P48 selected-difference import, retaining the original source-review gates."""
import copy
from collections import defaultdict
from lab import LabError, find, candidate_pending
from profile_contract import EXPRESSIONS, current_values, fields_for
from profile_current import save_values
from resume_import import record_token

EXAM_RESULT = {'language_score', 'obtained_date', 'exam_components', 'exam_files', 'exam_level'}


def resolve_selected(lab, state, decisions):
    lookup = {c['id']:(p,c) for p in state['imports'] for c in p['candidates']}
    affected = defaultdict(list)
    for decision in decisions:
        if decision.get('candidate_id') not in lookup:raise LabError('候选不存在')
        preview,candidate = lookup[decision['candidate_id']]
        if candidate_pending(candidate):affected[(preview['id'],candidate['group'])].append((decision,candidate))
    saved=ignored=0;receipts=[]
    initial={e['id']:record_token(state,e) for e in state['entries']}
    for (pid,group),chosen in affected.items():
        preview=find(state['imports'],pid)
        rows=[c for c in preview['candidates'] if c['group']==group]
        first=rows[0]
        incoming=[]
        for decision,c in chosen:
            mode=decision.get('mode')
            if mode not in {'replace','new','ignore'}:raise LabError('请选择采用、另存或忽略')
            if mode=='ignore':c.update(disposition='ignore',selected=False,status='已忽略');ignored+=1
            else:incoming.append((decision,c))
        if not incoming:continue
        # Source uncertainty belongs to the object; selecting a subset cannot bypass it.
        if first.get('identity_review') or any(c.get('validation_issues') for c in rows):
            raise LabError('此对象的归属或原文尚未核验，请先核对；其他对象可先保存',409)
        if len({d['mode'] for d,c in incoming})!=1:raise LabError('同一对象请使用一致保存方式')
        mode=incoming[0][0]['mode']
        target=find(state['entries'],first['entry_id']) if first.get('entry_id') else None
        if target and initial[target['id']]!=first.get('target_token'):raise LabError('已有资料已变化，请重新比较',409)
        if target and mode=='new' and target['category'] not in EXPRESSIONS:raise LabError('此类资料只保留一个当前内容，请选择采用本次变化')
        if target and target.get('legacy_only'):raise LabError('请先处理旧资料迁移',409)
        is_new=target is None
        if is_new:
            target=lab.new_entry(state,first['category'])
            target.update(record_type=first.get('record_type',''),resume_identity=first.get('identity_key'))
        allowed={f['id']:f for f in fields_for(state,target)}
        values={};sources={}
        for decision,c in incoming:
            fid=c['field_id']
            if fid not in allowed:
                # New semantic attributes require explicit definition approval, never silently revive a removed preset.
                existing=next((f for f in state['fields'] if f['id']==fid),None)
                if existing or decision.get('confirm_new_field') is not True:raise LabError('字段不在当前目录，需明确确认新定义')
                definition=copy.deepcopy(c.get('definition',{}))
                if definition.get('id')!=fid or not definition.get('label'):raise LabError('新字段定义与候选不一致')
                if definition.get('category')!=target['category'] or definition.get('record_types') and target.get('record_type') not in definition['record_types']:raise LabError('新字段对象类型不符')
                if any(f['category']==definition['category'] and definition.get('label') in [f['label'],*f.get('aliases',[])] for f in state['fields']):raise LabError('已有同义字段，请重新对应')
                definition.update(entry_id=target['id'],value_role='fact',save_unit='object')
                state['fields'].append(definition);allowed[fid]=definition
            value=decision.get('value',c['value'])
            if value=='' and not decision.get('clear'):continue
            values[fid]=value;sources[fid]=c['source']
        if not values:
            if is_new:state['entries'].remove(target)
            continue
        if not is_new and target['category']=='language' and target.get('record_type')=='exam':
            old=current_values(state,target)
            changed=any(old.get(fid,'') for fid in EXAM_RESULT) and any(fid in EXAM_RESULT and old.get(fid,'')!=value for fid,value in values.items())
            if changed:
                if not all(d.get('confirm_exam_result') is True for d,c in incoming):raise LabError('请确认采用同一次考试的完整结果，缺失日期/分项将留空',409)
                candidate_ids={c['id'] for c in rows if c['field_id'] in EXAM_RESULT and candidate_pending(c)}
                if not candidate_ids.issubset({c['id'] for d,c in incoming}):raise LabError('考试新结果的成绩、日期、分项和证明必须一起确认',409)
                values={**{fid:'' for fid in EXAM_RESULT if fid in allowed},**values}
        selected=incoming[0][0].get('set_id',target.get('profile_default_set_id'))
        result=save_values(state,target,values,mode='update' if is_new or mode=='replace' else 'new',set_id=selected,name=incoming[0][0].get('name','导入表达'))
        by_id={v['id']:v for key in ('versions','answer_versions') for v in state.get(key,[])}
        for fid,source in sources.items():
            ref=result['field_versions'].get(fid)
            if ref:
                version=by_id[ref];version.setdefault('import_sources',[])
                if source not in version['import_sources']:version['import_sources'].append(copy.deepcopy(source))
                if version.get('source',{}).get('kind')=='manual':version['source']=copy.deepcopy(source)
        actual=current_values(state,target,result['id'])
        if any(actual.get(fid,'')!=value for fid,value in values.items()):raise LabError('导入回读不一致',409)
        for decision,c in incoming:
            if c['field_id'] in values:
                c.update(saved=True,disposition=mode,created_entry=target['id'],saved_set_id=result['id']);saved+=1
        # Remaining candidates keep the same confirmed object without being silently adopted.
        preview.setdefault('identity_decisions',{})[group]={'entry_id':target['id']}
        receipts.append(dict(entry_id=target['id'],set_id=result['id'],field_values=values))
    return dict(saved=saved,ignored=ignored,groups=receipts)
