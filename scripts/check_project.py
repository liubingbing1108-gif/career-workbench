#!/usr/bin/env python3
"""Validate public project contracts and per-change records; no runtime access."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

LEGACY_RECORDS = {'20261015T124128Z-profile-prd-mapping-and-writeback',
                  '20261015T124141Z-repository-governance',
                  '20261016T021248Z-profile-correction-loop-prd'}

def public_root(root):
    overlay = root / 'release/public'
    return overlay if overlay.is_dir() else root


def safe_path(value):
    return (isinstance(value, str) and bool(value) and '\\' not in value
            and not PurePosixPath(value).is_absolute()
            and '..' not in PurePosixPath(value).parts
            and not set(PurePosixPath(value).parts) & {'.runtime', '.git', '.env'})


def validate(root, check_index=True):
    root = Path(root).resolve()
    public = public_root(root)
    errors = []
    def read(path):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            errors.append(f'{path.name}: missing or invalid JSON')
            return None
    def exists(name):
        return safe_path(name) and ((public / name).is_file() or (root / name).is_file())
    for name in ('GOVERNANCE.md', 'docs/AGENT_PLAYBOOK.md', 'docs/CAPABILITIES.json'):
        if not exists(name):
            errors.append(f'Missing governance document: {name}')
    package = read(root / 'package.json')
    lock = read(root / 'package-lock.json')
    version = package.get('version') if isinstance(package, dict) else None
    locked_root = lock.get('packages', {}).get('', {}) if isinstance(lock, dict) and isinstance(lock.get('packages'), dict) else {}
    if (not isinstance(version, str) or not isinstance(lock, dict)
            or lock.get('version') != version or not isinstance(locked_root, dict)
            or locked_root.get('version') != version):
        errors.append('package.json and package-lock.json versions must agree')
    catalog = read(public / 'docs/CAPABILITIES.json')
    caps = catalog.get('capabilities', []) if isinstance(catalog, dict) else []
    if not isinstance(catalog, dict) or catalog.get('schema_version') != 1 or not isinstance(caps, list) or not caps:
        errors.append('Invalid capability catalog')
        caps = []
    ids = set()
    graph = {}
    for cap in caps:
        if not isinstance(cap, dict):
            errors.append('Capability must be an object'); continue
        cid = cap.get('id')
        if not isinstance(cid, str) or not re.fullmatch(r'[a-z][a-z0-9-]+', cid) or cid in ids:
            errors.append('Invalid or duplicate capability id'); continue
        ids.add(cid)
        if cap.get('status') not in {'implemented', 'partial', 'planned'}:
            errors.append(f'{cid}: invalid status')
        for key in ('summary', 'limitations', 'acceptance'):
            if not isinstance(cap.get(key), str) or not cap[key].strip():
                errors.append(f'{cid}: missing {key}')
        for key in ('sources', 'tests', 'docs'):
            paths = cap.get(key)
            if not isinstance(paths, list) or not paths:
                errors.append(f'{cid}: missing {key}'); continue
            for name in paths:
                if not exists(name):
                    errors.append(f'{cid}: missing/unsafe {key} reference')
        deps = cap.get('depends_on')
        if not isinstance(deps, list) or any(not isinstance(d, str) for d in deps):
            errors.append(f'{cid}: invalid dependencies'); deps = []
        graph[cid] = deps
    for cid, deps in graph.items():
        if any(d not in ids for d in deps):
            errors.append(f'{cid}: unknown dependency')
    visiting, visited = set(), set()
    def visit(cid):
        if cid in visiting:
            errors.append('Capability dependency cycle'); return
        if cid in visited or cid not in graph:
            return
        visiting.add(cid)
        for dep in graph[cid]: visit(dep)
        visiting.remove(cid); visited.add(cid)
    for cid in graph: visit(cid)
    records = {}
    for path in sorted((public / '.changes').glob('*.json')):
        item = read(path)
        if not isinstance(item, dict):
            errors.append(f'{path.name}: change must be an object'); continue
        expected = {'id', 'kind', 'summary', 'capabilities', 'files', 'validation', 'compatibility', 'release'}
        if set(item) not in (expected, expected | {'handoff'}):
            errors.append(f'{path.name}: change keys must match schema')
        from project_handoff import handoff_errors
        if 'handoff' in item or path.stem not in LEGACY_RECORDS:
            errors.extend(f'{path.name}: {e}' for e in handoff_errors(item))
        if item.get('id') != path.stem or not re.fullmatch(r'\d{8}T\d{6}Z-[a-z0-9-]+', path.stem):
            errors.append(f'{path.name}: invalid change id')
        if item.get('kind') not in {'feature', 'fix', 'docs', 'refactor', 'test', 'build', 'security'}:
            errors.append(f'{path.name}: invalid change kind')
        for key in ('summary', 'validation', 'compatibility'):
            if not isinstance(item.get(key), str) or not item[key].strip():
                errors.append(f'{path.name}: missing {key}')
        affected = item.get('capabilities')
        if not isinstance(affected, list) or not affected or any(not isinstance(c, str) or c not in ids for c in affected):
            errors.append(f'{path.name}: unknown/missing capabilities')
        names = item.get('files')
        if not isinstance(names, list) or not names or any(not safe_path(n) for n in names):
            errors.append(f'{path.name}: invalid files')
        elif len(names) != len(set(names)):
            errors.append(f'{path.name}: duplicate file references')
        release = item.get('release')
        if release is not None and (not isinstance(release, str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?', release)):
            errors.append(f'{path.name}: release must be null or version')
        records[f'.changes/{path.name}'] = item
    if not records:
        errors.append('No change records')
    if check_index and not errors:
        from project_handoff import index_errors
        errors.extend(index_errors(root))
    return errors, records


def validate_diff(root, base, records):
    """Check the complete PR diff, not just its last commit. No changes are executed."""
    if not re.fullmatch(r'[0-9a-fA-F]{40,64}', base):
        return ['--base must be a full commit SHA']
    try:
        ancestor = subprocess.check_output(['git', 'merge-base', base, 'HEAD'], cwd=root).decode().strip()
        output = subprocess.check_output(
            ['git', 'diff', '--name-status', '--no-renames', '-z', ancestor, 'HEAD'],
            cwd=root).decode('utf-8')
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        return ['Cannot compare base; fetch full history and provide an existing base SHA']
    fields = output.split('\0')
    changes = dict(zip(fields[1::2], fields[0::2]))
    if not changes:
        return []
    added = [n for n, s in changes.items() if n.startswith('.changes/') and n.endswith('.json') and s == 'A']
    if not added:
        return ['Every non-empty PR requires a new .changes/<UTC timestamp>-<slug>.json']
    errors = []
    covered = set()
    for name in added:
        if name not in records:
            errors.append(f'{name}: missing valid change record'); continue
        from project_handoff import handoff_errors
        if Path(name).stem not in LEGACY_RECORDS or 'handoff' in records[name]:
            errors.extend(f'{name}: {e}' for e in handoff_errors(records[name]))
        covered.update(records[name].get('files', []))
    # The manifest is a generated artifact; fragments themselves need no self-reference.
    required = {n for n in changes if n not in added and n not in {'SOURCE_MANIFEST.json', 'docs/PROJECT_ACTIVITY.md'}}
    missing = required - covered
    if missing:
        errors.append('Changed files absent from new records: ' + ', '.join(sorted(missing)))
    # Published records are immutable except for assigning a release once.
    for name, status in changes.items():
        if not name.startswith('.changes/') or not name.endswith('.json') or status == 'A':
            continue
        try:
            previous = json.loads(subprocess.check_output(['git', 'show', f'{ancestor}:{name}'], cwd=root))
            current = records.get(name)
            assign = (current is not None and previous.get('release') is None and current.get('release') is not None
                      and {k:v for k,v in previous.items() if k != 'release'} == {k:v for k,v in current.items() if k != 'release'})
            if not assign: errors.append(f'{name}: existing records cannot be rewritten/deleted; add a correction record')
        except (OSError, ValueError, subprocess.CalledProcessError):
            errors.append(f'{name}: cannot verify prior change record')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--base', help='Full PR base SHA; requires Git checkout with history')
    parser.add_argument('--notes', action='store_true', help='Print pending release notes without editing files')
    args = parser.parse_args()
    errors, records = validate(args.root)
    if not errors and args.base:
        errors.extend(validate_diff(args.root, args.base, records))
    if errors:
        raise SystemExit('\n'.join(errors))
    if args.notes:
        for name, item in sorted(records.items()):
            if item['release'] is None:
                print(f"- [{item['kind']}] {item['summary']} ({Path(name).stem})")
    else:
        print(f'PASS project catalog, references and {len(records)} change records' + ('; PR change coverage' if args.base else '; PR diff not checked'))


if __name__ == '__main__':
    main()
