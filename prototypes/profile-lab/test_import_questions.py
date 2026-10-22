import copy,tempfile,unittest
from lab import Lab,LabError,find
from import_questions import complete
from resume_skill import CONTRACT
from test_recognizer import field

TEXT='虚构创新赛 国二'
RESULT={'parser_contract':CONTRACT,'entries':[{'category':'honors','record_type':'','title':'虚构创新赛','source_range':{'block':0,'start_line':1,'end_line':1},'description_range':{'block':0,'start_line':0,'end_line':0},'fields':[field('award_name','奖项名称','虚构创新赛'),field('award_prize','获奖等次','国二')]}],'warnings':['示例提示：同名奖项尚需核对。'],'questions':[]}
class Engine:
 name='offline review fixture'
 def status(self):return {'available':True}
 def extract(self,fields,blocks):return copy.deepcopy(RESULT),{'parser_contract':CONTRACT,'review_contract':'resume-review/v1'}
 def call(self,prompt,schema):return {'matches':[]},{}

class QuestionTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name,Engine());self.p=self.lab.upload('fiction.txt',TEXT.encode());self.baseline=copy.deepcopy(self.lab.state()['entries'])
 def tearDown(self):self.lab.db.close();self.tmp.cleanup()
 def current(self):return find(self.lab.state()['imports'],self.p['id'])
 def submit(self,answers):
  p=self.current();return complete(self.lab,{'import_id':p['id'],'revision':p['revision'],'answers':answers})
 def test_all_warnings_in_optional_form(self):
  p=self.current();self.assertEqual(len(p['review_questions']),3);self.assertFalse(p['review_completed']);self.assertEqual(self.lab.state()['entries'],self.baseline)
  with self.assertRaisesRegex(LabError,'确认表单'):self.lab.resolve_import([{'candidate_id':c['id'],'mode':'replace'} for c in p['candidates']],{p['id']:p['revision']})
 def test_skip_all_finishes_without_fabrication(self):
  self.submit([]);p=self.current();self.assertTrue(p['review_completed']);self.assertFalse(any(c['field_id']=='award_date' for c in p['candidates']));self.assertEqual(next(c['value'] for c in p['candidates'] if c['field_id']=='award_prize'),'国二');self.assertEqual(self.lab.state()['entries'],self.baseline)
  self.lab.resolve_import([{'candidate_id':c['id'],'mode':'replace'} for c in p['candidates']],{p['id']:p['revision']});self.assertEqual(len([e for e in self.lab.state()['entries'] if e['category']=='honors']),1)
 def test_confirm_meaning_and_optional_date_only_changes_candidates(self):
  p=self.current();meaning=next(q for q in p['review_questions'] if q['kind']=='meaning');missing=next(q for q in p['review_questions'] if q['kind']=='missing')
  self.submit([{'id':meaning['id'],'action':'apply','values':{'award_level':'国家级','award_prize':'二等奖'}},{'id':missing['id'],'action':'apply','values':{'award_date':'2024'}}]);p=self.current();values={c['field_id']:c['value'] for c in p['candidates']};self.assertEqual(values['award_prize'],'二等奖');self.assertEqual(values['award_date'],'2024');self.assertEqual(self.lab.state()['entries'],self.baseline)
  self.assertEqual(next(c for c in p['candidates'] if c['field_id']=='award_prize')['source']['kind'],'user_confirmation')
  self.lab.resolve_import([{'candidate_id':c['id'],'mode':'replace'} for c in p['candidates']],{p['id']:p['revision']});self.lab.db.close();self.lab=Lab(self.tmp.name);e=next(e for e in self.lab.state()['entries'] if e['category']=='honors');self.assertEqual(e['values']['award_level'],'国家级');self.assertEqual(e['values']['award_prize'],'二等奖')
 def test_notes_do_not_become_field_facts(self):
  q=self.current()['review_questions'][0];self.submit([{'id':q['id'],'action':'note','note':'日期以后补充'}]);self.assertEqual(self.current()['review_answers'][q['id']]['note'],'日期以后补充');self.assertFalse(any(c['field_id']=='award_date' for c in self.current()['candidates']))
 def test_stale_and_foreign_field_edits_are_atomic(self):
  p=self.current();q=next(q for q in p['review_questions'] if q['kind']=='meaning');before=self.lab.state()
  with self.assertRaises(LabError):complete(self.lab,{'import_id':p['id'],'revision':-1,'answers':[]})
  with self.assertRaises(LabError):self.submit([{'id':q['id'],'action':'apply','values':{'phone':'111'}}])
  self.assertEqual(self.lab.state(),before)
 def test_same_submission_idempotent_and_blank_never_clears(self):
  q=next(q for q in self.current()['review_questions'] if q['kind']=='meaning');answers=[{'id':q['id'],'action':'apply','values':{'award_prize':'','award_level':''}}];self.submit(answers);before=self.lab.state();self.assertTrue(self.submit(answers)['replayed']);self.assertEqual(self.lab.state(),before);self.assertEqual(next(c['value'] for c in self.current()['candidates'] if c['field_id']=='award_prize'),'国二')

 def test_revalidation_preserves_unchanged_user_choices_and_provenance(self):
  q=next(q for q in self.current()['review_questions'] if q['kind']=='meaning');self.submit([{'id':q['id'],'action':'apply','values':{'award_level':'国家级','award_prize':'二等奖'}}]);self.lab.revalidate_import(self.p['id']);p=self.current();self.assertTrue(p['review_completed']);self.assertEqual(next(c['value'] for c in p['candidates'] if c['field_id']=='award_prize'),'二等奖');self.assertEqual(next(c['source']['kind'] for c in p['candidates'] if c['field_id']=='award_level'),'user_confirmation')

 def test_missing_date_model_question_is_one_editable_question(self):
  from import_questions import build_questions
  p=self.current();p['model_result']['questions']=[{'entry_index':0,'kind':'missing','prompt':'未提供获奖时间，可补充或跳过。','changes':[]}];build_questions(self.lab.state(),p)
  dates=[q for q in p['review_questions'] if any(c['field_id']=='award_date' for c in q['changes'])];self.assertEqual(len(dates),1)
 def test_full_national_second_prize_is_not_abbreviation_question(self):
  from import_questions import build_questions
  p=self.current();p['model_result']['entries'][0]['fields'][1]['value']='全国二等奖';build_questions(self.lab.state(),p);self.assertFalse(any(q['kind']=='meaning' for q in p['review_questions']))


