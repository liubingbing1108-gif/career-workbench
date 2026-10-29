#!/usr/bin/env python3
"""Offline contract checks only: no model, product import, database or network."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import urlsplit

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
CONTRACT = 'application-field-mapper/v1'
RULES = '1.1.0'
RUNTIME = ['SKILL.md', 'references/decisions.md', 'references/contract.md']


class ContractError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise ContractError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def load_bundle(root=ROOT, expected_digest=None):
    root = Path(root).resolve()
    require(not (root / 'manifest.json').is_symlink(), 'manifest_symlink')
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    require(set(manifest) == {'package', 'rules_version', 'contract_version', 'runtime_files', 'files'}, 'manifest_shape')
    require(manifest['package'] == 'application-field-mapper' and manifest['rules_version'] == RULES and manifest['contract_version'] == CONTRACT, 'unsupported_version')
    require(manifest['runtime_files'] == RUNTIME, 'runtime_files_changed')
    actual_digest = digest(manifest)
    require(expected_digest is None or actual_digest == expected_digest, 'bundle_digest_mismatch')
    files = manifest['files']
    require(isinstance(files, dict) and files, 'empty_manifest')
    for name, expected in files.items():
        parts = PurePosixPath(name)
        require(not parts.is_absolute() and '..' not in parts.parts and str(parts) == name and '\\' not in name, 'unsafe_path')
        path = root / name
        require(not any((root.joinpath(*parts.parts[:i])).is_symlink() for i in range(1, len(parts.parts) + 1)), 'symlink')
        require(path.is_file() and path.resolve().is_relative_to(root), 'file_missing_or_outside')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'file_digest_mismatch')
    actual = {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p != root / 'manifest.json'}
    require(actual == set(files), 'manifest_inventory_mismatch')
    require(set(RUNTIME + ['schemas/contract.schema.json']).issubset(files), 'required_file_missing')
    schema = json.loads((root / 'schemas/contract.schema.json').read_text(encoding='utf-8'))
    from jsonschema import Draft202012Validator
    Draft202012Validator.check_schema(schema)
    rules = '\n\n'.join((root / p).read_text(encoding='utf-8') for p in RUNTIME)
    return {'manifest': manifest, 'digest': actual_digest, 'rules': rules, 'schema': schema}


def validate_shape(value, kind, schema=None):
    from jsonschema import Draft202012Validator
    if schema is None:
        schema = json.loads((ROOT / 'schemas/contract.schema.json').read_text(encoding='utf-8'))
    view = {**schema, '$ref': '#/$defs/' + kind}
    require(not next(Draft202012Validator(view).iter_errors(value), None), 'schema_' + kind)


def unique(items, key, code):
    ids = [item[key] for item in items]
    require(len(ids) == len(set(ids)), code)
    return {item[key]: item for item in items}


def semantic_fingerprint(q):
    keys = ['label', 'section', 'instructions', 'examples', 'control', 'options', 'condition', 'unit', 'scale']
    payload = {k: q[k] for k in keys}
    payload['object'] = {k: q['object'][k] for k in ['category', 'record_type', 'repeatable']}
    def trim(value):
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            return [trim(v) for v in value]
        if isinstance(value, dict):
            return {k: trim(v) for k, v in value.items()}
        return value
    return digest(trim(payload))


def scope_applies(scope, q, site, category, record_type):
    if scope['category'] != category or scope['record_type'] != record_type:
        return False
    if scope['entry_id'] is not None and scope['entry_id'] != q['object']['entry_id']:
        return False
    if scope['level'] == 'general':
        return not any(scope[k] for k in ['origin', 'tenant', 'form_key'])
    return bool(site['tenant']) and all(scope[k] == site[k] for k in ['origin', 'tenant', 'form_key'])


def excluded(request, q, field_ids, category, record_type, selector=None, plan=None):
    for x in request['exclusions']:
        if x['semantic_fingerprint'] != q['semantic_fingerprint'] or not scope_applies(x['scope'], q, request['site'], category, record_type):
            continue
        if x['match'] == 'target' and set(x['field_ids']) & set(field_ids):
            return True
        normalized_plan = {**plan, 'extracts': []} if plan and plan['kind'] == 'extract' else plan
        if x['match'] == 'plan' and x['field_ids'] == field_ids and x['selector'] == selector and x['plan'] == normalized_plan:
            return True
    return False


def relation_signature(relation):
    return digest({k: relation[k] for k in ['kind', 'field_ids', 'selector', 'plan']})


def eligible_relations(request, q, category, record_type):
    """Pure eligibility check over a caller-supplied snapshot, never a DB query."""
    fields = {f['id']: f for f in request['catalog']}
    eligible = []
    for r in request['relations']:
        if r['state'] != 'active' or r['contract_version'] != CONTRACT or r['rules_version'] != RULES:
            continue
        if not r['confirmation_id'] or not r['confirmation_basis'] or not r['confirmed_at']:
            continue
        if not scope_applies(r['scope'], q, request['site'], category, record_type) or r['semantic_fingerprint'] != q['semantic_fingerprint']:
            continue
        deps = {f['field_id']: f['revision'] for f in r['field_revisions']}
        if len(deps) != len(r['field_revisions']) or set(deps) != set(r['field_ids']):
            continue
        if any(fid not in fields or fields[fid]['revision'] != deps[fid] for fid in deps):
            continue
        if excluded(request, q, r['field_ids'], category, record_type, r['selector'], r['plan']):
            continue
        try:
            for fid in r['field_ids']:
                check_field(fields, fid, category, record_type, q)
            check_selector(r['selector'], fields, category, record_type, q)
        except ContractError:
            continue
        if r['kind'] == 'alias' and (len(r['field_ids']) != 1 or r['plan']['kind'] not in {'alias', 'transform'}):
            continue
        if r['kind'] == 'recipe' and (r['plan']['kind'] not in {'compose', 'extract'} or r['plan']['extracts']):
            continue
        eligible.append(r)
    if len({relation_signature(r) for r in eligible}) > 1:
        return 'conflict', eligible
    return ('hit' if eligible else 'miss'), eligible


def check_field(fields, fid, category, record_type, q):
    require(fid in fields, 'unknown_field')
    field = fields[fid]
    require(field['category'] == category, 'cross_category')
    require(not field['record_types'] or record_type in field['record_types'], 'cross_subtype')
    require(field['entry_id'] is None or field['entry_id'] == q['object']['entry_id'], 'cross_entry')
    return field


def check_selector(selector, fields, category, record_type, q):
    if selector is None:
        return
    require(len(selector['entry_ids']) == len(set(selector['entry_ids'])), 'duplicate_entry')
    require(set(selector['entry_ids']).issubset(q['object']['allowed_entry_ids']), 'unknown_entry')
    if q['object']['entry_id']:
        require(not selector['entry_ids'] or selector['entry_ids'] == [q['object']['entry_id']], 'wrong_bound_entry')
    if selector['selection'] in {'one', 'highest'}:
        require(len(selector['entry_ids']) <= 1, 'too_many_entries')
    require(selector['selection'] != 'highest' or selector['rank'] is not None, 'highest_without_rank')
    lo, hi = selector['min_items'], selector['max_items']
    require(lo is None or hi is None or lo <= hi, 'invalid_item_bounds')
    conditions = selector['filters'] + selector['required_values']
    for cond in conditions + ([selector['rank']] if selector['rank'] else []):
        check_field(fields, cond['field_id'], category, record_type, q)
        if 'op' in cond:
            require(cond['op'] == 'exists' or bool(cond['values']), 'empty_condition')


def validate_pair(request, response, schema=None):
    validate_shape(request, 'request', schema)
    validate_shape(response, 'response', schema)
    require(request['request_id'] == response['request_id'] and request['context'] == response['context'], 'stale_context')
    site = urlsplit(request['site']['origin'])
    require(site.scheme == 'https' and bool(site.hostname) and not site.username and not site.password and site.path in {'', '/'} and not site.query and not site.fragment, 'unsafe_site_origin')
    questions = unique(request['questions'], 'id', 'duplicate_question')
    fields = unique(request['catalog'], 'id', 'duplicate_field')
    decisions = unique(response['decisions'], 'question_id', 'duplicate_decision')
    checks = unique(request['availability_checks'], 'id', 'duplicate_check')
    spans = unique(request['source_spans'], 'id', 'duplicate_span')
    unique(request['relations'], 'id', 'duplicate_relation')
    unique(request['exclusions'], 'id', 'duplicate_exclusion')
    require(set(decisions) == set(questions), 'question_coverage')
    require(request['search']['catalog_revision'] == request['context']['catalog_revision'], 'stale_search')
    groups = {}
    for qid, d in decisions.items():
        q = questions[qid]
        require(q['semantic_fingerprint'] == semantic_fingerprint(q), 'fingerprint_mismatch')
        status, cat, subtype = d['semantic_status'], d['category'], d['record_type']
        require(not q['object']['category'] or cat == q['object']['category'], 'wrong_object')
        require(not q['object']['record_type'] or subtype == q['object']['record_type'], 'wrong_subtype')
        ids = [x['field_id'] for x in d['sources']]
        require(len(ids) == len(set(ids)), 'duplicate_source')
        for fid in ids + [f for a in d['alternatives'] for f in a['field_ids']]:
            check_field(fields, fid, cat, subtype, q)
        check_selector(d['selector'], fields, cat, subtype, q)
        certain = status in {'equivalent', 'transform', 'compose', 'extract_candidate'}
        if certain:
            require(bool(cat) and bool(ids), 'missing_source')
            require(not q['object']['repeatable'] or d['selector'] is not None, 'missing_selector')
            require(not q['object']['category'] or q['object']['repeatable'] or d['selector'] is None, 'scalar_selector')
        if q['group_id'] and certain:
            key = (cat, subtype, digest(d['selector']))
            require(q['group_id'] not in groups or groups[q['group_id']] == key, 'inconsistent_group')
            groups[q['group_id']] = key
        cov = d['coverage']
        require(cov['partial'] == bool(cov['uncovered']), 'coverage_flag')
        require(not cov['partial'] or status in {'ambiguous', 'unresolved'}, 'partial_as_complete')
        require(not certain or bool(cov['covered']), 'missing_coverage')
        plan = d['plan']
        expected_kind = {'equivalent': 'alias', 'transform': 'transform', 'compose': 'compose', 'extract_candidate': 'extract'}.get(status, 'none')
        require(plan['kind'] == expected_kind, 'plan_status_mismatch')
        require((status == 'transform') == (plan['transform'] is not None), 'invalid_transform')
        require(status != 'equivalent' and status != 'transform' or len(ids) == 1, 'alias_cardinality')
        require(status != 'compose' or len(ids) >= 2, 'compose_cardinality')
        require(status == 'extract_candidate' or not plan['extracts'], 'unexpected_extract')
        if status == 'transform':
            f = fields[ids[0]]
            if plan['transform'] in {'month', 'year'}:
                require(f['type'] in {'date', 'partial_date'}, 'date_transform_type')
            require(f['unit'] == q['unit'] and f['scale'] == q['scale'], 'incompatible_scale')
        if status == 'equivalent':
            require(fields[ids[0]]['unit'] == q['unit'] and fields[ids[0]]['scale'] == q['scale'], 'incompatible_scale')
        if status == 'extract_candidate':
            require(bool(plan['extracts']), 'missing_extract')
            owners = set()
            for e in plan['extracts']:
                require(e['span_id'] in spans, 'unknown_span')
                span = spans[e['span_id']]
                require(span['field_id'] in ids, 'extract_wrong_field')
                require(span['entry_id'] in q['object']['allowed_entry_ids'], 'extract_wrong_entry')
                require(q['object']['entry_id'] is None or span['entry_id'] == q['object']['entry_id'], 'extract_wrong_entry')
                require(0 <= e['start'] < e['end'] <= len(span['text']), 'extract_bounds')
                selected = (d['selector'] or {}).get('entry_ids', [])
                require(not selected or span['entry_id'] in selected, 'extract_unselected_entry')
                owners.add((span['entry_id'], span['version_id']))
            require(len(owners) == 1, 'extract_mixed_object_or_version')
        avail = d['availability']
        if avail['status'] in {'not_evaluated', 'draft_required'}:
            require(avail['check_id'] is None, 'unexpected_check')
        else:
            require(avail['check_id'] in checks, 'missing_check')
            c = checks[avail['check_id']]
            require(c['question_id'] == qid and c['context'] == request['context'] and set(c['field_ids']) == set(ids) and c['status'] == avail['status'], 'availability_mismatch')
            require(set(c['entry_ids']).issubset(q['object']['allowed_entry_ids']), 'availability_wrong_entry')
            require(q['object']['entry_id'] is None or not c['entry_ids'] or c['entry_ids'] == [q['object']['entry_id']], 'availability_wrong_entry')
            selected = (d['selector'] or {}).get('entry_ids', [])
            require(not selected or set(c['entry_ids']).issubset(selected), 'availability_unselected_entry')
            require(avail['status'] != 'ready' or not q['object']['repeatable'] or bool(c['entry_ids']), 'ready_without_object')
            require(all(v['entry_id'] in c['entry_ids'] for v in c['version_refs']), 'version_wrong_entry')
            require(len({v['entry_id'] for v in c['version_refs']}) == len(c['version_refs']), 'mixed_group_versions')
        require(status != 'extract_candidate' or avail['status'] == 'draft_required', 'extract_not_draft')
        require(status not in {'new_attribute_candidate', 'unresolved', 'ambiguous'} or avail['status'] in {'not_evaluated', 'conflict'}, 'uncertain_as_ready')
        require(not certain or not excluded(request, q, ids, cat, subtype, d['selector'], plan), 'excluded_target')
        outcome, rels = eligible_relations(request, q, cat, subtype)
        require(outcome != 'conflict' or status in {'ambiguous', 'unresolved'}, 'relation_conflict')
        if d['relation_id'] is not None:
            chosen = next((r for r in rels if r['id'] == d['relation_id']), None)
            require(outcome == 'hit' and chosen is not None, 'relation_not_reusable')
            # Extraction recipes intentionally contain no old personal offsets.
            proposal_plan = {**plan, 'extracts': []} if plan['kind'] == 'extract' else plan
            require(chosen['field_ids'] == ids and chosen['selector'] == d['selector'] and chosen['plan'] == proposal_plan, 'relation_plan_changed')
        new = d['new_attribute']
        require((status == 'new_attribute_candidate') == (new is not None), 'new_attribute_status')
        if new:
            require(cat and new['category'] == cat and new['record_type'] == subtype and not ids and d['relation_id'] is None, 'new_attribute_object')
            require(cat in request['search']['complete_categories'] and new['search_receipt'] == request['search']['receipt'] and not d['request_expand_catalog'], 'incomplete_search')
            require(outcome == 'miss', 'new_despite_relation')
            # Deterministic exact alias guard is only a lower bound; semantic
            # duplicate review over the expanded catalog remains mandatory.
            name = new['label'].strip().casefold()
            for f in fields.values():
                in_scope = f['category'] == cat and (not f['record_types'] or subtype in f['record_types']) and f['entry_id'] in {None, q['object']['entry_id']}
                require(not in_scope or name not in {x.strip().casefold() for x in [f['label']] + f['aliases']}, 'duplicate_attribute')
        require(not d['request_expand_catalog'] or status == 'unresolved', 'expand_status')
    return True


def update_payload_digest(command):
    return digest({k: v for k, v in command.items() if k != 'payload_sha256'})


def guard_update(current, command, context, receipts, exclusion_hit=False, scope_change=False):
    """Pure precondition oracle, not a write service or a transaction emulator."""
    validate_shape(command, 'update')
    require(command['payload_sha256'] == update_payload_digest(command), 'payload_digest_mismatch')
    key = command['idempotency_key']
    if key in receipts:
        require(receipts[key]['payload_sha256'] == command['payload_sha256'], 'idempotency_conflict')
        return 'replayed'
    require(command['expected_context'] == context, 'stale_context')
    require(command['expected_revision'] == (current['revision'] if current else 0), 'revision_conflict')
    require(current is None or command['relation_id'] == current['id'], 'wrong_relation')
    require(not current or current['state'] not in {'disabled', 'superseded'}, 'restore_requires_explicit_review')
    op = command['operation']
    states = {'confirm': {None, 'candidate'}, 'correct': {'candidate', 'active', 'needs_review'}, 'disable': {'candidate', 'active', 'needs_review'}, 'invalidate': {'active'}, 'reconfirm': {'needs_review'}}
    require((current['state'] if current else None) in states[op], 'invalid_transition')
    if op != 'invalidate':
        require(bool(command['confirmation_id']) and bool(command['confirmation_basis']), 'confirmation_required')
    require(not exclusion_hit or op in {'disable', 'invalidate'}, 'excluded_target')
    require(not scope_change, 'scope_mismatch')
    require(command['candidate']['state'] == 'candidate', 'model_cannot_activate')
    return 'eligible_for_transaction'


def check_relation_only_diff(before, after):
    """Verify protected payloads, without storing or modifying either input."""
    allowed = {'relations', 'exclusions', 'relation_audit', 'relation_receipts', 'preview_validity'}
    for key in (set(before) | set(after)) - allowed:
        require(before.get(key) == after.get(key), 'protected_data_changed')
    return True


def run_fixture(path, schema=None):
    path = Path(path)
    fixture = json.loads(path.read_text(encoding='utf-8'))
    require(fixture['fictional'] is True, 'fictional_fixture_required')
    base = None
    if 'base_fixture' in fixture:
        name = fixture['base_fixture']
        require(isinstance(name, str) and Path(name).name == name, 'unsafe_fixture_path')
        base_doc = json.loads((path.parent / name).read_text(encoding='utf-8'))
        require(base_doc['fictional'] is True, 'fictional_fixture_required')
        base = base_doc['cases'][0]
    for case in fixture['cases']:
        pair = case
        if base is not None:
            import copy
            pair = copy.deepcopy(base)
            for change in case['changes']:
                target = pair[change['side']]
                for key in change['path'][:-1]:
                    target = target[key]
                target[change['path'][-1]] = change['value']
        error = None
        try:
            validate_pair(pair['request'], pair['response'], schema)
        except ContractError as e:
            error = str(e)
        require(error == case['expected_error'], 'fixture_failed:' + case['name'] + ':' + str(error))
    return len(fixture['cases'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--self-test', action='store_true')
    parser.add_argument('--check')
    parser.add_argument('--expected-digest')
    args = parser.parse_args()
    bundle = load_bundle(expected_digest=args.expected_digest)
    print('PASS bundle', RULES, CONTRACT, bundle['digest'])
    if args.check:
        path = Path(args.check)
        print('PASS fixture cases', run_fixture(path if path.is_absolute() else ROOT / path, bundle['schema']))
    if args.self_test:
        import unittest
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'scripts'), pattern='test_contract.py')
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ContractError, OSError, ValueError) as error:
        print('FAIL', type(error).__name__, str(error), file=sys.stderr)
        sys.exit(1)
