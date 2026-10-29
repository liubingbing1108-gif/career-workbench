#!/usr/bin/env python3
"""Rehearse/commit the profile migration with SQLite backup and guarded rollback.

Reports contain IDs and counts, never print personal values. Migration candidates
and backups are private. Opening the source uses read-only SQLite unless applying.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'prototypes/profile-lab'))
from profile_migration import prepare, state_hash


from contextlib import contextmanager


@contextmanager
def database(*args, **kwargs):
    connection = sqlite3.connect(*args, **kwargs)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def blob_digest(db):
    h = hashlib.sha256()
    count = 0
    for fid, body in db.execute('SELECT id,body FROM files ORDER BY id'):
        h.update(fid.encode());h.update(hashlib.sha256(body).digest());count += 1
    return dict(count=count, sha256=h.hexdigest())


def read_state(db):
    return json.loads(db.execute('SELECT body FROM state WHERE id=1').fetchone()[0])


def originals_inventory(db, state):
    """Verify the storage actually used by Lab.file_bytes, without exporting content."""
    blobs={fid:(len(body),hashlib.sha256(body).hexdigest()) for fid,body in db.execute('SELECT id,body FROM files')}
    metadata={f['id']:f for f in state.get('files',[])}
    missing=sorted(set(metadata)-set(blobs))
    mismatches=[fid for fid,f in metadata.items() if fid in blobs and
                ((f.get('size') is not None and f['size']!=blobs[fid][0]) or (f.get('sha256') and f['sha256']!=blobs[fid][1]))]
    if missing or mismatches:raise ValueError(f'原件核对失败：缺少BLOB {len(missing)}，元数据不一致 {len(mismatches)}')
    return dict(storage='sqlite.files.body',metadata_count=len(metadata),blob_count=len(blobs),unlisted_blob_count=len(set(blobs)-set(metadata)))


def database_digest(db):
    return hashlib.sha256('\n'.join(db.iterdump()).encode()).hexdigest()


@contextmanager
def management_guard(report):
    if not report.get('management'):
        yield
        return
    with database(Path(report['management']['source']).as_uri()+'?mode=rw',uri=True) as db:
        db.execute('BEGIN IMMEDIATE')
        if database_digest(db)!=report['management']['sha256']:raise ValueError('管理库在演练后已变化，请重新核对')
        yield


def review(output, data):
    """Apply an explicitly confirmed, hash-bound review to the isolated candidate."""
    from lab import find
    from profile_pending import resolve, token as pending_token
    from profile_current import save_record
    from profile_library import token as entry_token
    output=Path(output).resolve();report=json.loads((output/'report.json').read_text())
    if data.get('confirmed') is not True or not isinstance(data.get('request_id'),str) or not data['request_id']:
        raise ValueError('迁移核对需要明确确认及请求标识')
    signature=state_hash(data)
    with database(output/'candidate.sqlite') as db:
        db.execute('BEGIN IMMEDIATE');state=read_state(db)
        if blob_digest(db)!=report['originals'] or state_hash(state)!=report['candidate_hash']:raise ValueError('候选或原件已变化')
        receipt=report.get('review_receipts',{}).get(data['request_id'])
        if receipt:
            if receipt['signature']!=signature:raise ValueError('核对请求标识已用于不同内容')
            return dict(status='already_reviewed',candidate_hash=report['candidate_hash'])
        if data.get('expected_hash')!=report['candidate_hash']:raise ValueError('核对依据已变化，请重新查看候选')
        commands=data.get('commands')
        if not isinstance(commands,list) or not commands:raise ValueError('核对步骤不能为空')
        for index,command in enumerate(commands):
            args=dict(command.get('data',{}));args['request_id']=data['request_id']+':'+str(index)
            if command.get('operation')=='pending':
                item=find(state['profile_pending'],args.get('id'))
                args.update(confirmed=True,edit_token=pending_token(state,item));resolve(state,args)
            elif command.get('operation')=='record':
                if args.get('entry_id'):args['edit_token']=entry_token(state,find(state['entries'],args['entry_id']))
                save_record(state,args)
            elif command.get('operation')=='discard_legacy_answer':
                version=find(state.get('answer_versions',[]),args.get('version_id'))
                entry=find(state['entries'],version['entry_id'])
                if entry.get('default_versions',{}).get(version['field_id'])==version['id']:
                    raise ValueError('不能移除当前答案；请先明确选择当前内容')
                if any(version['id'] in v.get('field_versions',{}).values() for e in state['entries'] for v in e.get('expression_versions',[])):
                    raise ValueError('答案仍属于可用表达版本')
                # Retain bytes for historical references and missing-evidence holds.
                version['profile_deleted']=True
            elif command.get('operation')=='normalize_startup':
                from lab import normalize_startup,reconcile_semantic_imports
                from profile_trash import expire
                expire(state);normalize_startup(state);reconcile_semantic_imports(state)
            else:raise ValueError('未知核对步骤；不允许直接替换原始state')
        revised_hash=state_hash(state)
        db.execute('UPDATE state SET body=? WHERE id=1',(json.dumps(state,ensure_ascii=False),))
        if state_hash(read_state(db))!=revised_hash:raise ValueError('核对回读失败')
    report['candidate_hash']=revised_hash
    report['pending']=sum(p['state']=='pending' for p in state.get('profile_pending',[]))
    report.setdefault('review_receipts',{})[data['request_id']]=dict(signature=signature,candidate_hash=revised_hash)
    staged=output/'report.next.json';staged.write_text(json.dumps(report,ensure_ascii=False,indent=2));staged.chmod(0o600);staged.replace(output/'report.json')
    return dict(status='reviewed',candidate_hash=revised_hash,pending=report['pending'])


def rehearsal(source, output, timestamp=None, management_source=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if output.exists():raise ValueError('演练目录已存在，拒绝覆盖')
    output.mkdir(parents=True, mode=0o700)
    os.chmod(output, 0o700)
    with database(source.as_uri()+'?mode=ro', uri=True) as db:
        with database(output/'backup.sqlite') as backup:db.backup(backup)
    with database(output/'backup.sqlite') as db:
        original = read_state(db); blobs = blob_digest(db); inventory=originals_inventory(db,original)
        migrated, report = prepare(original, timestamp if timestamp is not None else time.time())
        with database(output/'candidate.sqlite') as candidate:db.backup(candidate)
    with database(output/'candidate.sqlite') as db:
        db.execute('UPDATE state SET body=? WHERE id=1', (json.dumps(migrated, ensure_ascii=False),))
        db.commit()
        if state_hash(read_state(db)) != state_hash(migrated) or blob_digest(db) != blobs:
            raise ValueError('迁移回读或原件校验失败')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':raise ValueError('SQLite完整性检查失败')
    if management_source:
        management_source=Path(management_source).resolve()
        with database(management_source.as_uri()+'?mode=ro',uri=True) as management:
            with database(output/'management-backup.sqlite') as backup:management.backup(backup)
        with database(output/'management-backup.sqlite') as backup:
            if backup.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('管理库完整性检查失败')
            job_ids={row[0] for row in backup.execute('SELECT id FROM jobs')}
            if any(s.get('management_job_id') and s['management_job_id'] not in job_ids for s in original['sessions']):raise ValueError('资料会话引用了不存在的管理岗位')
            report['management']=dict(source=str(management_source),sha256=database_digest(backup))
    report.update(source=str(source), originals=blobs, originals_inventory=inventory, candidate_hash=state_hash(migrated), created_at=time.time(), status='rehearsed')
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    for path in output.iterdir():os.chmod(path, 0o600)
    return report


def apply(output):
    output = Path(output).resolve();report = json.loads((output/'report.json').read_text())
    with database(output/'candidate.sqlite') as candidate:
        desired = read_state(candidate)
        if state_hash(desired) != report['candidate_hash'] or blob_digest(candidate) != report['originals']:
            raise ValueError('候选或原件已变化，请重新演练')
    with management_guard(report), database(Path(report['source']).as_uri()+'?mode=rw', uri=True) as db:
        db.execute('BEGIN IMMEDIATE')
        current = state_hash(read_state(db))
        if current == report['candidate_hash'] and blob_digest(db)==report['originals']:return dict(status='already_applied')
        if current != report['input_hash'] or blob_digest(db) != report['originals']:
            raise ValueError('活动库在演练后已变化，拒绝覆盖，请重新演练')
        if any(s.get('preparation',{}).get('execution',{}).get('status') in {'running','awaiting_executor'} for s in read_state(db).get('sessions',[])):
            raise ValueError('仍有执行任务，请先停止后重新演练')
        db.execute('UPDATE state SET body=? WHERE id=1', (json.dumps(desired, ensure_ascii=False),))
        if state_hash(read_state(db)) != report['candidate_hash']:raise ValueError('切换回读失败')
    return dict(status='applied', hash=report['candidate_hash'])


def rollback(output):
    output = Path(output).resolve();report = json.loads((output/'report.json').read_text())
    with database(output/'backup.sqlite') as backup:
        original = read_state(backup)
        if state_hash(original) != report['input_hash'] or blob_digest(backup)!=report['originals']:raise ValueError('备份校验失败')
    with database(Path(report['source']).as_uri()+'?mode=rw', uri=True) as db:
        db.execute('BEGIN IMMEDIATE')
        current = state_hash(read_state(db))
        if current == report['input_hash'] and blob_digest(db)==report['originals']:return dict(status='already_rolled_back')
        if current != report['candidate_hash'] or blob_digest(db) != report['originals']:
            raise ValueError('切换后已有写入，拒绝丢弃新数据；需保留新写入并制定前向修复')
        db.execute('UPDATE state SET body=? WHERE id=1', (json.dumps(original, ensure_ascii=False),))
    return dict(status='rolled_back')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['rehearse', 'review', 'apply', 'rollback'])
    parser.add_argument('--source', type=Path)
    parser.add_argument('--management-source', type=Path)
    parser.add_argument('--decisions', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.action == 'rehearse' and not args.source:parser.error('rehearse requires --source')
    if args.action=='review' and not args.decisions:parser.error('review requires --decisions')
    result = rehearsal(args.source, args.output, management_source=args.management_source) if args.action == 'rehearse' else review(args.output,json.loads(args.decisions.read_text())) if args.action=='review' else apply(args.output) if args.action == 'apply' else rollback(args.output)
    print(json.dumps({k:v for k,v in result.items() if k != 'source'}, ensure_ascii=False))
