import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from recognizer import CodexRecognizer, RecognitionError

SCHEMA = {'type':'object','properties':{'value':{'type':'string'}},'required':['value'],'additionalProperties':False}


class AgentAdapterTests(unittest.TestCase):
    def call(self, response, web=False, consent='1'):
        with tempfile.TemporaryDirectory() as folder:
            runner = Path(folder) / 'runner.py'
            runner.write_text('import json,sys\nr=json.load(sys.stdin)\nassert r["protocol_version"]==1\nprint('+repr(json.dumps(response))+')\n')
            with patch.dict(os.environ, {'CAREER_AGENT_COMMAND':json.dumps([sys.executable,str(runner)]),'CAREER_AGENT_ALLOW_PERSONAL_DATA':consent}):
                return CodexRecognizer(web_search=web).call('fictional request', SCHEMA)

    def test_custom_agent_works_without_codex(self):
        self.assertEqual(self.call({'protocol_version':1,'result':{'value':'fictional'}})[0], {'value':'fictional'})

    def test_schema_rejects_wrong_value_type(self):
        with self.assertRaises(RecognitionError):self.call({'protocol_version':1,'result':{'value':17}})

    def test_personal_data_requires_operator_configuration(self):
        with self.assertRaises(RecognitionError) as ctx:self.call({},consent='')
        self.assertEqual(ctx.exception.code,'agent_consent')

    def test_public_search_without_opened_evidence_fails(self):
        with self.assertRaises(RecognitionError) as ctx:self.call({'protocol_version':1,'result':{'value':'fictional'}},web=True)
        self.assertEqual(ctx.exception.code,'search_not_executed')

    def test_public_search_carries_evidence_without_personal_consent(self):
        response={'protocol_version':1,'result':{'value':'fictional'},'web_pages':[{'url':'https://example.com/jobs','opened':True,'snippet':'example'}]}
        self.assertEqual(len(self.call(response,web=True,consent='')[1]['web_pages']),1)

    def test_command_is_argv_not_shell(self):
        with patch.dict(os.environ, {'CAREER_AGENT_COMMAND':'echo unsafe'}):
            with self.assertRaises(RecognitionError):CodexRecognizer().call('test',SCHEMA)
