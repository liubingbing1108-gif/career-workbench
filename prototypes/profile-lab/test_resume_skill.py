"""Regression cases for source/object binding and complete import representations."""
import copy,json,tempfile,unittest
from pathlib import Path
from lab import Lab,LabError,find
from recognizer import grounded_candidates,CodexRecognizer
from resume_skill import CONTRACT,rules
from resume_import import representations,comparison_token
from profile_library import ProfileLibrary
from test_recognizer import field


def award(name='校奖学金一等奖',date='2024',extra=''):
    text=name+' '+date+('\n'+extra if extra else '')
    fields=[field('award_name','奖项名称',name),field('award_date','获奖时间',date)]
    if extra:fields.append(field('award_details','完整获奖说明',extra,kind='multiline'))
    return text,{'parser_contract':CONTRACT,'entries':[{'category':'honors','record_type':'','title':name,'source_range':{'block':0,'start_line':1,'end_line':len(text.splitlines())},'description_range':{'block':0,'start_line':0,'end_line':0},'fields':fields}],'warnings':[]}


class Stub:
    name='Skill test'
    def __init__(self,results):self.results=iter(results);self.calls=0;self.target=None
    def status(self):return {'available':True,'engine':self.name}
    def extract(self,fields,blocks):return copy.deepcopy(next(self.results)),{'parser_contract':CONTRACT}
    def call(self,prompt,schema):
        self.calls+=1
        data=json.loads(prompt.split('\n',1)[1]);matches=[]
        for o in data['incoming']:
            for t in data['existing']:
                if o['category']==t['category']:
                    matches.append({'group':o['group'],'target_id':t['id'],'relation':'same','reason':'虚构同次奖项','conflict_fields':[]})
        return {'matches':matches},{}


class SkillTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name)
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def upload(self,data):
        text,result=data;self.lab.recognizer=Stub([result]);return self.lab.upload('example.txt',text.encode())
    def choose(self,p,mode='replace',**extra):
        p=find(self.lab.state()['imports'],p['id'])
        return self.lab.resolve_import([dict(candidate_id=c['id'],mode=mode,**extra) for c in p['candidates']],{p['id']:p['revision']})
    def link(self,p,eid):
        p=find(self.lab.state()['imports'],p['id']);ProfileLibrary(self.lab).import_identity({'import_id':p['id'],'group':p['candidates'][0]['group'],'entry_id':eid,'revision':p['revision']})
    def test_prompt_loads_skill_catalog_scope(self):
        r=CodexRecognizer();r.cli=__file__;captured=[]
        r.call=lambda p,s:(captured.append((p,s)) or {'entries':[],'warnings':[]},{})
        output,usage=r.extract(self.lab.state()['fields'],[{'text':'示例','location':'原文'}])
        self.assertIn('同一信息的不同表述',captured[0][0]);self.assertIn('record_types',captured[0][0]);self.assertEqual(usage['skill_sha256'],rules()[1]);self.assertEqual(output['parser_contract'],CONTRACT)
    def test_cross_object_date_and_wrong_field_type_rejected(self):
        text='甲公司 2024.01\n乙公司 2025.01'
        result={'parser_contract':CONTRACT,'entries':[{'category':'employment','record_type':'','source_range':{'block':0,'start_line':1,'end_line':1},'description_range':{'block':0,'start_line':0,'end_line':0},'fields':[field('company','公司','甲公司'),field('started','开始日期','2025-01','甲公司 2024.01',kind='partial_date'),field('school','学校','甲公司')]}]}
        candidates,rejected=grounded_candidates(self.lab.state(),[{'text':text,'location':'原文'}],'example.txt',result)
        self.assertEqual([c['field_id'] for c in candidates],['company']);self.assertTrue(candidates[0]['validation_issues']);self.assertTrue(rejected)
    def test_complete_description_cannot_drop_last_sentence(self):
        text='甲公司\n访谈12人。\n整理10项问题。'
        result={'parser_contract':CONTRACT,'entries':[{'category':'employment','record_type':'','source_range':{'block':0,'start_line':1,'end_line':3},'description_range':{'block':0,'start_line':2,'end_line':3},'fields':[field('company','公司','甲公司'),field('description','经历描述','访谈12人。',kind='versioned_text')]}]}
        c,r=grounded_candidates(self.lab.state(),[{'text':text,'location':'原文'}],'example.txt',result)
        self.assertEqual([x['field_id'] for x in c],['company']);self.assertTrue(r)
    def test_language_subtype_cannot_mix_exam_score_into_ability(self):
        result={'parser_contract':CONTRACT,'entries':[{'category':'language','record_type':'ability','source_range':{'block':0,'start_line':1,'end_line':1},'description_range':{'block':0,'start_line':0,'end_line':0},'fields':[field('language_name','语种','英语'),field('language_score','总分','560')]}]}
        c,r=grounded_candidates(self.lab.state(),[{'text':'英语 560','location':'原文'}],'example.txt',result)
        self.assertEqual([x['field_id'] for x in c],['language_name']);self.assertTrue(r)
    def test_section_heading_and_explicit_ongoing_are_scoped_evidence(self):
        text='实习经历\n甲公司 2024.01-至今'
        result={'parser_contract':CONTRACT,'entries':[{'category':'employment','record_type':'','source_range':{'block':0,'start_line':2,'end_line':2},'description_range':{'block':0,'start_line':0,'end_line':0},'fields':[field('company','公司','甲公司'),field('employment_type','经历性质','实习','甲公司'),field('still_employed','是否仍在职','是','至今')]}]}
        c,r=grounded_candidates(self.lab.state(),[{'text':text,'location':'原文'}],'example.txt',result)
        self.assertFalse(r);self.assertEqual(len(c),4);self.assertEqual(c[-1]['value'],'至今');self.assertIn('实习经历',c[1]['source']['quote'])
        result['entries'][0]['fields'].append(field('education_full_time','是否全日制','是','至今'))
        c,r=grounded_candidates(self.lab.state(),[{'text':text,'location':'原文'}],'example.txt',result)
        self.assertTrue(r)
    def test_new_field_alias_maps_to_existing_same_object_field(self):
        text='项目甲 本人角色：负责人'
        result={'parser_contract':CONTRACT,'entries':[{'category':'projects','record_type':'','source_range':{'block':0,'start_line':1,'end_line':1},'description_range':{'block':0,'start_line':0,'end_line':0},'fields':[field('new_project_role','本人角色','负责人')]}]}
        c,r=grounded_candidates(self.lab.state(),[{'text':text,'location':'原文'}],'example.txt',result)
        self.assertFalse(r);self.assertEqual(c[0]['field_id'],'project_role')
    def test_only_rejected_objects_are_sent_to_repair(self):
        from resume_skill import repair
        text,result=award();result['entries'].append({'category':'language','record_type':'exam','title':'六级','source_range':{'block':0,'start_line':2,'end_line':2},'description_range':{'block':0,'start_line':0,'end_line':0},'fields':[field('exam_name','考试名称','英语六级','英语（六级576分）')]})
        blocks=[{'text':text+'\n英语（六级576分）','location':'原文'}];captured=[]
        class RepairStub:
            def call(self,prompt,schema):
                captured.append(prompt);e=copy.deepcopy(result['entries'][1]);e['fields'][0]['value']='六级'
                return {'repairs':[{'index':1,'entry':e}]},{}
        fixed,info=repair(RepairStub(),self.lab.state()['fields'],blocks,result,[])
        payload=json.loads(captured[0].split('\n',1)[1]);self.assertEqual([i['index'] for i in payload['objects']],[1]);self.assertEqual(fixed['entries'][0],result['entries'][0]);self.assertEqual(fixed['entries'][1]['fields'][0]['value'],'六级')
    def test_both_stays_one_record_with_two_complete_versions(self):
        p=self.upload(award());self.choose(p);e=next(e for e in self.lab.state()['entries'] if e['category']=='honors')
        q=self.upload(award('示例大学校级奖学金一等奖',extra='经学校评定。'));self.assertTrue(q['candidates'][0]['identity_review']);self.link(q,e['id'])
        before=copy.deepcopy(e);result=self.choose(q,'new');state=self.lab.state();e=find(state['entries'],e['id'])
        variants=representations(state,e);self.assertEqual(len(variants),2);self.assertEqual(len([e for e in state['entries'] if e['category']=='honors']),1)
        self.assertEqual(e['values']['award_name'],before['values']['award_name']);self.assertEqual(variants[1]['values']['award_date'],'2024');self.assertEqual(variants[1]['values']['award_details'],'经学校评定。')
        self.assertTrue(ProfileLibrary(self.lab).view()['records'][next(i for i,x in enumerate(ProfileLibrary(self.lab).view()['records']) if x['id']==e['id'])]['versions_enabled'])
        self.assertEqual(self.choose(q,'new')['saved'],0)
        repeat=self.upload(award('示例大学校级奖学金一等奖',extra='经学校评定。'));self.link(repeat,e['id']);self.assertTrue(all(c['status']=='一致' for c in find(self.lab.state()['imports'],repeat['id'])['candidates']))
    def test_keep_incoming_keeps_source_and_only_one_active_version(self):
        p=self.upload(award());self.choose(p);e=next(e for e in self.lab.state()['entries'] if e['category']=='honors')
        q=self.upload(award('示例大学校级奖学金一等奖'));self.link(q,e['id']);self.choose(q,'replace');state=self.lab.state()
        self.assertEqual(len(representations(state,find(state['entries'],e['id']))),1);self.assertEqual(len(state['files']),2)
    def test_ignore_is_local_even_after_retry_and_global_legacy_fingerprint(self):
        p=self.upload(award());self.choose(p,'ignore');self.lab.revalidate_import(p['id']);p=find(self.lab.state()['imports'],p['id']);self.assertTrue(all(c['status']=='已忽略' for c in p['candidates']))
        q=self.upload(award());self.assertTrue(all(c['status']=='新增' for c in q['candidates']))
    def test_fact_conflict_requires_explicit_choice_and_is_atomic(self):
        p=self.upload(award());self.choose(p);e=next(e for e in self.lab.state()['entries'] if e['category']=='honors')
        q=self.upload(award(date='2025'));self.link(q,e['id']);before=self.lab.state()
        for mode in ['new','replace']:
            with self.assertRaises(LabError):self.choose(q,mode)
            self.assertEqual(self.lab.state(),before)
        self.choose(q,'replace',confirm_facts=True);self.assertEqual(find(self.lab.state()['entries'],e['id'])['values']['award_date'],'2025')
    def test_partial_group_and_stale_revision_rejected(self):
        p=self.upload(award());before=self.lab.state()
        with self.assertRaises(LabError):self.lab.resolve_import([{'candidate_id':p['candidates'][0]['id'],'mode':'replace'}],{p['id']:p['revision']})
        self.assertEqual(self.lab.state(),before)
        with self.assertRaises(LabError):self.lab.resolve_import([{'candidate_id':c['id'],'mode':'replace'} for c in p['candidates']],{p['id']:0})
    def test_comparison_failure_keeps_extraction_and_requires_identity_review(self):
        from recognizer import RecognitionError
        p=self.upload(award());self.choose(p)
        text,result=award('大学校级奖学金一等奖')
        class Offline(Stub):
            def call(self,prompt,schema):raise RecognitionError('连接失败','connection_failed')
        self.lab.recognizer=Offline([result]);q=self.lab.upload('other.txt',text.encode())
        self.assertEqual(q['status'],'完成');self.assertTrue(q['comparison_failed']);self.assertTrue(q['candidates'][0]['identity_review'])
        with self.assertRaises(LabError):self.choose(q)
    def test_changed_target_does_not_silently_turn_alias_into_new_record(self):
        from lab import put_answer
        p=self.upload(award());self.choose(p);e=next(e for e in self.lab.state()['entries'] if e['category']=='honors')
        q=self.upload(award('大学校级奖学金一等奖'))
        def change(s):
            target=find(s['entries'],e['id']);put_answer(s,target,find(s['fields'],'award_date'),'2023',mode='replace')
        self.lab.mutate(change);q=find(self.lab.state()['imports'],q['id']);self.assertTrue(q['candidates'][0]['identity_review']);self.assertIn(e['id'],q['candidates'][0]['identity_choices'])
    def test_pending_aliases_link_to_one_object(self):
        p=self.upload(award());q=self.upload(award('示例大学校级奖学金一等奖'))
        pending='pending:'+p['id']+'/'+p['candidates'][0]['group'];self.link(q,pending);self.choose(p);self.choose(q,'new')
        state=self.lab.state();es=[e for e in state['entries'] if e['category']=='honors'];self.assertEqual(len(es),1);self.assertEqual(len(representations(state,es[0])),2)

if __name__=='__main__':unittest.main()
