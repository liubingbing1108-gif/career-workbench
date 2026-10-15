#!/usr/bin/env python3
"""Explicit first-run initialization. Never overwrites an existing runtime."""
import json
from contextlib import closing
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def initialize(root=ROOT):
    root = Path(root).resolve()
    runtime = root / '.runtime'
    # An incomplete/old installation requires recovery, never silent replacement.
    if any((runtime / name).exists() for name in ('locations.json', 'profile', 'management')):
        raise ValueError('已有资料目录或配置，拒绝覆盖。请使用启动命令或按恢复文档处理。')
    sys.path[:0] = [str(ROOT / 'prototypes/profile-lab'), str(ROOT / 'prototypes/management-lab')]
    from lab import Lab
    from store import Store
    runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
    lab = Lab(runtime / 'profile')
    lab.db.close()
    store = Store(runtime / 'management')
    # Store opens short-lived connections; verify both databases before publishing config.
    import sqlite3
    for relative in ('profile/lab.sqlite', 'management/management.sqlite3'):
        path = runtime / relative
        with closing(sqlite3.connect(path)) as db:
            if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise ValueError('初始化核对失败，保留现场，请按恢复文档检查。')
        path.chmod(0o600)
    config = runtime / 'locations.json'
    with config.open('x', encoding='utf-8') as handle:
        json.dump({'profile': '.runtime/profile', 'management': '.runtime/management'}, handle)
    config.chmod(0o600)
    return config


if __name__ == '__main__':
    try:
        initialize()
        print('已建立空白资料库。运行 python scripts/start_workbench.py 启动。')
    except ValueError as error:
        raise SystemExit(str(error))