class SourceEngine(Engine):
 def extract(self,fields,blocks):
  r=copy.deepcopy(RESULT)
  r['questions']=[{'entry_index':0,'kind':'source','prompt':'奖项与这一段的归属仍不清楚，请核对原件。','changes':[]}]
  second=copy.deepcopy(r['entries'][0]);second.update(title='另一次校级奖',source_range={'block':0,'start_line':2,'end_line':2},fields=[field('award_name','奖项名称','另一次校级奖')]);r['entries'].append(second)
  return r,{'parser_contract':CONTRACT,'review_contract':'resume-review/v1'}

class SourceQuestionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name,SourceEngine());self.p=self.lab.upload('source-doubt.txt',(TEXT+'\n另一次校级奖').encode())
 def tearDown(self):self.lab.db.close();self.tmp.cleanup()
 def current(self):return find(self.lab.state()['imports'],self.p['id'])
 def submit(self,answers):
  p=self.current();return complete(self.lab,{'import_id':p['id'],'revision':p['revision'],'answers':answers})
 def save(self,group):
  p=self.current();return self.lab.resolve_import([{'candidate_id':c['id'],'mode':'replace'} for c in p['candidates'] if c['group']==group],{p['id']:p['revision']})
 def test_skip_doubt_blocks_only_affected_group_then_human_can_confirm(self):
  self.submit([]);p=self.current();q=next(q for q in p['review_questions'] if q['kind']=='source')
  before=self.lab.state()
  with self.assertRaisesRegex(LabError,'尚未核验'):self.save('honors:0')
  self.assertEqual(before,self.lab.state());self.save('honors:1');saved=copy.deepcopy(self.lab.state()['entries'])
  self.submit([{'id':q['id'],'action':'confirm','note':'已查看原件，此项归属正确'}]);self.assertEqual(saved,self.lab.state()['entries'])
  self.save('honors:0');self.assertEqual(len(self.lab.state()['entries']),len(saved)+1)
 def test_original_and_note_are_not_confirmation(self):
  q=next(q for q in self.current()['review_questions'] if q['kind']=='source')
  for action in ['original','note']:
   self.submit([{'id':q['id'],'action':action,'note':'稍后核对'}])
   with self.assertRaises(LabError):self.save('honors:0')
 def test_saved_question_tampering_rejected_atomically(self):
  self.submit([]);self.save('honors:1');p=self.current();q=next(q for q in p['review_questions'] if q['group']=='honors:1');before=self.lab.state()
  with self.assertRaisesRegex(LabError,'已保存'):self.submit([{'id':q['id'],'action':'note','note':'修改已保存对象的问题'}])
  self.assertEqual(before,self.lab.state())
 def test_source_confirmation_does_not_clear_grounding_rejection(self):
  q=next(q for q in self.current()['review_questions'] if q['kind']=='source')
  def reject(s):
   for c in find(s['imports'],self.p['id'])['candidates']:
    if c['group']=='honors:0':c['validation_issues'].append('对象原文引用范围无效')
  self.lab.mutate(reject);self.submit([{'id':q['id'],'action':'confirm'}])
  with self.assertRaisesRegex(LabError,'尚未核验'):self.save('honors:0')
 def test_revalidation_retains_source_answer_and_no_false_unblock(self):
  q=next(q for q in self.current()['review_questions'] if q['kind']=='source')
  self.submit([]);self.lab.revalidate_import(self.p['id'])
  with self.assertRaises(LabError):self.save('honors:0')
  self.submit([{'id':q['id'],'action':'confirm'}]);self.lab.revalidate_import(self.p['id']);self.assertTrue(self.current()['review_completed']);self.save('honors:0')

 def test_warning_only_source_doubt_cannot_bypass_confirmation(self):
  from import_questions import build_questions
  def warn(s):
   p=find(s['imports'],self.p['id']);p['model_result']['questions']=[];p['warnings']=['日期与经历分离，暂不绑定。'];build_questions(s,p)
  self.lab.mutate(warn);p=self.current();self.assertTrue(any(q['kind']=='source' and not q['group'] for q in p['review_questions']))
  self.submit([])
  with self.assertRaises(LabError):self.save('honors:1')
