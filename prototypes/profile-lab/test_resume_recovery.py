import copy
import tempfile
import threading
import unittest
from lab import Lab, LabError, find
from preparation import Preparation
from application import Application
from official_draft import save_official_draft, restore_content
from test_recognizer import sample
import test_preparation


class RecoveryTests(unittest.TestCase):
    setUp = test_preparation.PreparationTests.setUp
    tearDown = test_preparation.PreparationTests.tearDown
    complete = test_preparation.PreparationTests.complete

    def test_edit_drafts_survive_reload_are_isolated_and_never_change_facts(self):
        self.complete();before=copy.deepcopy(self.lab.state()['entries'])
        key=self.sid+'/edu/object/school'
        row=self.prep.draft(self.sid,key,'尚未确认的文字')
        self.assertEqual(row['revision'],1)
        other=self.prep.open_target('https://example.com/other')['id']
        self.assertFalse(self.prep.view(other)['drafts'])
        with self.assertRaises(LabError):self.prep.draft(other,key,'串岗')
        with self.assertRaises(LabError):self.prep.draft(self.sid,key,'旧页面覆盖',0)
        preview=self.prep.preview(self.sid)
        with self.assertRaises(LabError):self.prep.start(self.sid,preview['digest'])
        reopened=Lab(self.temp.name)
        try:self.assertEqual(Preparation(reopened,Application(reopened)).view(self.sid)['drafts'][key]['value'],'尚未确认的文字')
        finally:reopened.db.close()
        self.prep.draft(self.sid,key,None,1)
        self.assertFalse(self.prep.current(self.sid)['pending'])
        self.assertEqual(self.lab.state()['entries'],before)

    def test_optional_existing_facts_included_and_missing_requires_deliberate_decision(self):
        self.complete()
        manifest=copy.deepcopy(self.manifest);maps=copy.deepcopy(self.maps)
        manifest['fields'][0]['children'].append(dict(id='major',label='专业',required=False))
        maps['mappings'][0]['members'].append(dict(website_id='major',field_id='major'))
        self.app.install_mapping(self.sid,manifest,maps)
        item=next(i for i in self.app.plan(self.sid)['missing'] if i.get('child_id')=='major')
        self.assertFalse(item['blocking'])
        key=self.prep.missing_key(item)
        self.assertTrue(any(t['key']==key for t in self.prep.current(self.sid)['tasks']))
        self.prep.omit_optional(self.sid,key,True)
        self.assertFalse(any(t['key']==key for t in self.prep.current(self.sid)['tasks']))
        self.lab.save_profile([dict(entry_id=self.edu['id'],field_id='major',value='虚构专业')])
        content=self.prep.current(self.sid)
        self.assertEqual(content['rows'][0]['records'][0]['values'][-1]['value'],'虚构专业')
        self.assertFalse(any(i.get('child_id')=='major' for i in self.app.plan(self.sid)['missing']))

    def test_official_recovery_is_local_preserves_before_reload_and_checks_digest(self):
        self.complete();url=self.manifest['url']
        def field(value):return dict(fieldId='name',label='姓名',kind='text',currentValue=value,section='个人信息',sectionId='basic',record=-1)
        result=save_official_draft(self.lab,self.sid,url,dict(initial=True,fields=[field('虚构姓名'),{**field('秘密'),'label':'密码'}]))
        self.assertTrue(result['local_only']);self.assertEqual(result['count'],1)
        save_official_draft(self.lab,self.sid,url,dict(initial=True,fields=[field('')]))
        self.assertEqual(restore_content(self.lab,self.sid)['rows'][0]['value'],'虚构姓名')
        preview=self.prep.preview(self.sid,True)
        save_official_draft(self.lab,self.sid,url,dict(fields=[field('新虚构姓名')]))
        with self.assertRaises(LabError):self.prep.start(self.sid,preview['digest'],True)
        preview=self.prep.preview(self.sid,True);job=self.prep.start(self.sid,preview['digest'],True)
        self.assertFalse(job['saved']);self.assertEqual(job['filled'],0)
        self.assertTrue(job['confirmed_materials']['preserve_unsaved_page'])
        with self.assertRaises(LabError):save_official_draft(self.lab,self.sid,'https://example.com/wrong',dict(fields=[field('bad')]))
        save_official_draft(self.lab,self.sid,url,dict(fields=[{**field('虚构大学'),'fieldId':'school','label':'学校','kind':'autocomplete'},
            {**field(''),'fieldId':'skills','label':'技能','kind':'multiselect','currentValue':['虚构技能甲','虚构技能乙']}]))
        recovered=restore_content(self.lab,self.sid)
        self.assertEqual(recovered['rows'][-1]['value'],['虚构技能甲','虚构技能乙'])
        self.assertEqual(recovered['rows'][-2]['value'],'虚构大学')


class ImportTaskTests(unittest.TestCase):
    def test_async_stages_source_preview_failure_retry_and_restart(self):
        started=threading.Event();release=threading.Event();text,result=sample()
        class Recognizer:
            name='离线受控识别'
            calls=0
            def extract(self,fields,blocks):
                self.calls+=1;started.set();release.wait(3)
                if self.calls==1:raise RuntimeError('虚构失败')
                return result,{}
        with tempfile.TemporaryDirectory() as directory:
            lab=Lab(directory,Recognizer())
            try:
                task=lab.upload('fiction.txt',text.encode(),asynchronous=True)
                self.assertTrue(started.wait(2));current=find(lab.state()['imports'],task['id'])
                self.assertEqual(current['stage'],'按资料组识别内容');self.assertIn('陈示例',current['text_preview'])
                lab.start_import(task['id']);self.assertEqual(lab.recognizer.calls,1)
                release.set();lab.import_workers[task['id']].join(3)
                self.assertEqual(find(lab.state()['imports'],task['id'])['status'],'失败')
                lab.start_import(task['id']);lab.import_workers[task['id']].join(3)
                current=find(lab.state()['imports'],task['id']);self.assertEqual(current['status'],'完成');self.assertTrue(current['candidates'])
                self.assertEqual([a['status'] for a in current['attempts']],['失败','完成'])
                self.assertEqual(lab.state()['entries'][0]['values'],{})
                lab.mutate(lambda s:find(s['imports'],task['id']).update(status='识别中'))
                other=Lab(directory)
                try:self.assertEqual(find(other.state()['imports'],task['id'])['status'],'已中断')
                finally:other.db.close()
            finally:
                release.set()
                for worker in lab.import_workers.values():worker.join(5)
                lab.db.close()
