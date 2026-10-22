"""Optional clarification form. Answers affect only an import draft until saved."""
import copy
import hashlib
import json
import re

SOURCE_PENDING = '原件归属待确认：'


def question_locked(p, q):
    return any(c.get('saved') and (not q['group'] or c['group']==q['group']) for c in p['candidates'])


def sync_source_issues(p):
    """Skipping a source question is not evidence that its object binding is correct."""
    for c in p['candidates']:
        if c.get('saved'):continue
        c['validation_issues']=[s for s in c.get('validation_issues',[]) if not s.startswith(SOURCE_PENDING)]
        for q in p.get('review_questions',[]):
            if q['kind']!='source' or q['group'] and q['group']!=c['group']:continue
            a=p.get('review_answers',{}).get(q['id'],{})
            if a.get('action')=='confirm' or a.get('action')=='apply' and a.get('values'):continue
            c['validation_issues'].append(SOURCE_PENDING+q['prompt'])


def question_schema():
    def obj(p):return {'type':'object','properties':p,'required':list(p),'additionalProperties':False}
    string={'type':'string'}
    return {'type':'array','items':obj({'entry_index':{'type':'integer'},'kind':{'type':'string','enum':['meaning','missing','source','other']},'prompt':string,'changes':{'type':'array','items':obj({'field_id':string,'value':string})}})}


def group_id(entry,index):
    from lab import category
    return f"{entry['category']}:{index if category(entry['category'])[2] else 0}"


