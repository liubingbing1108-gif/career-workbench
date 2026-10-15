import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from lab import Lab,LabError
from application import Application
from preparation import Preparation
from executor_bridge import ExecutorBridge
from browser_launch import BrowserLaunch


class LaunchTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.lab=Lab(Path(self.tmp.name));self.prep=Preparation(self.lab,Application(self.lab));self.bridge=ExecutorBridge(self.lab)
        self.session=self.prep.open_target('https://example.com/apply','示例岗位');self.opened=[]
        self.launch=BrowserLaunch(self.lab,self.bridge,self.opened.append);self.origin='chrome-extension://'+'a'*32
    def tearDown(self):self.lab.db.close();self.tmp.cleanup()
    def ticket(self):
        self.launch.request(self.session['id'],'http://127.0.0.1:8768');return next(reversed(self.launch.tickets))
    def test_launch_opens_chrome_workbench_but_never_starts_unconfirmed_filling(self):
        ticket=self.ticket();self.assertIn('?launch='+ticket,self.opened[0])
        state=self.lab.state()['sessions'][0];self.assertNotIn('execution',state['preparation'])
        details=self.launch.claim(ticket,self.origin);self.assertEqual(details['session_id'],self.session['id'])
        self.assertEqual(details['url'],'https://example.com/apply')
        with self.assertRaises(LabError):self.launch.claim(ticket,self.origin)
    def test_retry_renews_connection_without_rescanning_confirmed_materials(self):
        self.lab.mutate(lambda s:s['sessions'][0]['preparation'].update(execution={'status':'failed','confirmed_materials':{'rows':[]}}))
        with patch.object(self.bridge,'status',return_value={'connected':True}):
            result=self.launch.request(self.session['id'],'http://127.0.0.1:8768',reconnect=True)
        details=self.launch.claim(result['ticket'],self.origin)
        self.assertTrue(details['resume_confirmed'])
        self.assertEqual(details['url'],'https://example.com/apply')
    def test_expired_or_untrusted_launch_cannot_disclose_connection(self):
        ticket=self.ticket()
        with self.assertRaises(LabError):self.launch.claim(ticket,'https://evil.example')
        self.launch.tickets[ticket]['created']-=301
        with self.assertRaises(LabError):self.launch.claim(ticket,self.origin)
    def test_busy_or_manual_preference_task_cannot_be_launched(self):
        for values in [{'manual_reason':'请到官网人工选择志愿'},{'preparation':{'execution':{'status':'running'}}}]:
            self.lab.mutate(lambda s:s['sessions'][0].update(values))
            with self.assertRaises(LabError):self.ticket()
        self.assertEqual(self.opened,[])
    def test_deleted_session_cannot_be_resurrected_by_old_launch(self):
        ticket=self.ticket();self.lab.mutate(lambda s:s.update(sessions=[]))
        with self.assertRaises(LabError):self.launch.claim(ticket,self.origin)
        self.assertEqual(self.lab.state()['sessions'],[])
    def test_two_pending_launches_keep_separate_single_use_connection_codes(self):
        a=self.ticket();other=self.prep.open_target('https://example.org/apply','示例乙')
        self.launch.request(other['id'],'http://127.0.0.1:8768');b=next(reversed(self.launch.tickets))
        for ticket,sid in [(a,self.session['id']),(b,other['id'])]:
            details=self.launch.claim(ticket,self.origin);token=self.bridge.call('connect',self.origin,{'code':details['code'],'url':details['url']})['connection']
            self.assertEqual(self.bridge.connections[token]['session_id'],sid)
    def test_launch_report_requires_the_claiming_extension_and_preserves_materials(self):
        ticket=self.ticket();self.launch.claim(ticket,self.origin)
        with self.assertRaises(LabError):self.launch.report(ticket,'chrome-extension://'+'b'*32,'ready')
        self.launch.report(ticket,self.origin,'permission')
        self.assertNotIn('execution',self.lab.state()['sessions'][0]['preparation'])

    def test_restarting_same_job_invalidates_old_ticket(self):
        old=self.ticket();self.launch.tickets[old]['created']-=16;new=self.ticket()
        with self.assertRaises(LabError):self.launch.claim(old,self.origin)
        self.assertEqual(self.launch.claim(new,self.origin)['session_id'],self.session['id'])

    def test_double_click_reuses_pending_launch_without_another_window(self):
        first=self.ticket();second=self.ticket()
        self.assertEqual(first,second);self.assertEqual(len(self.opened),1)

    def test_explicit_rescan_creates_fresh_ticket_even_when_current_page_is_connected(self):
        ticket=self.ticket();d=self.launch.claim(ticket,self.origin)
        self.bridge.call('connect',self.origin,{'code':d['code'],'url':d['url']})
        self.assertEqual(self.launch.request(self.session['id'],'http://127.0.0.1:8768')['status'],'ready')
        fresh=self.launch.request(self.session['id'],'http://127.0.0.1:8768',rescan=True)
        self.assertIn('ticket',fresh);self.assertNotEqual(fresh['ticket'],ticket)

    def test_explicit_rescan_reads_optional_sections_even_when_unsaved_page_is_preserved(self):
        self.lab.mutate(lambda s:s['sessions'][0]['preparation'].update(preserve_unsaved_page=True))
        first=self.ticket()
        self.assertTrue(self.launch.claim(first,self.origin)['resume_confirmed'])
        fresh=self.launch.request(self.session['id'],'http://127.0.0.1:8768',rescan=True)
        self.assertFalse(self.launch.claim(fresh['ticket'],self.origin)['resume_confirmed'])
        prep=self.lab.state()['sessions'][0]['preparation']
        self.assertTrue(prep['preserve_unsaved_page'])
        self.assertNotIn('execution',prep)

    def test_connected_controller_receives_launch_and_focus_without_opening_pages(self):
        ticket=self.ticket();details=self.launch.claim(ticket,self.origin)
        token=self.bridge.call('connect',self.origin,{'code':details['code'],'url':details['url']})['connection']
        self.launch.next(self.origin,token)
        self.launch.request(self.session['id'],'http://127.0.0.1:8768','focus')
        next_ticket=self.launch.next(self.origin,token)['ticket']
        self.assertEqual(len(self.opened),1)
        self.assertEqual(self.launch.claim(next_ticket,self.origin)['mode'],'focus')
        with self.assertRaises(LabError):self.launch.next('https://untrusted.example',token)
