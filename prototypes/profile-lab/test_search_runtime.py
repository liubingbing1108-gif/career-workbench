import json
import subprocess
import unittest
from unittest.mock import patch
from recognizer import CodexRecognizer,RecognitionError

class SearchRuntimeTests(unittest.TestCase):
    def result(self,events,code=0):return subprocess.CompletedProcess([],code,'\n'.join(json.dumps(e) for e in events),'')
    def answer(self):return {'type':'item.completed','item':{'type':'agent_message','text':'{"candidates":[]}'}}
    def test_live_search_enables_host_and_rejects_toolless_answer(self):
        with patch('recognizer.run_codex',return_value=self.result([self.answer()])) as run:
            with self.assertRaises(RecognitionError) as err:CodexRecognizer(web_search=True).call('public-only',{})
            self.assertEqual(err.exception.code,'search_not_executed')
            command=run.call_args.args[0];i=command.index('code_mode_host');self.assertEqual(command[i-1],'--enable')
    def test_actual_open_results_are_exposed_without_prompts_or_stderr(self):
        event={'type':'item.completed','item':{'type':'web_search','action':{'type':'open_page'},'results':[{'type':'text_result','url':'https://example.com/','title':'示例公司','snippet':'Total lines: 2'}]}}
        with patch('recognizer.run_codex',return_value=self.result([event,self.answer()])):
            result,usage=CodexRecognizer(web_search=True).call('public-only',{})
            self.assertTrue(usage['web_pages'][0]['opened']);self.assertEqual(result,{'candidates':[]})
    def test_capacity_is_not_disguised_as_missing_official_site(self):
        with patch('recognizer.run_codex',return_value=self.result([{'type':'error','message':'Selected model is at capacity.'}],1)):
            with self.assertRaises(RecognitionError) as err:CodexRecognizer(web_search=True).call('public-only',{})
            self.assertEqual(err.exception.code,'capacity')
