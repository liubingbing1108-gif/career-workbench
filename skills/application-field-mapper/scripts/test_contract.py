"""Synthetic forward contract examples and adversarial output mutations."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from validate import (ROOT, CONTRACT, RULES, ContractError, canonical,
                      check_relation_only_diff, digest, eligible_relations,
                      guard_update, load_bundle, run_fixture,
                      semantic_fingerprint, update_payload_digest, validate_pair)


def sample():
    case = json.loads((ROOT / 'fixtures/conformance.json').read_text())['cases'][0]
    return case['request'], case['response']


def relation(request, index=0, scope='site', fid='project_role'):
    q = request['questions'][index]
    return dict(id='relation-fictional-1', revision=1, state='active', kind='alias',
                scope=dict(level=scope, origin=request['site']['origin'] if scope == 'site' else '',
                           tenant=request['site']['tenant'] if scope == 'site' else '',
                           form_key=request['site']['form_key'] if scope == 'site' else '',
                           category=q['object']['category'], record_type=q['object']['record_type'], entry_id=None),
                semantic_fingerprint=q['semantic_fingerprint'], question_label=q['label'],
                question_context='虚构项目角色问题；明确同义与复用范围。', field_ids=[fid],
                field_revisions=[{'field_id': fid, 'revision': 1}],
                selector=sample()[1]['decisions'][index]['selector'],
                plan={'kind': 'alias', 'transform': None, 'extracts': []},
                confirmation_id='fictional-confirmation-1', confirmation_basis='虚构总预览明确接受对应与范围',
                confirmed_at='2026-10-16T00:00:00+08:00', supersedes=None,
                rules_version=RULES, contract_version=CONTRACT)


def exclusion(r):
    return {k: copy.deepcopy(r[k]) for k in ['scope', 'semantic_fingerprint', 'field_ids', 'revision', 'selector', 'plan']} | {'id': 'fictional-exclusion-1', 'reason': '用户纠正旧目标', 'match': 'target'}


def command(request, r, op='correct'):
    c = dict(contract_version=CONTRACT, operation=op, idempotency_key='fictional-key-1', payload_sha256='0' * 64,
             expected_context=request['context'], relation_id=r['id'], expected_revision=r['revision'],
             candidate={**r, 'state': 'candidate'}, confirmation_id='fictional-confirmation-2',
             confirmation_basis='虚构操作明确接受对应', reason='虚构纠错')
    c['payload_sha256'] = update_payload_digest(c)
    return c


class ModelContractTests(unittest.TestCase):
    def setUp(self):
        self.req, self.out = sample()

    def reject(self, code):
        with self.assertRaisesRegex(ContractError, '^' + code + '$'):
            validate_pair(self.req, self.out)

    def test_all_fifteen_synthetic_decisions(self):
        self.assertEqual(run_fixture(ROOT / 'fixtures/conformance.json'), 1)
        self.assertEqual(len(self.out['decisions']), 15)
        self.assertEqual({d['sources'][0]['field_id'] for d in self.out['decisions'][:3]}, {'project_role'})

    def test_portable_negative_fixture_corpus(self):
        self.assertEqual(run_fixture(ROOT / 'fixtures/rejections.json'), 12)

    def test_missing_and_version_preserve_semantic_identity(self):
        for index, availability in [(3, 'missing_value'), (4, 'version_needed')]:
            d = self.out['decisions'][index]
            self.assertEqual(d['semantic_status'], 'equivalent')
            self.assertEqual(d['availability']['status'], availability)
            self.assertIsNone(d['new_attribute'])
        self.out['decisions'][3]['availability']['status'] = 'ready'
        self.reject('availability_mismatch')

    def test_unknown_field(self):
        self.out['decisions'][0]['sources'][0]['field_id'] = 'invented'
        self.reject('unknown_field')

    def test_family_cannot_borrow_project_role(self):
        self.out['decisions'][0]['sources'][0]['field_id'] = 'family_company'
        self.reject('cross_category')

    def test_exam_cannot_supply_language_ability(self):
        self.out['decisions'][-1]['sources'][0]['field_id'] = 'fictional_exam_score'
        self.reject('cross_subtype')

    def test_local_field_cannot_leak_to_other_project(self):
        self.req['catalog'][0]['entry_id'] = 'fictional-project-2'
        self.reject('cross_entry')

    def test_context_replay_different_job(self):
        self.out['context'] = {**self.out['context'], 'session_id': 'another-job'}
        self.reject('stale_context')

    def test_optional_question_must_be_covered(self):
        self.out['decisions'].pop()
        self.reject('question_coverage')

    def test_duplicate_decisions_rejected(self):
        self.out['decisions'].append(self.out['decisions'][0])
        self.reject('duplicate_decision')

    def test_no_model_write_or_activation(self):
        self.out['decisions'][0]['write_profile'] = True
        self.reject('schema_response')
        del self.out['decisions'][0]['write_profile']
        self.out['decisions'][0]['proposal_state'] = 'active'
        self.reject('schema_response')

    def test_partial_not_complete(self):
        d = self.out['decisions'][8]
        d['semantic_status'] = 'equivalent'
        self.reject('partial_as_complete')

    def test_composition_not_alias(self):
        self.out['decisions'][6]['plan']['kind'] = 'alias'
        self.reject('plan_status_mismatch')

    def test_extraction_is_grounded_and_draft_only(self):
        d = self.out['decisions'][7]
        d['plan']['extracts'][0]['end'] = 999
        self.reject('extract_bounds')
        d['plan']['extracts'][0]['end'] = 8
        d['availability']['status'] = 'not_evaluated'
        self.reject('extract_not_draft')

    def test_extraction_cannot_cross_record(self):
        self.req['source_spans'][0]['entry_id'] = 'another-project'
        self.reject('extract_wrong_entry')

    def test_extraction_cannot_mix_group_versions(self):
        span = copy.deepcopy(self.req['source_spans'][0])
        span.update(id='span2', version_id='fictional-another-version')
        self.req['source_spans'].append(span)
        self.out['decisions'][7]['plan']['extracts'].append({'span_id': 'span2', 'start': 1, 'end': 3, 'covers': '另一片段'})
        self.reject('extract_mixed_object_or_version')

    def test_new_needs_expanded_catalog_receipt(self):
        self.req['search']['complete_categories'] = []
        self.reject('incomplete_search')

    def test_expanded_search_finds_existing_custom_alias(self):
        f = copy.deepcopy(self.req['catalog'][0])
        f.update(id='fictional_custom_budget', label='本项目计价币种', aliases=['项目预算币种'])
        self.req['catalog'].append(f)
        self.reject('duplicate_attribute')
        # The subsequent candidate references the discovered existing custom ID.
        d = self.out['decisions'][11]
        d.update(semantic_status='equivalent', sources=[{'field_id': f['id'], 'covers': '预算币种'}],
                 new_attribute=None, coverage={'covered': ['预算币种'], 'uncovered': [], 'partial': False},
                 plan={'kind': 'alias', 'transform': None, 'extracts': []})
        self.assertTrue(validate_pair(self.req, self.out))

    def test_highest_requires_rank_in_same_object(self):
        d = self.out['decisions'][13]
        d['selector']['rank'] = None
        self.reject('highest_without_rank')
        d['selector']['rank'] = {'field_id': 'family_company', 'domain': 'text', 'direction': 'desc'}
        self.reject('cross_category')

    def test_unknown_selected_entry(self):
        self.out['decisions'][0]['selector']['entry_ids'] = ['invented-entry']
        self.reject('unknown_entry')

    def test_group_fields_share_one_selector(self):
        for q in self.req['questions'][:2]:
            q['group_id'] = 'same-project-row'
        self.out['decisions'][1]['selector']['selection'] = 'all'
        self.reject('inconsistent_group')

    def test_versions_from_two_objects_or_two_group_versions_rejected(self):
        check = self.req['availability_checks'][0]
        check['version_refs'] = [{'entry_id': 'other-entry', 'version_id': 'v1', 'revision': 1}]
        self.reject('version_wrong_entry')
        check['version_refs'] = [{'entry_id': check['entry_ids'][0], 'version_id': v, 'revision': 1} for v in ['v1', 'v2']]
        self.reject('mixed_group_versions')

    def test_no_precision_invention_or_scale_conversion(self):
        self.out['decisions'][5]['plan']['transform'] = 'add_day_01'
        self.reject('schema_response')
        self.out['decisions'][5]['plan']['transform'] = 'month'
        self.req['questions'][0]['scale'] = 'incompatible-scale'
        self.req['questions'][0]['semantic_fingerprint'] = semantic_fingerprint(self.req['questions'][0])
        self.reject('incompatible_scale')

    def test_no_personal_url_or_stale_fingerprint(self):
        self.req['site']['origin'] += '/apply?token=fictional'
        self.reject('unsafe_site_origin')
        self.req['site']['origin'] = 'https://careers.example.test'
        self.req['questions'][0]['instructions'] = 'Changed meaning'
        self.reject('fingerprint_mismatch')


class RelationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.req, self.out = sample()
        self.q = self.req['questions'][0]
        self.r = relation(self.req)
        self.req['relations'] = [self.r]

    def lookup(self):
        return eligible_relations(self.req, self.q, 'projects', '')[0]

    def test_active_relation_reused_only_with_same_plan(self):
        self.out['decisions'][0]['relation_id'] = self.r['id']
        self.assertTrue(validate_pair(self.req, self.out))
        self.out['decisions'][0]['selector']['selection'] = 'all'
        with self.assertRaisesRegex(ContractError, 'relation_plan_changed'):
            validate_pair(self.req, self.out)

    def test_site_tenant_and_form_isolation(self):
        for key in ['origin', 'tenant', 'form_key']:
            with self.subTest(key=key):
                req = copy.deepcopy(self.req)
                req['site'][key] = 'different'
                self.assertEqual(eligible_relations(req, self.q, 'projects', '')[0], 'miss')
        self.req['site']['tenant'] = ''
        self.assertEqual(self.lookup(), 'miss')

    def test_general_scope_still_requires_constraints(self):
        self.r['scope'].update(level='general', origin='', tenant='', form_key='')
        self.req['site']['tenant'] = 'different'
        self.assertEqual(self.lookup(), 'hit')
        self.r['scope']['record_type'] = 'unrelated-subtype'
        self.assertEqual(self.lookup(), 'miss')

    def test_disabled_and_superseded_do_not_revive(self):
        for state in ['candidate', 'needs_review', 'disabled', 'superseded']:
            with self.subTest(state=state):
                self.r['state'] = state
                self.assertEqual(self.lookup(), 'miss')
        self.r['state'] = 'active'
        self.req['exclusions'] = [exclusion(self.r)]
        # A new relation ID and a broad scope cannot bypass the old exclusion.
        self.r['id'] = 'new-id'
        self.r['scope'] = {**self.r['scope'], 'level': 'general', 'origin': '', 'tenant': '', 'form_key': ''}
        self.assertEqual(self.lookup(), 'miss')
        with self.assertRaisesRegex(ContractError, 'excluded_target'):
            validate_pair(self.req, self.out)

    def test_conflicting_active_targets_not_ranked(self):
        other = relation(self.req, fid='project_responsibilities')
        other['id'] = 'other-relation'
        self.req['relations'].append(other)
        self.assertEqual(self.lookup(), 'conflict')
        with self.assertRaisesRegex(ContractError, 'relation_conflict'):
            validate_pair(self.req, self.out)

    def test_correct_same_field_selector_without_reenabling_old_plan(self):
        old = relation(self.req, index=13, fid='school')
        block = exclusion(old)
        block['match'] = 'plan'
        self.req['exclusions'] = [block]
        replacement = copy.deepcopy(old)
        replacement['id'] = 'corrected-scope'
        replacement['selector']['selection'] = 'one'
        replacement['selector']['rank'] = None
        replacement['selector']['filters'] = [{'field_id': 'degree', 'domain': 'education_level', 'op': 'in', 'values': ['本科']}]
        self.req['relations'] = [old, replacement]
        outcome, matches = eligible_relations(self.req, self.req['questions'][13], 'education', '')
        self.assertEqual(outcome, 'hit')
        self.assertEqual([r['id'] for r in matches], ['corrected-scope'])
        # The old selector remains blocked even with an unrelated new ID.
        replacement['selector'] = copy.deepcopy(old['selector'])
        self.assertEqual(eligible_relations(self.req, self.req['questions'][13], 'education', '')[0], 'miss')

    def test_context_changes_and_length_only_change(self):
        self.q['length']['max'] = 12
        self.assertEqual(semantic_fingerprint(self.q), self.q['semantic_fingerprint'])
        self.assertEqual(self.lookup(), 'hit')
        for key, value in [('instructions', '不同含义'), ('options', ['甲', '乙']), ('unit', '万元')]:
            with self.subTest(key=key):
                q = copy.deepcopy(self.q)
                q[key] = value
                q['semantic_fingerprint'] = semantic_fingerprint(q)
                self.assertEqual(eligible_relations(self.req, q, 'projects', '')[0], 'miss')

    def test_field_rename_revision_and_deletion(self):
        self.req['catalog'][0]['label'] = '项目中的角色'
        self.req['catalog'][0]['revision'] = 2
        self.assertEqual(self.lookup(), 'miss')
        self.r['field_revisions'][0]['revision'] = 2
        self.assertEqual(self.lookup(), 'hit')
        self.assertEqual(self.r['field_ids'], ['project_role'])
        self.req['catalog'].pop(0)
        self.assertEqual(self.lookup(), 'miss')

    def test_equivalent_merge_must_move_exclusion_too(self):
        self.req['exclusions'] = [exclusion(self.r)]
        target = copy.deepcopy(self.req['catalog'][0])
        target['id'] = 'fictional-merged-role'
        self.req['catalog'].append(target)
        self.r['field_ids'] = [target['id']]
        self.r['field_revisions'] = [{'field_id': target['id'], 'revision': 1}]
        self.req['exclusions'][0]['field_ids'] = [target['id']]
        self.assertEqual(self.lookup(), 'miss')
        # This tests the post-migration invariant, not a real migration runner.

    def test_stale_confirmation_and_concurrent_correction(self):
        c = command(self.req, self.r)
        self.assertEqual(guard_update(self.r, c, self.req['context'], {}), 'eligible_for_transaction')
        self.r['revision'] += 1
        with self.assertRaisesRegex(ContractError, 'revision_conflict'):
            guard_update(self.r, c, self.req['context'], {})
        c['expected_revision'] = self.r['revision']
        c['payload_sha256'] = update_payload_digest(c)
        with self.assertRaisesRegex(ContractError, 'stale_context'):
            guard_update(self.r, c, {**self.req['context'], 'relation_revision': 'new-revision'}, {})

    def test_idempotency_returns_original_receipt_without_reapply(self):
        c = command(self.req, self.r)
        receipts = {c['idempotency_key']: {'payload_sha256': c['payload_sha256']}}
        self.r['revision'] += 1
        self.r['state'] = 'disabled'
        self.assertEqual(guard_update(self.r, c, self.req['context'], receipts), 'replayed')
        c['reason'] = 'different-body'
        c['payload_sha256'] = update_payload_digest(c)
        with self.assertRaisesRegex(ContractError, 'idempotency_conflict'):
            guard_update(self.r, c, self.req['context'], receipts)

    def test_confirmation_scope_and_restore_guards(self):
        c = command(self.req, self.r)
        for kwargs, error in [({'exclusion_hit': True}, 'excluded_target'), ({'scope_change': True}, 'scope_mismatch')]:
            with self.subTest(error=error), self.assertRaisesRegex(ContractError, error):
                guard_update(self.r, c, self.req['context'], {}, **kwargs)
        c['confirmation_id'] = None
        c['payload_sha256'] = update_payload_digest(c)
        with self.assertRaisesRegex(ContractError, 'confirmation_required'):
            guard_update(self.r, c, self.req['context'], {})
        self.r['state'] = 'disabled'
        with self.assertRaisesRegex(ContractError, 'restore_requires_explicit_review'):
            guard_update(self.r, c, self.req['context'], {})

    def test_state_transition_matrix(self):
        permitted = {'confirm': ['candidate'], 'correct': ['candidate', 'active', 'needs_review'],
                     'disable': ['candidate', 'active', 'needs_review'], 'invalidate': ['active'], 'reconfirm': ['needs_review']}
        for op, states in permitted.items():
            for state in ['candidate', 'active', 'needs_review']:
                with self.subTest(operation=op, state=state):
                    self.r['state'] = state
                    c = command(self.req, self.r, op)
                    if state in states:
                        self.assertEqual(guard_update(self.r, c, self.req['context'], {}), 'eligible_for_transaction')
                    else:
                        with self.assertRaisesRegex(ContractError, 'invalid_transition'):
                            guard_update(self.r, c, self.req['context'], {})

    def test_history_values_versions_and_original_files_are_immutable(self):
        before = {'facts': {'fictional': '旧事实'}, 'versions': ['fictional-v1'], 'files': ['fictional-original'],
                  'application_snapshots': [{'actual_value': '历史实际值'}], 'relations': [self.r], 'exclusions': []}
        after = copy.deepcopy(before)
        after['relations'][0]['state'] = 'disabled'
        after['exclusions'] = [exclusion(self.r)]
        self.assertTrue(check_relation_only_diff(before, after))
        for key in ['facts', 'versions', 'files', 'application_snapshots']:
            with self.subTest(key=key):
                bad = copy.deepcopy(after)
                bad[key] = []
                with self.assertRaisesRegex(ContractError, 'protected_data_changed'):
                    check_relation_only_diff(before, bad)
        self.assertEqual(before['relations'][0]['state'], 'active')


class BundleTests(unittest.TestCase):
    def test_version_pin_and_rule_loading(self):
        bundle = load_bundle()
        self.assertEqual(load_bundle(expected_digest=bundle['digest'])['digest'], bundle['digest'])
        self.assertIn('申请字段对应', bundle['rules'])
        self.assertNotIn('def guard_update', bundle['rules'])
        with self.assertRaisesRegex(ContractError, 'bundle_digest_mismatch'):
            load_bundle(expected_digest='0' * 64)

    def test_tampered_missing_extra_and_symlinked_files(self):
        for mutation, error in [('tamper', 'file_digest_mismatch'), ('missing', 'file_missing_or_outside'),
                                ('extra', 'manifest_inventory_mismatch'), ('symlink', 'symlink')]:
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(prefix='field-mapper-test-') as tmp:
                dest = Path(tmp) / 'bundle'
                shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns('__pycache__'))
                target = dest / 'SKILL.md'
                if mutation == 'tamper':
                    target.write_text('changed rules')
                elif mutation == 'missing':
                    target.unlink()
                elif mutation == 'extra':
                    (dest / 'unexpected.md').write_text('unreviewed')
                else:
                    target.unlink()
                    target.symlink_to(ROOT / 'SKILL.md')
                with self.assertRaisesRegex(ContractError, error):
                    load_bundle(dest)

    def test_unknown_contract_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix='field-mapper-test-') as tmp:
            dest = Path(tmp) / 'bundle'
            shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns('__pycache__'))
            manifest = json.loads((dest / 'manifest.json').read_text())
            manifest['contract_version'] = 'unsupported/v99'
            (dest / 'manifest.json').write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ContractError, 'unsupported_version'):
                load_bundle(dest)


if __name__ == '__main__':
    unittest.main()
