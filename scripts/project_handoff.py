#!/usr/bin/env python3
"""Development-only task claims, change receipts and deterministic handoff index."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

STATE = '.project-local'
INDEX = 'docs/PROJECT_ACTIVITY.md'
EXCLUDED = {'.runtime', '.git', '.release', '.venv', 'node_modules', '__pycache__',
            STATE, 'evidence', 'screenshots', 'samples', '.changes'}
SUFFIXES = {'.md', '.py', '.js', '.cjs', '.ts', '.html', '.css', '.json', '.yml', '.yaml', '.txt', '.toml', '.command'}


def public_root(root):
    return root / 'release/public' if (root / 'release/public').is_dir() else root


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(content, encoding='utf-8')
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


@contextmanager
def locked(root):
    folder = root / STATE
    folder.mkdir(exist_ok=True)
    lock = folder / 'write.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        raise ValueError('Another handoff writer is active; retry. If interrupted, verify no writer before removing write.lock.')
    try:
        yield
    finally:
        lock.rmdir()


def safe_scope(value):
    if not isinstance(value, str):
        return False
    parts = Path(value).parts
    return (isinstance(value, str) and bool(parts) and not Path(value).is_absolute()
            and '\\' not in value and value.rstrip('/') == Path(value).as_posix()
            and '..' not in parts and not set(parts) & EXCLUDED
            and not any(p.startswith('.env') for p in parts)
            and not value.startswith('config/') and value != INDEX
            and value != 'release/public/' + INDEX)


def overlaps(a, b):
    a, b = a.rstrip('/'), b.rstrip('/')
    return a == b or a.startswith(b + '/') or b.startswith(a + '/')


def snapshot(root, scopes):
    result = {}
    for scope in scopes:
        start = root / scope
        paths = start.rglob('*') if start.is_dir() else [start]
        for p in paths:
            rel = p.relative_to(root)
            if set(rel.parts) & EXCLUDED or rel.as_posix() in {INDEX, 'release/public/' + INDEX}:
                continue
            if p.is_symlink() or root not in p.resolve().parents:
                raise ValueError('Symlinks/outside paths are not managed: ' + str(rel))
            if p.is_file() and (p.suffix in SUFFIXES or p.name in {'.gitignore', 'LICENSE'}):
                result[rel.as_posix()] = hashlib.sha256(p.read_bytes()).hexdigest()
    return result


def task_path(root, task):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', task):
        raise ValueError('Task must be a lowercase slug (max 80 characters)')
    return root / STATE / 'tasks' / (task + '.json')


def begin(root, task, scopes):
    path = task_path(root, task)
    if not scopes or any(not safe_scope(s) for s in scopes):
        raise ValueError('Use explicit source/document paths; runtime, private config and generated records are excluded')
    with locked(root):
        if path.exists():
            raise ValueError('Task already exists; use status and continue it, or choose a new task')
        for other in (root / STATE / 'tasks').glob('*.json'):
            item = read_json(other)
            if item['active'] and any(overlaps(a, b) for a in scopes for b in item['scopes']):
                raise ValueError('Scope overlaps active task ' + item['task'])
        item = dict(task=task, scopes=scopes, active=True, baseline=snapshot(root, scopes), records=[])
        if public_root(root) != root:
            from export_source import source_map
            item['public_mapping'] = {p.relative_to(root).as_posix(): name for name, p in source_map(root).items()}
        atomic_write(path, json.dumps(item, ensure_ascii=False, indent=2) + '\n')
    return item


def records(root):
    return [read_json(p) for p in sorted((public_root(root) / '.changes').glob('*.json'))]


def render_index(items):
    lines = ['# 项目更新与接续索引', '',
             '由 `python scripts/project_handoff.py sync` 从变更片段生成；不要手改。',
             '这里记录工程状态，不代表产品部署或完整功能验收。未登记的旧任务仍见 ROADMAP 与 HANDOFF_CONTEXT。', '']
    latest = {}
    for item in sorted(items, key=lambda i: i['id']):
        if item.get('handoff'):
            latest[item['handoff']['task']] = item
    def clean(text):
        return str(text).replace('\n', ' ').replace('|', '\\|')
    lines += ['## 已登记任务的最新状态', '', '| 任务 | 状态 | 下一步 | 记录 |', '|---|---|---|---|']
    for task, item in sorted(latest.items()):
        h = item['handoff']
        lines.append(f"| {clean(task)} | {clean(h['status'])} | {clean(h['next'])} | [{item['id']}](../.changes/{item['id']}.json) |")
    lines += ['', '## 全部更新', '']
    for item in sorted(items, key=lambda i: i['id'], reverse=True):
        lines.append(f"- [{item['id']}](../.changes/{item['id']}.json) — {clean(item['summary'])}")
    return '\n'.join(lines) + '\n'


def index_errors(root):
    p = public_root(root) / INDEX
    try:
        if p.read_text(encoding='utf-8') == render_index(records(root)):
            return []
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return ['Project handoff index missing/stale: run python scripts/project_handoff.py sync']


def sync(root):
    with locked(root):
        atomic_write(public_root(root) / INDEX, render_index(records(root)))


def handoff_errors(item):
    h = item.get('handoff')
    if not isinstance(h, dict) or set(h) != {'task', 'status', 'next', 'docs', 'docs_reason'}:
        return ['New records require handoff: task/status/next/docs/docs_reason']
    if (not isinstance(h['task'], str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', h['task'])
            or not isinstance(h['status'], str) or h['status'] not in {'planned', 'in_progress', 'blocked', 'complete'}
            or not isinstance(h['next'], str) or not h['next'].strip()
            or not isinstance(h['docs'], list) or any(not isinstance(p, str) or p not in item.get('files', []) for p in h['docs'])
            or not isinstance(h['docs_reason'], str) or not h['docs_reason'].strip()):
        return ['Invalid handoff metadata; docs must be changed paths and docs_reason must explain specification impact']
    return []


def record(root, task, payload):
    """Append a public record + local receipt, then refresh the index. Never run payload commands."""
    from check_project import validate
    path = task_path(root, task)
    with locked(root):
        item = read_json(path)
        if not item['active']:
            raise ValueError('Task is closed; create another task for further edits')
        now = snapshot(root, item['scopes'])
        changed = sorted(k for k in set(now) | set(item['baseline']) if now.get(k) != item['baseline'].get(k))
        # Private source maps to precisely the existing export whitelist. Local-only paths stay in local receipts.
        if public_root(root) != root:
            from export_source import source_map
            mapping = {p.relative_to(root).as_posix(): name for name, p in source_map(root).items()}
            # Deleted paths were captured at begin, before they disappeared.
            mapping.update(item.get('public_mapping', {}))
        else:
            mapping = {name: name for name in changed}
        public_files = sorted({mapping[n] for n in changed if n in mapping})
        # State-only updates still need a dated record, but private paths remain local.
        cid = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + task + '-' + uuid.uuid4().hex[:6]
        entry = {**payload, 'id': cid, 'files': public_files, 'release': None}
        if not isinstance(entry.get('handoff'), dict) or entry['handoff'].get('task') != task:
            raise ValueError('Handoff task must match the active task')
        if not public_files:
            # A public-neutral engineering receipt still updates the public project index; private filenames are never copied.
            entry['files'] = [INDEX]
        issues = handoff_errors(entry)
        if issues:
            raise ValueError('\n'.join(issues))
        out = public_root(root) / '.changes' / (cid + '.json')
        atomic_write(out, json.dumps(entry, ensure_ascii=False, indent=2) + '\n')
        try:
            errors, _ = validate(root, check_index=False)
            if errors:
                raise ValueError('\n'.join(errors))
        except Exception:
            out.unlink()
            raise
        item.update(baseline=now, active=entry['handoff']['status'] != 'complete')
        item['records'].append({'id': cid, 'local_files': changed})
        atomic_write(path, json.dumps(item, ensure_ascii=False, indent=2) + '\n')
        atomic_write(public_root(root) / INDEX, render_index(records(root)))
    return entry


def status(root):
    result = []
    for p in sorted((root / STATE / 'tasks').glob('*.json')):
        item = read_json(p)
        now = snapshot(root, item['scopes']) if item['active'] else item['baseline']
        result.append({'task': item['task'], 'active': item['active'], 'scopes': item['scopes'],
                       'unrecorded': sorted(k for k in set(now) | set(item['baseline']) if now.get(k) != item['baseline'].get(k))})
    return result


def release_errors(root):
    return ['Unrecorded local changes: ' + i['task'] + '; record changes before candidate export (do not discard claims)'
            for i in status(root) if i['unrecorded']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest='command', required=True)
    b = sub.add_parser('begin'); b.add_argument('--task', required=True); b.add_argument('--scope', nargs='+', required=True)
    r = sub.add_parser('record'); r.add_argument('--task', required=True); r.add_argument('--input', type=Path, required=True)
    sub.add_parser('status')
    s = sub.add_parser('sync'); s.add_argument('--check', action='store_true')
    args = parser.parse_args(); root = args.root.resolve()
    if args.command == 'begin':
        result = begin(root, args.task, args.scope)
        print('Read AGENTS.md, START_HERE.md, GOVERNANCE.md, ROADMAP/HANDOFF and PROJECT_ACTIVITY before editing.')
        print(json.dumps({'task': result['task'], 'scopes': result['scopes']}, ensure_ascii=False))
    elif args.command == 'record':
        print(record(root, args.task, read_json(args.input))['id'])
    elif args.command == 'status':
        print(json.dumps(status(root), ensure_ascii=False, indent=2))
    elif args.check:
        errors = index_errors(root)
        if errors: raise ValueError('\n'.join(errors))
        print('PASS project handoff index')
    else:
        sync(root); print('Updated project handoff index')


if __name__ == '__main__':
    try: main()
    except (ValueError, OSError, KeyError) as error: raise SystemExit(str(error))