def build_questions(state,p,previous=None):
    if not p.get('review_contract'):return
    fields={f['id']:f for f in state['fields'] if not f.get('entry_id') and not f.get('profile_archived') and f.get('widget')!='files'}
    entries=p.get('model_result',{}).get('entries',[]);result=[]
    def add(group,kind,prompt,changes=None):
        rows=[c for c in p['candidates'] if c['group']==group]
        entry=next((e for i,e in enumerate(entries) if group_id(e,i)==group),None)
        cat=rows[0]['category'] if rows else entry['category'] if entry else None
        changes=[{'field_id':v['field_id'],'label':fields[v['field_id']]['label'],'type':fields[v['field_id']]['type'],'value':v.get('value','')} for v in changes or [] if v.get('field_id') in fields and fields[v['field_id']]['category']==cat and (not fields[v['field_id']].get('record_types') or (entry or (rows[0] if rows else {})).get('record_type') in fields[v['field_id']]['record_types'])]
        item={'group':group,'title':(entry or {}).get('title','本次文件'),'kind':kind,'prompt':str(prompt)[:2000],'changes':changes}
        item['id']=hashlib.sha256(json.dumps(item,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
        if not any(q['id']==item['id'] for q in result):result.append(item)
    for q in p.get('model_result',{}).get('questions',[]):
        i=q.get('entry_index');entry=entries[i] if type(i)==int and 0<=i<len(entries) else None
        changes=q.get('changes',[])
        if entry and q.get('kind')=='missing' and not changes:
            prompt=q.get('prompt','');cat=entry['category']
            matched=[f['id'] for f in fields.values() if f['category']==cat and any(label and label in prompt for label in [f['label'],*f.get('aliases',[])])]
            if cat=='honors' and re.search('获奖(?:时间|日期)',prompt):matched.append('award_date')
            if cat=='language' and entry.get('record_type')=='exam' and re.search('考试(?:时间|日期)',prompt):matched.append('exam_date')
            if cat=='campus' and '起止' in prompt:matched.extend(['campus_started','campus_ended'])
            changes=[{'field_id':fid,'value':''} for fid in dict.fromkeys(matched)]
        add(group_id(entry,i) if entry else '',q.get('kind','other'),q.get('prompt','请核对'),changes)
    for i,e in enumerate(entries):
        g=group_id(e,i);rows=[c for c in p['candidates'] if c['group']==g];vals={c['field_id']:c['value'] for c in rows}
        datefield='award_date' if e['category']=='honors' else 'exam_date' if e['category']=='language' and e.get('record_type')=='exam' else None
        if datefield and not vals.get(datefield) and not any(q['group']==g and any(c['field_id']==datefield for c in q['changes']) for q in result):
            add(g,'missing','原文未明确'+fields[datefield]['label']+'；可补充，也可跳过并留空。',[{'field_id':datefield,'value':''}])
        if e['category']=='honors' and any(re.search(r'(?<!全)国二(?!等)',f.get('value','')) for f in e['fields'] if f.get('field_id') in {'award_name','award_prize'}) and not any(q['group']==g and q['kind']=='meaning' for q in result):
            add(g,'meaning','原文“国二”是否表示“国家级二等奖”？确认前保留原文，可修改解释或跳过。',[{'field_id':'award_level','value':'国家级'},{'field_id':'award_prize','value':'二等奖'}])
    for w in p.get('warnings',[]):
        if not any(q['prompt']==w for q in result):
            from document_review import needs_source
            add('','source' if needs_source({'warnings':[w]}) else 'other',w)
    basis=hashlib.sha256(json.dumps([(c['group'],c['field_id'],c['value'],c.get('source'),c.get('validation_issues')) for c in p['candidates']],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    unchanged=p.get('review_basis')==basis
    old=p.get('review_answers',{}) if unchanged else {}
    restore=p.get('review_completed') and unchanged and set(old)=={q['id'] for q in result}
    p['review_questions']=result
    p['review_answers']={q['id']:old[q['id']] for q in result if q['id'] in old}
    p['review_completed']=bool(restore or not result)
    p['review_basis']=basis
    if restore:
        for old_row in previous or []:
            if old_row.get('source',{}).get('kind')!='user_confirmation':continue
            row=next((c for c in p['candidates'] if c['group']==old_row['group'] and c['field_id']==old_row['field_id']),None)
            if row is None:p['candidates'].append(copy.deepcopy(old_row))
            else:
                for key in ('value','source','source_before_review','validation_issues'):row[key]=copy.deepcopy(old_row.get(key))
            p.get('comparison_hints',{}).pop(old_row['group'],None)
    sync_source_issues(p)


def complete(lab,data):
    from lab import find,LabError,validate_value,uid
    request=data.get('answers',[])
    if not isinstance(request,list):raise LabError('确认表单格式无效')
    digest=hashlib.sha256(json.dumps(request,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    def apply(state):
        p=find(state['imports'],data['import_id'])
        if p.get('review_completed') and p.get('review_submission')==digest:return {'completed':True,'replayed':True}
        if not p.get('review_contract') or p.get('status') in {'识别中','待识别'}:raise LabError('识别尚未生成确认表单',409)
        if data.get('revision')!=p.get('revision',1):raise LabError('预览已变化，请重新打开确认表单',409)
        questions={q['id']:q for q in p.get('review_questions',[])}
        supplied={a.get('id'):a for a in request if isinstance(a,dict)}
        if len(supplied)!=len(request) or set(supplied)-set(questions):raise LabError('问题已变化或重复')
        answers={};changed=set()
        for qid,q in questions.items():
            if question_locked(p,q):
                old=p.get('review_answers',{}).get(qid,{'action':'skip','note':''})
                a=supplied.get(qid,old)
                canonical={'action':a.get('action','skip'),'note':a.get('note','')}
                if canonical['action']=='apply':canonical['values']=a.get('values',{})
                if canonical!=old:raise LabError('此问题涉及已保存资料，不能修改；其他未保存对象仍可确认',409)
                answers[qid]=copy.deepcopy(old);continue
            a=supplied.get(qid,{'action':'skip'});action=a.get('action','skip');note=a.get('note','')
            if action not in {'skip','original','apply','note','confirm'} or not isinstance(note,str) or len(note)>4000:raise LabError('请选择采用、保留原文、补充说明、核对确认或跳过')
            if action=='confirm' and q['kind']!='source':raise LabError('只有原件归属疑点可使用核对确认')
            answers[qid]={'action':action,'note':note}
            if action!='apply':continue
            if not q['changes']:raise LabError('此提示只能补充说明或跳过，不能自动改写字段')
            values=a.get('values',{})
            if not isinstance(values,dict) or set(values)-{c['field_id'] for c in q['changes']}:raise LabError('补充字段不属于此问题')
            answers[qid]['values']={}
            rows=[c for c in p['candidates'] if c['group']==q['group']]
            if not rows:raise LabError('此对象没有可用候选，请跳过并保留待核验',409)
            for change in q['changes']:
                fid=change['field_id'];definition=find(state['fields'],fid)
                if definition['category']!=rows[0]['category'] or definition.get('entry_id'):raise LabError('字段归属已变化',409)
                value=values.get(fid,change['value'])
                if not isinstance(value,str):raise LabError('补充值须为文本')
                if not value.strip():continue  # optional blank never clears previous data
                if definition['type'] in {'date','partial_date'}:
                    from recognizer import normalized_date
                    value=normalized_date(value)
                value=validate_value(definition,value)
                if (q['group'],fid) in changed:raise LabError('同一字段出现多次修改，请在一个问题中补充',409)
                changed.add((q['group'],fid));answers[qid]['values'][fid]=value
                c=next((c for c in rows if c['field_id']==fid),None)
                if c is None:
                    c=copy.deepcopy(rows[0]);c.update(id=uid('candidate'),field_id=fid,label=definition['label'],type=definition['type'],definition=copy.deepcopy(definition),existing='',saved=False,disposition=None);c['source']={'filename':p['filename'],'location':'本次对象原文（用户补充前）','quote':rows[0].get('object_source','')}
                    c.pop('source_before_review',None)
                    p['candidates'].append(c);rows.append(c)
                c.setdefault('source_before_review',copy.deepcopy(c.get('source',{})))
                c['value']=value;c['source']={'kind':'user_confirmation','filename':p['filename'],'question_id':qid,'quote':value,'note':note,'original_source':c['source_before_review']}
                # A human-confirmed field can resolve only its own field-level rejection.
                for row in rows:row['validation_issues']=[x for x in row.get('validation_issues',[]) if not x.startswith(definition['label'])]
            # Changed facts invalidate prior semantic comparisons, but not user identity decisions.
            p.get('comparison_hints',{}).pop(q['group'],None)
        p.update(review_answers=answers,review_completed=True,review_submission=digest,stage="完成识别确认",revision=p.get('revision',1)+1)
        sync_source_issues(p)
        return {'completed':True,'updated_fields':len(changed),'skipped':sum(a['action']=='skip' for a in answers.values())}
    return lab.mutate(apply)
