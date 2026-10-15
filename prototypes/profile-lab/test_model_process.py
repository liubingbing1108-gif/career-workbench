import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from model_process import run_codex, model_environment, failure_diagnostics
from recognizer import CodexRecognizer, RecognitionError


class ModelProcessTests(unittest.TestCase):
    def run_fixture(self, source, timeout=2):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'fixture.py';path.write_text('import sys,json,time\nsys.stdin.read()\n'+source)
            return run_codex([sys.executable,'-u',str(path)],input='fictional',timeout=timeout,cwd=directory)

    def test_completed_turn_does_not_wait_for_lingering_process(self):
        started=time.monotonic()
        result=self.run_fixture('print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"{}"}}),flush=True)\nprint(json.dumps({"type":"turn.completed"}),flush=True)\ntime.sleep(20)')
        self.assertEqual(result.returncode,0);self.assertLess(time.monotonic()-started,2)
        self.assertIn('turn.completed',result.stdout)

    def test_partial_message_without_completion_is_not_accepted(self):
        with self.assertRaises(subprocess.TimeoutExpired) as ctx:
            self.run_fixture('print(json.dumps({"type":"item.completed","item":{"type":"agent_message","text":"{}"}}),flush=True)\ntime.sleep(20)',.3)
        self.assertIn('agent_message',ctx.exception.stdout)

    def test_failed_turn_preserves_error_and_exits_promptly(self):
        result=self.run_fixture('print(json.dumps({"type":"turn.failed","error":{"message":"workspace routing discovery failed"}}),flush=True)\ntime.sleep(20)')
        self.assertEqual(result.returncode,1)
        self.assertEqual(failure_diagnostics(result.stdout,result.stderr,1)['code'],'connection_failed')

    def test_proxy_reuses_existing_system_settings_without_overriding_environment(self):
        with patch('model_process.sys.platform','darwin'),patch.dict(os.environ,{},clear=True),patch('model_process.getproxies',return_value={'http':'http://127.0.0.1:7897','https':'http://127.0.0.1:7897'}):
            self.assertEqual(model_environment()['HTTPS_PROXY'],'http://127.0.0.1:7897')
            self.assertEqual(model_environment()['WSS_PROXY'],'http://127.0.0.1:7897')
            self.assertEqual(model_environment()['WS_PROXY'],'http://127.0.0.1:7897')
            os.environ['https_proxy']='http://explicit.example:1234'
            env=model_environment();self.assertEqual(env['https_proxy'],'http://explicit.example:1234');self.assertNotIn('HTTPS_PROXY',env)
            self.assertEqual(env['WSS_PROXY'],'http://explicit.example:1234')
            os.environ['wss_proxy']='http://explicit-ws.example:1234'
            self.assertNotIn('WSS_PROXY',model_environment())
            self.assertEqual(model_environment()['wss_proxy'],'http://explicit-ws.example:1234')

    def test_timeout_diagnostics_are_classified_without_persisting_private_output(self):
        raw='workspace routing discovery failed secret-token user@example.invalid'
        error=subprocess.TimeoutExpired(['fictional'],1,output=b'{"type":"turn.started"}',stderr=raw.encode())
        with patch('recognizer.run_codex',side_effect=error):
            with self.assertRaises(RecognitionError) as ctx:CodexRecognizer(timeout=1).call('fictional',{})
        self.assertEqual(ctx.exception.code,'connection_failed')
        self.assertNotIn('secret-token',json.dumps(ctx.exception.diagnostics))
        self.assertNotIn('user@example.invalid',str(ctx.exception))

    def test_structured_inference_keeps_runtime_host_without_global_skill_instructions(self):
        events=[{'type':'item.completed','item':{'type':'agent_message','text':'{"ok":true}'}},
                {'type':'turn.completed','usage':{}}]
        result=subprocess.CompletedProcess([],0,'\n'.join(json.dumps(e) for e in events),'')
        with patch('recognizer.run_codex',return_value=result) as run:
            answer,_=CodexRecognizer().call('fictional',{})
        self.assertEqual(answer,{'ok':True})
        command=run.call_args.args[0]
        for feature in ('code_mode_host','respect_system_proxy'):
            self.assertEqual(command[command.index(feature)-1],'--enable')
        for feature in ('shell_tool','apps','browser_use','computer_use','multi_agent','plugins','skill_search'):
            self.assertEqual(command[command.index(feature)-1],'--disable')
        self.assertIn('web_search="disabled"',command)
        self.assertIn('skills.include_instructions=false',command)
        self.assertEqual(command[command.index('--sandbox')+1],'read-only')

    def test_structured_inference_still_rejects_execution_events(self):
        event={'type':'item.completed','item':{'type':'command_execution','command':'fictional'}}
        result=subprocess.CompletedProcess([],0,json.dumps(event),'')
        with patch('recognizer.run_codex',return_value=result):
            with self.assertRaisesRegex(RecognitionError,'非预期执行事件'):
                CodexRecognizer().call('fictional',{})


if __name__=='__main__':unittest.main()
