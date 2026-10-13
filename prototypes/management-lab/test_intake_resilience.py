"""Fictional inputs: no model, network, browser or applicant data."""
import threading
import time
import unittest
from unittest.mock import Mock

from intake import JobIntake, input_urls
from test_intake_migration import Model


class IntakeResilienceTests(unittest.TestCase):
    url = 'https://sample.jobs.feishu.cn/123456/resume/1234567890123456789/apply'

    def test_explicit_company_role_does_not_wait_for_network_or_model(self):
        for text in [self.url + '\n示例科技 用户增长产品经理（平台运营）',
                     '示例科技\t用户增长产品经理（平台运营）\n' + self.url,
                     '[申请入口](' + self.url + ')\n示例科技 用户增长产品经理（平台运营）',
                     self.url + '\n公司：示例科技\n岗位：用户增长产品经理（平台运营）',
                     '我要投递示例科技的用户增长产品经理（平台运营）岗位\n' + self.url]:
            with self.subTest(text=text):
                model, reader = Mock(), Mock()
                row = JobIntake(model, reader).preview(text)[0]
                self.assertEqual((row['company'], row['role']), ('示例科技', '用户增长产品经理（平台运营）'))
                self.assertEqual(row['source_url'], self.url)
                self.assertEqual(row['official_url_status'], 'unverified')
                self.assertFalse(row['needs_review'])
                model.call.assert_not_called(); reader.assert_not_called()

    def test_link_only_dynamic_shell_keeps_editable_preview_without_model_wait(self):
        model = Mock()
        row = JobIntake(model, lambda u: ('投递简历 - 示例科技校招官网', [])).preview(self.url)[0]
        self.assertEqual(row['source_url'], self.url)
        self.assertEqual((row['company'], row['role']), ('', ''))
        self.assertTrue(row['needs_review']); model.call.assert_not_called()

    def test_slow_reader_is_bounded_and_late_response_cannot_change_preview(self):
        release, finished = threading.Event(), threading.Event()
        def reader(url):
            release.wait(2); finished.set(); return ('迟到公司 迟到岗位', [])
        try:
            started = time.monotonic()
            row = JobIntake(Mock(), reader, read_timeout=.03).preview(self.url)[0]
            self.assertLess(time.monotonic() - started, .5)
            self.assertEqual(row['role'], '')
        finally:
            release.set(); self.assertTrue(finished.wait(1))
        self.assertEqual(row['role'], '')

    def test_equivalent_parentheses_and_whitespace_restore_original_text(self):
        role = '用户增长产品经理（平台运营）'
        model = Model({'jobs': [{'company':'示例科技', 'role':'用户增长产品经理 (平台运营)',
                                'url':self.url, 'evidence':'示例科技 用户增长产品经理 (平台运营)'}]})
        row = JobIntake(model, lambda u: ('示例科技\n' + role, [])).preview(self.url)[0]
        self.assertEqual(row['company'], '示例科技'); self.assertEqual(row['role'], role)

    def test_multiple_links_keep_their_own_source_not_the_first_url(self):
        urls = ['https://example.com/a', 'https://example.com/b']
        pages = {urls[0]: ('示例甲 产品经理', []), urls[1]: ('示例乙 研发工程师', [])}
        model = Model({'jobs': [{'company':'示例乙','role':'研发工程师','url':urls[1],'evidence':'示例乙 研发工程师'},
                                {'company':'示例甲','role':'产品经理','url':urls[0],'evidence':'示例甲 产品经理'}]})
        rows = JobIntake(model, pages.__getitem__).preview('\n'.join(urls))
        self.assertEqual([(r['company'],r['source_url']) for r in rows], [('示例乙',urls[1]),('示例甲',urls[0])])

    def test_missing_link_result_stays_available_without_fabricating_identity(self):
        urls = ['https://example.com/a', 'https://example.com/b']
        model = Model({'jobs':[{'company':'示例甲','role':'产品经理','url':urls[0],'evidence':'示例甲 产品经理'}]})
        rows = JobIntake(model, lambda u: ('示例甲 产品经理', [])).preview('\n'.join(urls))
        self.assertEqual(len(rows),2); self.assertEqual(rows[1]['source_url'],urls[1])
        self.assertEqual(rows[1]['company'],''); self.assertTrue(rows[1]['needs_review'])

    def test_invalid_output_fails_to_editable_draft_not_http_error(self):
        for result in [None, [], {'jobs':None}, {'jobs':[None]}, {'jobs':[{'company':12}]}]:
            row=JobIntake(Model(result), lambda u: ('示例科技招聘', [])).preview(self.url)[0]
            self.assertTrue(row['needs_review']); self.assertEqual(row['source_url'],self.url)

    def test_markdown_query_and_fragment_links_are_preserved(self):
        url='https://example.com/job?filter=(campus)&channel=a|b#岗位'
        self.assertEqual(input_urls('[岗位入口](' + url + ')'), [url])
        model=Model({'jobs':[]})
        row=JobIntake(model,lambda u:('',[])).preview(url)[0]
        self.assertEqual(row['source_url'],url); self.assertEqual(row['company'],'')

    def test_negatives_collections_and_ambiguous_text_use_model(self):
        for text in ['示例科技 不投产品经理', '示例科技 产品经理和研发工程师',
                     '我要投递示例科技的产品经理或者研发工程师', '请 整理这些岗位',
                     '我要投递示例科技的产品经理和研发工程师', 'Example Corp Product Manager']:
            model=Model({'jobs':[]})
            row=JobIntake(model).preview(text)[0]
            self.assertTrue(model.calls); self.assertEqual(row['role'],'')

    def test_company_and_role_from_another_page_cannot_be_paired_to_this_link(self):
        urls=['https://example.com/a','https://example.com/b']
        pages={urls[0]:('示例甲 产品经理',[]),urls[1]:('示例乙 研发工程师',[])}
        model=Model({'jobs':[{'company':'示例甲','role':'产品经理','url':urls[1],'evidence':'示例甲 产品经理'}]})
        rows=JobIntake(model,pages.__getitem__).preview('\n'.join(urls))
        self.assertEqual([r['source_url'] for r in rows],urls)
        self.assertTrue(all(not r['company'] and not r['role'] for r in rows))

    def test_tabular_input_keeps_source_link_without_official_verification(self):
        row=JobIntake().preview('示例科技 | 产品经理 | https://example.com/a')[0]
        self.assertEqual(row['source_url'],'https://example.com/a')
        self.assertEqual(row['official_url_status'],'unverified')


if __name__ == '__main__':
    unittest.main()
