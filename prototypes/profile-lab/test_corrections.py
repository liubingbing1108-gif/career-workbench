import copy
import tempfile
import unittest
from lab import Lab,LabError,find
from application import Application
from preparation import Preparation
from executor_bridge import ExecutorBridge
from profile_library import ProfileLibrary,token
from profile_migration import prepare,state_hash
from corrections import preview,start


class CorrectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(self.tmp.name)
        self.lab.mutate(lambda s:s.update(prepare(s,1000)[0]))
        self.sid=self.lab.new_session()['id'];self.url='https://fictional.example/apply';self.origin='chrome-extension://'+'a'*32
        state=self.lab.state();basic=next(e for e in state['entries'] if e['category']=='basic')
        ProfileLibrary(self.lab).save(dict(request_id='initial',entry_id=basic['id'],edit_token=token(state,basic),values={'name':'确认姓名'}));self.eid=basic['id']
        self.app=Application(self.lab);self.prep=Preparation(self.lab,self.app)
        self.app.install_mapping(self.sid,dict(url=self.url,title='虚构岗位',fields=[dict(id='q',label='姓名')]),dict(mappings=[dict(website_id='q',status='mapped',category='basic',field_id='name',requirement=None)]))
        self.lab.mutate(lambda s:find(s['sessions'],self.sid).update(form_analysis=dict(url=self.url,sections=[])))
        self.prep.settings(self.sid,'')
        self.bridge=ExecutorBridge(self.lab)
        self.connection=self.bridge.call('connect',self.origin,dict(url=self.url,code=self.bridge.code,core_session_id='fiction-core',capabilities={'structuredIssues':1,'correctionRetry':1,'stopProof':1}))['connection']
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def call(self,action,**data):return self.bridge.call(action,self.origin,dict(connection=self.connection,url=self.url,**data))
    def failed_attempt(self):
        p=self.prep.preview(self.sid);job=self.prep.start(self.sid,p['digest']);self.call('poll')
        row=job['confirmed_materials']['rows'][0]
        issue=dict(website_id='q',source_ref=row['source_ref'],expected_value='确认姓名',field_id='native-name',label='姓名',section_id='basic',record_id='',snapshot_id='s1',observed_value='官网旧值',error_type='READBACK_MISMATCH',record_fields=[])
        self.call('report',job_id=job['id'],status='needs_attention',filled=0,verified=0,message='需修正',issues=['姓名未一致'],structured_issues=[issue])
        return find(self.lab.state()['sessions'],self.sid)['preparation']['execution']
    def test_correction_binds_attempt_old_value_new_digest_and_replays(self):
        old=self.failed_attempt();self.app.edit_answer(self.sid,'q','本次更正','session')
        p=preview(self.prep,self.sid,[old['structured_issues'][0]['id']]);self.assertEqual(p['corrections'][0]['expected_current'],'官网旧值');self.assertEqual(p['corrections'][0]['value'],'本次更正')
        job=start(self.prep,self.sid,p['digest']);self.assertEqual(job['id'],start(self.prep,self.sid,p['digest'])['id'])
        self.assertEqual(self.call('poll')['job']['materials']['corrections'],p['corrections'])
        stable=state_hash(self.lab.state())
        with self.assertRaises(LabError):self.call('report',job_id=old['id'],status='complete',filled=1,verified=1,message='迟到报告')
        self.assertEqual(stable,state_hash(self.lab.state()))
    def test_edits_after_correction_preview_require_new_confirmation(self):
        old=self.failed_attempt();p=preview(self.prep,self.sid,[old['structured_issues'][0]['id']]);self.app.edit_answer(self.sid,'q','后来编辑','session')
        with self.assertRaises(LabError):start(self.prep,self.sid,p['digest'])
        self.assertEqual(find(self.lab.state()['sessions'],self.sid)['preparation']['execution']['id'],old['id'])
    def test_new_batch_cannot_replace_running_batch_and_unknown_report_rejected(self):
        p=self.prep.preview(self.sid);job=self.prep.start(self.sid,p['digest']);self.call('poll')
        self.app.edit_answer(self.sid,'q','新草稿','session');fresh=self.prep.preview(self.sid)
        with self.assertRaises(LabError):self.prep.start(self.sid,fresh['digest'])
        with self.assertRaises(LabError):self.call('report',job_id=job['id'],status='needs_attention',filled=0,verified=0,message='bad',structured_issues=[dict(website_id='other')])
    def test_unacknowledged_disconnect_blocks_correction(self):
        old=self.failed_attempt();self.lab.mutate(lambda s:find(s['sessions'],self.sid)['preparation']['execution'].update(stop_unconfirmed=True))
        with self.assertRaises(LabError):preview(self.prep,self.sid,[old['structured_issues'][0]['id']])

    def reconnect(self,core_id='fiction-core'):
        code=self.bridge.setup(self.sid)['code']
        self.connection=self.bridge.call('connect',self.origin,dict(url=self.url,code=code,core_session_id=core_id,capabilities={'structuredIssues':1,'correctionRetry':1,'stopProof':1}))['connection']

    def test_disconnect_reconnect_requires_same_core_idle_cancel_and_fresh_preview(self):
        old=self.failed_attempt();p=preview(self.prep,self.sid,[old['structured_issues'][0]['id']]);self.prep.preview(self.sid)
        self.lab.mutate(lambda s:find(s['sessions'],self.sid)['preparation']['execution'].update(stop_unconfirmed=True))
        self.reconnect()
        check=self.call('stop-check')['stop_check'];self.assertEqual(check['core_session_id'],'fiction-core')
        self.assertEqual(self.call('poll'),dict(job=None,stop_check=check))
        proof=dict(sessionId='fiction-core',page={'url':self.url},busy=False,cancelled=True)
        for change in ({'busy':True},{'cancelled':False},{'sessionId':'new-page'},{'page':{'url':self.url+'?other=1'}}):
            with self.assertRaises(LabError):self.call('stop-proof',job_id=old['id'],proof={**proof,**change})
        with self.assertRaises(LabError):self.prep.verify(self.sid)
        with self.assertRaises(LabError):self.call('stop-proof',job_id='stale-attempt',proof=proof)
        self.assertTrue(self.call('stop-proof',job_id=old['id'],proof=proof)['accepted'])
        prep=find(self.lab.state()['sessions'],self.sid)['preparation']
        self.assertNotIn('preview',prep);self.assertNotIn('correction_preview',prep)
        self.assertEqual(prep['execution']['status'],'paused');self.assertFalse(prep['execution']['stop_unconfirmed'])
        with self.assertRaises(LabError):start(self.prep,self.sid,p['digest'])
        fresh=preview(self.prep,self.sid,[old['structured_issues'][0]['id']]);self.assertEqual(start(self.prep,self.sid,fresh['digest'])['status'],'awaiting_executor')

    def test_another_core_or_legacy_unknown_core_cannot_prove_stop(self):
        old=self.failed_attempt();self.lab.mutate(lambda s:find(s['sessions'],self.sid)['preparation']['execution'].update(stop_unconfirmed=True))
        proof=dict(sessionId='fiction-core',page={'url':self.url},busy=False,cancelled=True)
        self.reconnect('different-core')
        with self.assertRaises(LabError):self.call('stop-proof',job_id=old['id'],proof=proof)
        self.reconnect();self.lab.mutate(lambda s:find(s['sessions'],self.sid)['preparation']['execution'].pop('executor_core_session_id'))
        with self.assertRaises(LabError):self.call('stop-proof',job_id=old['id'],proof=proof)

    def test_restart_only_requires_stop_proof_for_dispatched_job(self):
        p=self.prep.preview(self.sid);self.prep.start(self.sid,p['digest'])
        self.bridge=ExecutorBridge(self.lab)
        self.assertFalse(find(self.lab.state()['sessions'],self.sid)['preparation']['execution']['stop_unconfirmed'])
        self.reconnect();p=self.prep.preview(self.sid);self.prep.start(self.sid,p['digest']);self.call('poll')
        self.bridge=ExecutorBridge(self.lab);self.reconnect()
        self.assertEqual(self.call('stop-check')['stop_check']['core_session_id'],'fiction-core')

    def test_stop_check_does_not_take_pending_job_or_expose_answers(self):
        p=self.prep.preview(self.sid);self.prep.start(self.sid,p['digest'])
        self.assertEqual(self.call('stop-check'),{'stop_check':None})
        self.assertEqual(find(self.lab.state()['sessions'],self.sid)['preparation']['execution']['status'],'awaiting_executor')

    def test_unconfirmed_other_session_blocks_same_url_new_batch(self):
        old=self.failed_attempt();original=find(self.lab.state()['sessions'],self.sid)
        other=copy.deepcopy(original);other['id']='other-session';other['preparation']['execution']['stop_unconfirmed']=True
        self.lab.mutate(lambda s:s['sessions'].append(other))
        p=self.prep.preview(self.sid)
        with self.assertRaises(LabError):self.prep.start(self.sid,p['digest'])
        p=preview(self.prep,self.sid,[old['structured_issues'][0]['id']])
        with self.assertRaises(LabError):start(self.prep,self.sid,p['digest'])

if __name__=='__main__':unittest.main()
